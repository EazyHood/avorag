"""Corre el golden set contra el pipeline y reporta métricas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from avorag.eval.golden_set import load_golden
from avorag.eval.metrics import EvalMetrics, compute_metrics, gate
from avorag.eval.report_html import write_html_report
from avorag.rag import answer

console = Console()


def run_eval(
    golden_path: str | Path,
    *,
    tenant: str | None = None,
    report_dir: str | Path = "eval/reports",
) -> tuple[EvalMetrics, bool]:
    items = load_golden(golden_path)
    console.print(f"[bold]Evaluando {len(items)} preguntas del golden set…[/bold]")

    pairs = []
    for item in items:
        ans = answer(item.question, tenant=tenant)
        pairs.append((item, ans))
        mark = "🟢" if not ans.abstained else "⚪"
        console.print(f"  {mark} [{item.id}] {item.question[:60]}… → {ans.semaforo.value}")

    metrics = compute_metrics(pairs)
    passed, failures = gate(metrics)
    _print_report(metrics, passed, failures)

    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / "last_report.json"
    out.write_text(
        json.dumps(
            {"metrics": metrics.as_dict(), "passed": passed, "failures": failures},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # Dashboard HTML (artefacto de portafolio).
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    provider_info = pairs[0][1].provider_info if pairs else None
    html_out = write_html_report(
        metrics,
        passed,
        failures,
        report_dir / "report.html",
        generated_at=stamp,
        provider_info=provider_info,
    )
    console.print(f"\nReporte JSON: [cyan]{out}[/cyan]")
    console.print(f"Dashboard HTML: [cyan]{html_out}[/cyan]  (ábrelo en el navegador)")
    return metrics, passed


def _print_report(m: EvalMetrics, passed: bool, failures: list[str]) -> None:
    t = Table(title="Métricas de evaluación AvoRAG")
    t.add_column("Métrica")
    t.add_column("Valor", justify="right")
    t.add_row("Preguntas", str(m.n))
    t.add_row("Reales / trampas", f"{m.n_real} / {m.n_traps}")
    t.add_row("Tasa de respuesta (reales)", f"{m.answered_rate:.2%}")
    t.add_row("Abstención correcta (trampas)", f"{m.correct_abstention_rate:.2%}")
    t.add_row("Citación (respondidas)", f"{m.citation_rate:.2%}")
    t.add_row("must_cite cumplido", f"{m.must_cite_rate:.2%}")
    t.add_row("Tasa rojo (HITL)", f"{m.rojo_rate:.2%}")
    t.add_row(
        "Fidelidad media", f"{m.avg_faithfulness:.2f}" if m.avg_faithfulness is not None else "n/a"
    )
    t.add_row("Latencia media", f"{m.avg_latency_ms:.0f} ms")
    console.print(t)
    if passed:
        console.print("[bold green]✓ GATE: PASA[/bold green]")
    else:
        console.print("[bold red]✗ GATE: FALLA[/bold red]")
        for f in failures:
            console.print(f"  [red]- {f}[/red]")
