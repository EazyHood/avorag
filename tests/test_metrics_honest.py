"""Ola 5: métricas honestas — IC Wilson, soporte de cita, alias groundedness."""

from __future__ import annotations

from avorag.eval.metrics import EvalMetrics, _citation_supported, wilson_ci
from avorag.rag.schemas import Answer, RetrievedContext


def test_wilson_ci_small_sample_is_wide() -> None:
    # 4/4 no es "100% seguro": el IC inferior debe estar bastante por debajo de 1.0.
    low, high = wilson_ci(4, 4)
    assert high == 1.0
    assert low < 0.6  # muestra pequeña -> mucha incertidumbre
    # Muestra grande -> IC estrecho.
    low2, high2 = wilson_ci(95, 100)
    assert high2 - low2 < 0.15


def _ans(text: str, ctx_content: str) -> Answer:
    return Answer(
        question="q",
        text=text,
        contexts=[RetrievedContext(chunk_id="a", fuente="ICA", score=1.0, content=ctx_content)],
    )


def test_citation_supported_true_when_figure_in_chunk() -> None:
    assert _citation_supported(_ans("Aplica 2,5 cc/L [1].", "La dosis es 2,5 cc/L.")) is True


def test_citation_supported_false_when_figure_absent() -> None:
    assert _citation_supported(_ans("Aplica 9 cc/L [1].", "La dosis es 2,5 cc/L.")) is False


def test_groundedness_is_alias_of_faithfulness() -> None:
    m = EvalMetrics(avg_faithfulness=0.91)
    assert m.groundedness == 0.91
    assert m.as_dict()["groundedness"] == 0.91
