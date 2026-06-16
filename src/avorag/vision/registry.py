"""Fábrica del clasificador de visión según configuración (instancia cacheada)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from avorag.config import get_settings
from avorag.vision.base import DisabledVisionClassifier, VisionClassifier

if TYPE_CHECKING:
    from avorag.vision.describe import VisionDescriber


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


@lru_cache
def get_vision_describer() -> VisionDescriber:
    """Fábrica del describidor visual de síntomas (VLM) según VISION_DESCRIBER_PROVIDER."""
    from avorag.vision import describe as d

    p = get_settings().vision_describer_provider.lower()
    if p in ("none", "", "off"):
        return d.DisabledDescriber()
    if p == "fake":
        return d.FakeDescriber()
    if p == "ollama":
        return d.OllamaVisionDescriber()
    if p == "anthropic":
        return d.AnthropicVisionDescriber()
    raise ValueError(f"VISION_DESCRIBER_PROVIDER desconocido: {p!r}")
