"""Clasificadores reales de visión.

Dos backends que comparten labels.json, preprocesamiento y construcción del resultado:
- `LocalVisionClassifier` (VISION_PROVIDER=local): TorchScript `.pt` con `torch` (extra 'vision').
- `OnnxVisionClassifier` (VISION_PROVIDER=onnx): ONNX con `onnxruntime` (extra 'vision-onnx').
  Portátil y con mejor fallback a CPU multivendor; los *execution providers* se fijan EXPLÍCITOS
  para que no caiga a CPU en silencio.

El modelo se entrena con torchvision (BSD-3) → `scripts/train_vision.py` exporta TorchScript, y
`scripts/export_onnx.py` lo convierte a ONNX. La inferencia no depende de nada copyleft.

`torch`/`onnxruntime`/`PIL` se importan de forma perezosa; `numpy` es dependencia base.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.vision.base import VisionClassifier
from avorag.vision.labels import display_for, kind_for
from avorag.vision.schemas import VisionKind, VisionPrediction, VisionResult

log = get_logger(__name__)

# Soporte HEIC/HEIF (formato por defecto de fotos de iPhone). Si pillow-heif está instalado, registra
# el decodificador en Pillow; si no, los HEIC caen a un 422 claro (no rompe el arranque).
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:  # noqa: BLE001 — soporte opcional (extra 'vision')
    _HEIC_OK = False

# Normalización por defecto (ImageNet); el labels.json puede sobreescribirla.
_DEFAULT_MEAN = (0.485, 0.456, 0.406)
_DEFAULT_STD = (0.229, 0.224, 0.225)
_DEFAULT_SIZE = 224
_MAX_IMAGE_PIXELS = 60_000_000  # ~60 MP: cubre fotos de móvil (48-50 MP); PIL lanza DecompressionBombError por encima de 2× (anti-bomba)


# ----------------------------- helpers compartidos -----------------------------
def _default_labels_path(model_path: Path) -> Path:
    """labels.json junto al modelo, por convención."""
    return model_path.with_name("labels.json")


def _load_label_meta(labels_path: Path) -> dict:
    """Lee y normaliza el labels.json (clases + preprocesamiento + versión)."""
    if not labels_path.exists():
        raise FileNotFoundError(
            f"No encuentro labels.json en {labels_path}. Debe acompañar al modelo."
        )
    raw = json.loads(labels_path.read_text("utf-8"))
    return {
        "classes": list(raw["classes"]),
        "input_size": int(raw.get("input_size", _DEFAULT_SIZE)),
        "mean": tuple(raw.get("mean", _DEFAULT_MEAN)),
        "std": tuple(raw.get("std", _DEFAULT_STD)),
        "model_version": str(raw.get("model_version", labels_path.parent.name or "modelo")),
    }


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - np.max(logits))
    return e / e.sum()


def _preprocess_np(image: bytes, size: int, mean: Any, std: Any) -> np.ndarray:
    """bytes de imagen → tensor NCHW float32 normalizado, robusto a fotos reales: cualquier formato
    (incl. HEIC si pillow-heif está), corrige la orientación EXIF (móviles) y aplana transparencia."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS  # PIL lanza DecompressionBombError por encima de 2×
    try:
        img: Image.Image = Image.open(io.BytesIO(image))
        img = ImageOps.exif_transpose(img)  # endereza fotos de móvil giradas (orientación EXIF)
    except Image.DecompressionBombError as e:
        raise ValueError("la imagen es demasiado grande; redúcela antes de subirla") from e
    except UnidentifiedImageError as e:
        hint = "" if _HEIC_OK else " Si es una foto HEIC de iPhone, conviértela a JPG."
        raise ValueError(
            f"no reconozco el formato de esta imagen (usa JPG, PNG o WebP).{hint}"
        ) from e
    except OSError as e:
        raise ValueError("el archivo de imagen está incompleto o dañado; vuelve a subirlo") from e
    if img.mode in ("RGBA", "LA", "P"):  # aplana transparencia sobre blanco (evita fondo negro)
        img = Image.alpha_composite(
            Image.new("RGBA", img.size, (255, 255, 255, 255)), img.convert("RGBA")
        ).convert("RGB")
    else:
        img = img.convert("RGB")
    w, h = img.size
    scale = size / min(w, h)  # resize lado corto + center-crop cuadrado
    img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))))
    w, h = img.size
    left, top = (w - size) // 2, (h - size) // 2
    img = img.crop((left, top, left + size, top + size))

    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC
    arr = ((arr - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)).astype(
        np.float32
    )
    arr = arr.transpose(2, 0, 1)[None, ...]  # CHW + batch
    return np.ascontiguousarray(arr, dtype=np.float32)


def _result_from_probs(
    probs: list[float],
    classes: list[str],
    *,
    top_k: int,
    min_conf: float,
    model_version: str,
) -> VisionResult:
    """Construye el VisionResult a partir del vector de probabilidades (sin dependencias de modelo)."""
    k = max(1, min(top_k, len(probs)))
    order = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)[:k]
    preds = [
        VisionPrediction(
            label=(classes[i] if i < len(classes) else str(i)),
            label_es=display_for(classes[i] if i < len(classes) else str(i)),
            kind=kind_for(classes[i] if i < len(classes) else str(i)),
            confidence=float(probs[i]),
        )
        for i in order
    ]
    top = preds[0] if preds else None
    requires_review = top is None or top.confidence < min_conf or top.kind == VisionKind.DESCONOCIDO
    return VisionResult(
        kind=top.kind if (top and not requires_review) else VisionKind.DESCONOCIDO,
        top=top,
        predictions=preds,
        requires_review=requires_review,
        model_version=model_version,
    )


