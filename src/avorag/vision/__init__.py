"""Módulo de visión de AvoRAG: identifica madurez/patología en una foto y la conecta al RAG.

Esquemas reexportados de forma eager; las funciones que tocan el modelo o el RAG se cargan lazy
(vía `bridge`) para no arrastrar `torch`/`avorag.db` al importar el paquete.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from avorag.vision.schemas import (
    VisionDiagnosis,
    VisionKind,
    VisionPrediction,
    VisionResult,
)

if TYPE_CHECKING:
    from avorag.vision.bridge import classify_image, diagnose
    from avorag.vision.registry import get_vision_classifier

__all__ = [
    "VisionDiagnosis",
    "VisionKind",
    "VisionPrediction",
    "VisionResult",
    "classify_image",
    "diagnose",
    "get_vision_classifier",
]


def __getattr__(name: str) -> Any:
    if name in ("classify_image", "diagnose"):
        return getattr(importlib.import_module("avorag.vision.bridge"), name)
    if name == "get_vision_classifier":
        return importlib.import_module("avorag.vision.registry").get_vision_classifier
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
