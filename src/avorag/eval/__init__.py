"""Evaluación: golden set, métricas, gate y dashboard HTML."""

from avorag.eval.golden_set import GoldenItem, load_golden
from avorag.eval.metrics import EvalMetrics, compute_metrics, gate
from avorag.eval.report_html import render_html, write_html_report
from avorag.eval.run_eval import run_eval

__all__ = [
    "EvalMetrics",
    "GoldenItem",
    "compute_metrics",
    "gate",
    "load_golden",
    "render_html",
    "run_eval",
    "write_html_report",
]
