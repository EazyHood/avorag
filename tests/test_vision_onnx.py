"""Tests de los helpers compartidos del clasificador y del proveedor ONNX.

Cubren lógica pura (sin torch ni onnxruntime): construcción del resultado desde probabilidades,
softmax, y que el registro devuelve el clasificador ONNX (sin importar onnxruntime, que es lazy).
"""

from __future__ import annotations

import numpy as np

from avorag.config import Settings
from avorag.vision import classifier as C
from avorag.vision import registry
from avorag.vision.classifier import OnnxVisionClassifier
from avorag.vision.registry import get_vision_classifier
from avorag.vision.schemas import VisionKind, VisionResult


def test_result_from_probs_top_y_orden() -> None:
    classes = ["madurez_verde", "trips", "sano"]
    r = C._result_from_probs([0.1, 0.7, 0.2], classes, top_k=3, min_conf=0.55, model_version="t")
    assert isinstance(r, VisionResult)
    assert r.top is not None and r.top.label == "trips" and r.top.kind == VisionKind.PATOLOGIA
    assert [p.label for p in r.predictions] == ["trips", "sano", "madurez_verde"]  # orden desc
    assert not r.requires_review and r.kind == VisionKind.PATOLOGIA
    assert r.model_version == "t"


def test_result_from_probs_baja_confianza_requiere_revision() -> None:
    r = C._result_from_probs(
        [0.4, 0.35, 0.25],
        ["madurez_verde", "trips", "sano"],
        top_k=2,
        min_conf=0.55,
        model_version="t",
    )
    assert r.requires_review and r.kind == VisionKind.DESCONOCIDO
    assert len(r.predictions) == 2  # respeta top_k


def test_result_from_probs_indice_fuera_de_clases() -> None:
    # Menos nombres que probabilidades → cae a str(index) sin romper.
    r = C._result_from_probs([0.9, 0.1], ["solo_una"], top_k=2, min_conf=0.5, model_version="t")
    assert r.predictions[0].label == "solo_una"
    assert r.predictions[1].label == "1"


def test_softmax_suma_uno() -> None:
    s = C._softmax(np.array([2.0, 1.0, 0.1]))
    assert abs(float(s.sum()) - 1.0) < 1e-6
    assert int(s.argmax()) == 0


def test_registry_onnx_devuelve_onnx_classifier(monkeypatch) -> None:
    get_vision_classifier.cache_clear()
    monkeypatch.setattr(registry, "get_settings", lambda: Settings(vision_provider="onnx"))
    try:
        assert isinstance(get_vision_classifier(), OnnxVisionClassifier)
    finally:
        get_vision_classifier.cache_clear()


def test_onnx_available_false_sin_modelo() -> None:
    # Instanciar NO importa onnxruntime (lazy); available solo mira el disco.
    clf = OnnxVisionClassifier(
        model_path="no/existe/model.onnx", labels_path="no/existe/labels.json"
    )
    assert clf.available is False
