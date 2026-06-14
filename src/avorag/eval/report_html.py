"""Genera un dashboard HTML autocontenido a partir de las métricas de evaluación.

El HTML es el artefacto de portafolio: se abre en el navegador, se captura, y muestra
TUS números (fidelidad, citación, abstención, dosis-seguras) de forma presentable.
"""

from __future__ import annotations

from pathlib import Path

from avorag.eval.metrics import GATE_THRESHOLDS, EvalMetrics


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _card(label: str, value: str, *, good: bool | None = None) -> str:
    cls = "" if good is None else (" ok" if good else " bad")
    return f'<div class="card{cls}"><div class="v">{value}</div><div class="l">{label}</div></div>'


def _semaforo_badge(s: str) -> str:
    color = {"verde": "#1f9d55", "amarillo": "#d69e2e", "rojo": "#c53030"}.get(s, "#8b98a5")
    return f'<span class="pill" style="background:{color}22;color:{color}">{s}</span>'


def render_html(
    m: EvalMetrics,
    passed: bool,
    failures: list[str],
    *,
    generated_at: str = "",
    provider_info: dict | None = None,
) -> str:
    """Devuelve el HTML completo del reporte (autocontenido, sin dependencias externas)."""
    gate_cls = "pass" if passed else "fail"
    gate_txt = "✓ GATE: PASA" if passed else "✗ GATE: FALLA"
    fail_list = "".join(f"<li>{f}</li>" for f in failures) if failures else "<li>sin fallos</li>"

    cards = "".join(
        [
            _card("Preguntas", str(m.n)),
            _card("Reales / trampas", f"{m.n_real} / {m.n_traps}"),
            _card(
                "Citación (respondidas)",
                _pct(m.citation_rate),
                good=m.citation_rate >= GATE_THRESHOLDS["citation_rate"] if m.n_answered else None,
            ),
            _card(
                "Abstención correcta",
                _pct(m.correct_abstention_rate),
                good=m.correct_abstention_rate >= GATE_THRESHOLDS["correct_abstention_rate"]
                if m.n_traps
                else None,
            ),
            _card("Tasa de respuesta", _pct(m.answered_rate)),
            _card("must_cite cumplido", _pct(m.must_cite_rate)),
            _card(
                "Fidelidad media",
                "n/a" if m.avg_faithfulness is None else f"{m.avg_faithfulness:.2f}",
                good=m.avg_faithfulness >= GATE_THRESHOLDS["avg_faithfulness"]
                if m.avg_faithfulness is not None
                else None,
            ),
            _card("Tasa rojo (HITL)", _pct(m.rojo_rate)),
            _card("Latencia media", f"{m.avg_latency_ms:.0f} ms"),
        ]
    )

    rows = ""
    for d in m.details:
        faith = "—" if d.get("faithfulness") is None else f"{d['faithfulness']:.2f}"
        trap = "🪤" if d.get("is_trap") else ""
        abst = "✓" if d.get("abstained") else ""
        cite_ok = "✓" if d.get("must_cite_ok") else "✗"
        rows += (
            f"<tr><td>{d.get('id', '')} {trap}</td>"
            f"<td>{_semaforo_badge(str(d.get('semaforo', '')))}</td>"
            f"<td class='c'>{abst}</td>"
            f"<td class='c'>{d.get('n_citations', 0)}</td>"
            f"<td class='c'>{cite_ok}</td>"
            f"<td class='c'>{faith}</td>"
            f"<td class='c'>{d.get('latency_ms', 0)} ms</td></tr>"
        )

    prov = ""
    if provider_info:
        prov = " · ".join(f"{k}: {v}" for k, v in provider_info.items())

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AvoRAG — Reporte de evaluación</title>
<style>
:root{{--bg:#0f1419;--panel:#1a212b;--text:#e6edf3;--muted:#8b98a5;--line:#2a3441;--accent:#3fb950}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:28px}}
h1{{font-size:22px;margin:0 0 4px}}
.sub{{color:var(--muted);font-size:13px;margin-bottom:20px}}
.gate{{display:inline-block;font-weight:700;padding:8px 16px;border-radius:10px;margin-bottom:20px}}
.gate.pass{{background:rgba(31,157,85,.15);color:#1f9d55}}
.gate.fail{{background:rgba(197,48,48,.15);color:#c53030}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}}
.card.ok{{border-color:#1f9d5566}} .card.bad{{border-color:#c5303066}}
.card .v{{font-size:24px;font-weight:700}} .card .l{{color:var(--muted);font-size:12px;margin-top:4px}}
table{{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13px}}
th{{color:var(--muted);font-weight:600}} td.c{{text-align:center}}
.pill{{padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}}
ul.fail{{color:#c53030;font-size:13px}}
.foot{{color:var(--muted);font-size:12px;margin-top:24px}}
</style></head>
<body><div class="wrap">
<h1>🥑 AvoRAG — Reporte de evaluación</h1>
<div class="sub">Golden set · {generated_at}{(" · " + prov) if prov else ""}</div>
<div class="gate {gate_cls}">{gate_txt}</div>
{f'<ul class="fail">{fail_list}</ul>' if not passed else ""}
<div class="grid">{cards}</div>
<table><thead><tr><th>ID</th><th>Semáforo</th><th>Abst.</th><th>Citas</th><th>must_cite</th><th>Fidelidad</th><th>Latencia</th></tr></thead>
<tbody>{rows or '<tr><td colspan="7" class="c">sin detalle</td></tr>'}</tbody></table>
<div class="foot">Generado por AvoRAG. Las métricas son resultados propios medidos sobre el golden set; nunca se presentan cifras de terceros como propias.</div>
</div></body></html>"""


def write_html_report(
    m: EvalMetrics,
    passed: bool,
    failures: list[str],
    out_path: str | Path,
    *,
    generated_at: str = "",
    provider_info: dict | None = None,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_html(m, passed, failures, generated_at=generated_at, provider_info=provider_info),
        encoding="utf-8",
    )
    return out
