"""Describidor visual de síntomas (VLM) → consulta al motor RAG.

A diferencia del clasificador (modelo entrenado que devuelve una clase), aquí un modelo de
VISIÓN-LENGUAJE (VLM) DESCRIBE objetivamente lo visible en la foto (manchas, lesiones, insectos…)
SIN diagnosticar. Esa descripción se convierte en una consulta para `avorag.rag.answer()`, que
IDENTIFICA la plaga/enfermedad y aconseja CITANDO la fuente oficial (con semáforo y guardarraíles).

Por qué esta vía: identificar plagas del Hass por foto a calidad profesional con un clasificador
propio exige un dataset de imágenes grande y bien-licenciado que HOY no existe. El VLM no lo
necesita: aporta la descripción visual y el corpus curado aporta la identificación citada.

Frontera de seguridad (igual que el clasificador): la visión DESCRIBE; el RAG diagnostica y aconseja
con citas. La salida se comunica como CANDIDATOS posibles, nunca como veredicto.

Proveedores intercambiables por `.env` (VISION_DESCRIBER_PROVIDER): none | fake | ollama | anthropic.
"""

from __future__ import annotations

import base64
import io
from abc import ABC, abstractmethod

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.vision.schemas import SymptomReport

log = get_logger(__name__)

# Soporte HEIC opcional (fotos de iPhone), idéntico al del clasificador.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001 — opcional
    pass

_NO_SYMPTOMS_MARK = "SIN SINTOMAS CLAROS"
_MAX_SIDE = 1568  # lado largo máx para el VLM (equilibra calidad, latencia y costo)

_DESCRIBE_SYSTEM = (
    "Eres un asistente que SOLO describe lo visible en una foto de un cultivo de aguacate Hass. "
    "NO diagnostiques NI recomiendes tratamientos ni dosis.\n"
    "IMPORTANTE — lo que es NORMAL en un Hass sano y NO debes reportar como síntoma: la piel es muy "
    "rugosa y granulada, con MUCHOS puntos claros (lenticelas); puede tener parches corchosos marrones "
    "(russeting) y pequeñas marcas naturales; al madurar se oscurece a morado/negro de forma uniforme y "
    "se arruga un poco. Nada de eso es enfermedad.\n"
    "Reporta SOLO lo que claramente se sale de lo normal: manchas con halo o anillos concéntricos, "
    "pudrición o zonas hundidas/blandas, lesiones húmedas, perforaciones con galerías, insectos o "
    "ácaros, telarañas, excrementos o mielecilla, mohos. Describe en español, breve y objetivo: la parte "
    "de la planta y los síntomas ANÓMALOS con su color/forma/borde. Ante la DUDA, o si solo ves piel "
    f"rugosa/madura normal sin anomalías, responde EXACTAMENTE: {_NO_SYMPTOMS_MARK}"
)
_DESCRIBE_USER = "Describe los síntomas visibles en esta foto."


def _to_jpeg_b64(image: bytes) -> str:
    """Decodifica cualquier formato (incl. HEIC), endereza por EXIF, reescala y reencoda a JPEG
    base64 — robusto a fotos reales y al formato que aceptan los VLM."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = 60_000_000
    try:
        img: Image.Image = Image.open(io.BytesIO(image))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("no pude leer la imagen (¿formato no soportado o archivo dañado?)") from e
    w, h = img.size
    if max(w, h) > _MAX_SIDE:
        s = _MAX_SIDE / max(w, h)
        img = img.resize((max(1, round(w * s)), max(1, round(h * s))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def _report_from_text(text: str, *, provider: str) -> SymptomReport:
    t = (text or "").strip()
    no_sym = (not t) or (_NO_SYMPTOMS_MARK.lower() in t.lower())
    return SymptomReport(descripcion="" if no_sym else t, sin_sintomas=no_sym, provider=provider)


def build_health_query(report: SymptomReport) -> str | None:
    """Convierte la descripción de síntomas en una consulta para el RAG (None si no hay nada útil)."""
    if report.sin_sintomas or not report.descripcion.strip():
        return None
    return (
        f"Síntomas observados en una foto de aguacate Hass: {report.descripcion.strip()} "
        "¿Qué plaga o enfermedad del aguacate Hass podría ser? Indica los 2-3 candidatos más "
        "probables, cómo distinguirlos entre sí y su manejo, citando las fuentes."
    )


class VisionDescriber(ABC):
    """Recibe los bytes de una imagen y DESCRIBE síntomas (no diagnostica)."""

    name: str = "desconocido"

    @abstractmethod
    def describe(self, image: bytes) -> SymptomReport: ...

    @property
    def available(self) -> bool:
        return True


class DisabledDescriber(VisionDescriber):
    """Activo con VISION_DESCRIBER_PROVIDER=none."""

    name = "disabled"

    @property
    def available(self) -> bool:
        return False

    def describe(self, image: bytes) -> SymptomReport:
        raise RuntimeError(
            "El describidor visual no está configurado (VISION_DESCRIBER_PROVIDER=none). "
            "Usa =fake (demo), =ollama (VLM local) o =anthropic (Claude visión)."
        )


class FakeDescriber(VisionDescriber):
    """Determinista para demo/tests (sin VLM). Devuelve síntomas de ejemplo (compatibles con trips)."""

    name = "fake"

    def describe(self, image: bytes) -> SymptomReport:
        return SymptomReport(
            descripcion=(
                "Hoja de aguacate con pequeñas manchas plateadas y raspaduras en el haz, puntos "
                "negros diminutos (posibles excrementos) y algunos insectos alargados muy pequeños."
            ),
            provider="fake",
        )


class OllamaVisionDescriber(VisionDescriber):
    """VLM local vía Ollama (p.ej. llava, qwen2.5-vl). Gratis y offline; requiere `ollama pull`."""

    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        from ollama import Client

        s = get_settings()
        self._client = Client(host=s.ollama_host)
        self._model = model or s.vision_describer_model or "llava:7b"

    def describe(self, image: bytes) -> SymptomReport:
        b64 = _to_jpeg_b64(image)
        resp = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": _DESCRIBE_SYSTEM},
                {"role": "user", "content": _DESCRIBE_USER, "images": [b64]},
            ],
            options={"temperature": 0.1},
        )
        return _report_from_text(resp.message.content or "", provider=f"ollama:{self._model}")


class AnthropicVisionDescriber(VisionDescriber):
    """Claude (Anthropic) con visión: más preciso describiendo síntomas. Requiere API key (costo)."""

    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        from anthropic import Anthropic

        s = get_settings()
        if not s.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY vacío pero VISION_DESCRIBER_PROVIDER=anthropic")
        self._client = Anthropic(api_key=s.anthropic_api_key)
        self._model = model or s.vision_describer_model or s.anthropic_model

    def describe(self, image: bytes) -> SymptomReport:
        b64 = _to_jpeg_b64(image)
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=400,
            temperature=0.1,
            system=_DESCRIBE_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                        },
                        {"type": "text", "text": _DESCRIBE_USER},
                    ],
                }
            ],
        )
        txt = "".join(b.text for b in resp.content if b.type == "text")
        return _report_from_text(txt, provider=f"anthropic:{self._model}")
