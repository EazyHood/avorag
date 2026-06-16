"""Clasificador fake determinista (VISION_PROVIDER=fake).

Permite probar TODO el flujo (API, CLI, integración con el RAG, tests) SIN torch ni un modelo
entrenado. Elige una clase de forma determinista a partir del hash de la imagen, así los tests son
reproducibles y la demo funciona en cualquier máquina.
"""

from __future__ import annotations

import hashlib

from avorag.vision.base import VisionClassifier
from avorag.vision.labels import LABELS, display_for, kind_for
from avorag.vision.schemas import VisionPrediction, VisionResult

# Conjunto de clases que el fake puede "reconocer" (orden estable).
_FAKE_CLASSES: tuple[str, ...] = tuple(LABELS.keys())


class FakeVisionClassifier(VisionClassifier):
    """Devuelve una clase determinista por SHA-256 de la imagen, con probabilidades decrecientes."""

    model_version = "fake-v1"

    def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
        digest = hashlib.sha256(image).digest()
        n = len(_FAKE_CLASSES)
        start = digest[0] % n
        # Probabilidad decreciente y estable; la primera supera cualquier umbral razonable.
        confs = [0.82, 0.11, 0.04, 0.02, 0.01]
        preds: list[VisionPrediction] = []
        for i in range(min(top_k, n)):
            key = _FAKE_CLASSES[(start + i) % n]
            preds.append(
                VisionPrediction(
                    label=key,
                    label_es=display_for(key),
                    kind=kind_for(key),
                    confidence=confs[i] if i < len(confs) else 0.01,
                )
            )
        top = preds[0]
        return VisionResult(
            kind=top.kind,
            top=top,
            predictions=preds,
            requires_review=False,
            model_version=self.model_version,
        )
