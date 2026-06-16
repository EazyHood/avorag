"""Fábrica del clasificador de visión según configuración (instancia cacheada)."""

from __future__ import annotations

from functools import lru_cache

from avorag.config import get_settings
from avorag.vision.base import DisabledVisionClassifier, VisionClassifier


@lru_cache
def get_vision_classifier() -> VisionClassifier:
    p = get_settings().vision_provider.lower()
    if p in ("none", "", "off"):
        return DisabledVisionClassifier()
    if p == "fake":
        from avorag.vision.fakes import FakeVisionClassifier

        return FakeVisionClassifier()
    if p == "local":
        from avorag.vision.classifier import LocalVisionClassifier

        return LocalVisionClassifier()
    if p == "onnx":
        from avorag.vision.classifier import OnnxVisionClassifier

        return OnnxVisionClassifier()
    raise ValueError(f"VISION_PROVIDER desconocido: {p!r}")
