"""Tests del dashboard HTML de evaluación (puro, sin DB ni LLM)."""

from avorag.eval.metrics import EvalMetrics
from avorag.eval.report_html import render_html


def _sample_metrics() -> EvalMetrics:
    m = EvalMetrics(
        n=5,
        n_traps=2,
        n_real=3,
        n_answered=3,
        answered_rate=1.0,
        correct_abstention_rate=1.0,
        citation_rate=0.92,
        must_cite_rate=0.8,
        rojo_rate=0.2,
        avg_faithfulness=0.88,
        avg_latency_ms=1234.0,
    )
    m.details = [
        {
            "id": "trips-01",
            "is_trap": False,
            "abstained": False,
            "semaforo": "verde",
            "n_citations": 2,
            "faithfulness": 0.9,
            "must_cite_ok": True,
            "latency_ms": 1200,
        },
        {
            "id": "trampa-clima",
            "is_trap": True,
            "abstained": True,
            "semaforo": "amarillo",
            "n_citations": 0,
            "faithfulness": None,
            "must_cite_ok": True,
            "latency_ms": 80,
        },
    ]
    return m


def test_render_html_pass():
    html = render_html(_sample_metrics(), True, [], generated_at="2026-06-14")
    assert html.startswith("<!DOCTYPE html>")
    assert "AvoRAG" in html
    assert "GATE: PASA" in html
    assert "92.0%" in html  # citation_rate
    assert "trips-01" in html


def test_render_html_fail_lists_failures():
    html = render_html(_sample_metrics(), False, ["citation_rate 0.50 < 0.8"], generated_at="x")
    assert "GATE: FALLA" in html
    assert "citation_rate 0.50 &lt; 0.8" not in html  # no escapamos; se muestra crudo
    assert "citation_rate 0.50 < 0.8" in html


def test_render_html_handles_empty_details():
    m = EvalMetrics(n=0)
    html = render_html(m, True, [], generated_at="x")
    assert "sin detalle" in html