def _resolve_device(pref: str) -> str:
    if pref == "cpu":
        return "cpu"
    try:
        import torch

        if pref in ("auto", "cuda") and torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001 — si torch falla, caemos a CPU
        pass
    return "cpu"


# ----------------------------- TorchScript -----------------------------
class LocalVisionClassifier(VisionClassifier):
    """Inferencia con un modelo TorchScript local. GPU si hay CUDA, si no CPU (fallback automático)."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        labels_path: str | Path | None = None,
        device: str | None = None,
    ) -> None:
        s = get_settings()
        self._model_path = Path(model_path or s.vision_model_path)
        self._labels_path = Path(
            labels_path or s.vision_labels_path or _default_labels_path(self._model_path)
        )
        self._device_pref = (device or s.vision_device or "auto").lower()
        self._min_conf = s.vision_min_confidence

        self._model: Any | None = None
        self._device = "cpu"
        self._classes: list[str] = []
        self._size = _DEFAULT_SIZE
        self._mean: tuple[float, ...] = _DEFAULT_MEAN
        self._std: tuple[float, ...] = _DEFAULT_STD
        self.model_version = "local-no-cargado"

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch  # import perezoso (extra 'vision')

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"No encuentro el modelo de visión en {self._model_path}. "
                "Entrena uno con scripts/train_vision.py o ajusta VISION_MODEL_PATH."
            )
        meta = _load_label_meta(self._labels_path)
        self._classes, self._size = meta["classes"], meta["input_size"]
        self._mean, self._std = meta["mean"], meta["std"]
        self.model_version = meta["model_version"]
        self._device = _resolve_device(self._device_pref)
        model = torch.jit.load(str(self._model_path), map_location=self._device)
        model.eval()
        self._model = model
        log.info(
            "vision_model_loaded",
            path=str(self._model_path),
            device=self._device,
            classes=len(self._classes),
            version=self.model_version,
        )

    @property
    def available(self) -> bool:
        return self._model_path.exists() and self._labels_path.exists()

    def _preprocess(self, image: bytes) -> Any:
        import torch

        arr = _preprocess_np(image, self._size, self._mean, self._std)
        return torch.from_numpy(arr).to(self._device)

    def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
        import torch

        self._ensure_loaded()
        assert self._model is not None
        x = self._preprocess(image)
        with torch.no_grad():
            probs = torch.softmax(self._model(x), dim=1)[0]
        return _result_from_probs(
            probs.tolist(),
            self._classes,
            top_k=top_k,
            min_conf=self._min_conf,
            model_version=self.model_version,
        )


# ----------------------------- ONNX -----------------------------
class OnnxVisionClassifier(VisionClassifier):
    """Inferencia con un modelo ONNX vía onnxruntime (extra 'vision-onnx').

    Más portátil que TorchScript y con mejor fallback a CPU. Los execution providers se fijan
    EXPLÍCITOS (CUDA si está disponible, si no CPU) para evitar el fallback silencioso a CPU.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        labels_path: str | Path | None = None,
    ) -> None:
        s = get_settings()
        self._model_path = Path(model_path or s.vision_model_path)
        self._labels_path = Path(
            labels_path or s.vision_labels_path or _default_labels_path(self._model_path)
        )
        self._min_conf = s.vision_min_confidence

        self._sess: Any | None = None
        self._input_name = "input"
        self._classes: list[str] = []
        self._size = _DEFAULT_SIZE
        self._mean: tuple[float, ...] = _DEFAULT_MEAN
        self._std: tuple[float, ...] = _DEFAULT_STD
        self.model_version = "onnx-no-cargado"

    def _ensure_loaded(self) -> None:
        if self._sess is not None:
            return
        import onnxruntime as ort  # import perezoso (extra 'vision-onnx')

        if not self._model_path.exists():
            raise FileNotFoundError(
                f"No encuentro el modelo ONNX en {self._model_path}. "
                "Conviértelo con scripts/export_onnx.py o ajusta VISION_MODEL_PATH."
            )
        meta = _load_label_meta(self._labels_path)
        self._classes, self._size = meta["classes"], meta["input_size"]
        self._mean, self._std = meta["mean"], meta["std"]
        self.model_version = meta["model_version"]

        # Providers EXPLÍCITOS entre los disponibles (evita el fallback silencioso a CPU).
        avail = set(ort.get_available_providers())
        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in avail]
        self._sess = ort.InferenceSession(str(self._model_path), providers=providers or None)
        self._input_name = self._sess.get_inputs()[0].name
        log.info(
            "vision_onnx_loaded",
            path=str(self._model_path),
            providers=self._sess.get_providers(),
            classes=len(self._classes),
            version=self.model_version,
        )

    @property
    def available(self) -> bool:
        return self._model_path.exists() and self._labels_path.exists()

    def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
        self._ensure_loaded()
        assert self._sess is not None
        x = _preprocess_np(image, self._size, self._mean, self._std)
        logits = np.asarray(self._sess.run(None, {self._input_name: x})[0])[0]
        probs = _softmax(logits)
        return _result_from_probs(
            probs.tolist(),
            self._classes,
            top_k=top_k,
            min_conf=self._min_conf,
            model_version=self.model_version,
        )
