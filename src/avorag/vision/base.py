"""Interfaz del clasificador de visión. Permite cambiar el modelo por configuración.

Igual que `providers/base.py` para LLM/embeddings: una ABC mínima y proveedores intercambiables
(`none` | `fake` | `local`) seleccionados en `vision/registry.py` según `.env`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from avorag.vision.schemas import VisionResult


class VisionClassifier(ABC):
    """Recibe los bytes de una imagen y devuelve una identificación (no un diagnóstico)."""

    model_version: str = "desconocido"

    @abstractmethod
    def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
        """Clasifica la imagen y devuelve las `top_k` clases más probables."""

    @property
    def available(self) -> bool:
        """True si el clasificador puede producir predicciones reales."""
        return True


class DisabledVisionClassifier(VisionClassifier):
    """Activo cuando VISION_PROVIDER=none. Señala claramente que el módulo no está configurado."""

    model_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
        raise RuntimeError(
            "El módulo de visión no está configurado (VISION_PROVIDER=none). "
            "Usa VISION_PROVIDER=fake para la demo o =local con un modelo entrenado."
        )
