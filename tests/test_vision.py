"""Módulo de visión: clasificador fake, mapeo de etiquetas, puente al RAG y frontera de seguridad.

No requiere torch, ni un modelo entrenado, ni DB ni LLM (usa el clasificador fake y monkeypatch
del motor RAG), igual que el resto de la suite.
"""

from __future__ import annotations

import avorag.rag
from avorag.vision import bridge as D
from avorag.vision.base import DisabledVisionClassifier
from avorag.vision.fakes import FakeVisionClassifier
from avorag.vision.labels import LABELS, display_for, kind_for, question_for
from avorag.vision.registry import get_vision_classifier
from avorag.vision.schemas import VisionKind, VisionResult

_IMG = b"\xff\xd8\xff\xe0bytes-de-una-foto-cualquiera"


# --- clasificador fake ---
def test_fake_classifier_es_determinista_y_bien_formado() -> None:
    clf = FakeVisionClassifier()
    r1 = clf.classify(_IMG, top_k=3)
    r2 = clf.classify(_IMG, top_k=3)
    assert isinstance(r1, VisionResult)
    assert r1.top is not None
    assert r1.model_dump() == r2.model_dump()  # mismo input -> misma salida
    assert len(r1.predictions) == 3
    # Probabilidades ordenadas desc y la primera es la 'top'.
    confs = [p.confidence for p in r1.predictions]
    assert confs == sorted(confs, reverse=True)
    assert r1.top.label == r1.predictions[0].label
    assert r1.disclaimer  # siempre lleva el aviso de "no es diagnóstico"


def test_fake_classifier_top_k_distinto() -> None:
    clf = FakeVisionClassifier()
    assert len(clf.classify(_IMG, top_k=1).predictions) == 1
    assert len(clf.classify(_IMG, top_k=5).predictions) == 5


# --- mapeo de etiquetas ---
def test_todas_las_clases_tienen_metadatos_coherentes() -> None:
    for key, info in LABELS.items():
        assert question_for(key) == info.question
        assert display_for(key) == info.es
        assert kind_for(key) == info.kind
        assert info.kind in (VisionKind.MADUREZ, VisionKind.PATOLOGIA)
        assert "Hass" in info.question or "aguacate" in info.question.lower()


def test_clase_desconocida_cae_con_seguridad() -> None:
    assert question_for("no_existe") is None
    assert display_for("no_existe") == "no_existe"
    assert kind_for("no_existe") == VisionKind.DESCONOCIDO


# --- registry ---
def test_registry_none_da_disabled() -> None:
    get_vision_classifier.cache_clear()
    from avorag.config import Settings
    from avorag.vision import registry

    orig = registry.get_settings
    registry.get_settings = lambda: Settings(vision_provider="none")
    try:
        clf = get_vision_classifier()
        assert isinstance(clf, DisabledVisionClassifier)
        assert clf.available is False
    finally:
        registry.get_settings = orig
        get_vision_classifier.cache_clear()


# --- puente visión -> RAG (frontera de seguridad) ---
def _fake_answer(question, **kwargs):
    from avorag.rag.schemas import Answer, Citation, Semaforo

    return Answer(
        question=question,
        text="Según la fuente, monitoreo y manejo integrado [1].",
        semaforo=Semaforo.VERDE,
        citations=[Citation(chunk_id="c1", fuente="ICA - Manejo fitosanitario", pagina=41)],
    )


def test_diagnose_identifica_y_consulta_al_rag(monkeypatch) -> None:
    monkeypatch.setattr(D, "get_vision_classifier", lambda: FakeVisionClassifier())
    monkeypatch.setattr(avorag.rag, "answer", _fake_answer, raising=False)

    res = D.diagnose(_IMG)
    assert res.vision.top is not None
    assert res.answer is not None
    assert "[1]" in res.answer["text"]  # la respuesta CITADA viene del RAG, no de la visión
    assert res.vision.suggested_question  # se derivó una pregunta agronómica de la etiqueta


def test_diagnose_pregunta_libre_anexa_contexto_visual(monkeypatch) -> None:
    captured: dict = {}

    def _capture(question, **kwargs):
        captured["q"] = question
        return _fake_answer(question, **kwargs)

    monkeypatch.setattr(D, "get_vision_classifier", lambda: FakeVisionClassifier())
    monkeypatch.setattr(avorag.rag, "answer", _capture, raising=False)

    D.diagnose(_IMG, question="¿qué hago con esto?")
    assert "¿qué hago con esto?" in captured["q"]
    assert "Contexto visual" in captured["q"]  # se inyecta la etiqueta detectada


def test_diagnose_no_llama_al_rag_si_run_rag_false(monkeypatch) -> None:
    def _boom(*a, **k):
        raise AssertionError("run_rag=False no debe consultar al RAG")

    monkeypatch.setattr(D, "get_vision_classifier", lambda: FakeVisionClassifier())
    monkeypatch.setattr(avorag.rag, "answer", _boom, raising=False)

    res = D.diagnose(_IMG, run_rag=False)
    assert res.answer is None
    assert res.vision.top is not None  # la identificación sí ocurre


def test_diagnose_baja_confianza_sin_pregunta_no_inventa(monkeypatch) -> None:
    # Identificación poco fiable y sin pregunta del usuario -> NO se llama al RAG (no se inventa).
    class _UncertainClf(FakeVisionClassifier):
        def classify(self, image: bytes, *, top_k: int = 3) -> VisionResult:
            r = super().classify(image, top_k=top_k)
            r.requires_review = True
            r.top.confidence = 0.20
            return r

    def _boom(*a, **k):
        raise AssertionError("con baja confianza y sin pregunta no se debe consultar al RAG")

    monkeypatch.setattr(D, "get_vision_classifier", lambda: _UncertainClf())
    monkeypatch.setattr(avorag.rag, "answer", _boom, raising=False)

    res = D.diagnose(_IMG)
    assert res.answer is None
    assert res.vision.requires_review is True
