"""Reporte de RETENCIÓN real (no descargas) desde la auditoría de consultas (`queries`).

Resuelve la parte medible de la objeción #4 («no me muestres descargas, muéstrame cuánta gente lo
sigue usando en la segunda temporada»). Mide uso sostenido y recurrencia, no vanidad.

Uso:
    uv run python scripts/retention_report.py [--tenant finca1] [--weeks 12]

Métricas (sobre la tabla `queries`):
  - Consultas totales y rango de fechas.
  - Por semana: nº de consultas y de tenants activos.
  - Retención tenant semana-a-semana: % de tenants activos que también lo fueron la semana anterior.
  - Ratio de preguntas repetidas (misma pregunta normalizada ya vista) = señal de uso recurrente.
  - % de abstención y de respuestas con cita (calidad del uso).

HONESTIDAD — límite real: `queries` tiene `tenant` pero NO un id de PRODUCTOR/usuario final. Por eso la
retención se mide a nivel de TENANT (exportadora), no por productor individual. Para medir retención
por productor (lo que de verdad pide el comprador) hay que añadir un campo `user_ref` (p.ej. el número
de WhatsApp hasheado) a `QueryLog`. Este reporte lo señala y, si algún día existe ese campo, se extiende.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _norm_q(q: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (q or "").lower().strip())
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).split())


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reporte de retención desde la auditoría de consultas."
    )
    ap.add_argument(
        "--tenant", default=None, help="Tenant a reportar (por defecto, el configurado)."
    )
    ap.add_argument("--weeks", type=int, default=12, help="Semanas recientes a mostrar.")
    args = ap.parse_args()

    from sqlalchemy import select

    from avorag.config import get_settings
    from avorag.db import get_session
    from avorag.db.models import QueryLog
    from avorag.logging import configure_logging

    configure_logging()

    # RLS fail-closed: el acceso a datos requiere tenant; sin --tenant, usa el tenant por defecto.
    tenant = args.tenant or get_settings().default_tenant
    with get_session(tenant=tenant) as s:
        stmt = select(QueryLog).where(QueryLog.tenant == tenant)
        rows = list(s.scalars(stmt))

    if not rows:
        print("Sin consultas registradas todavía.")
        return

    rows.sort(key=lambda r: r.created_at)
    total = len(rows)
    abst = sum(1 for r in rows if r.abstained)
    con_cita = sum(1 for r in rows if r.citations)

    # Agrupar por semana ISO.
    by_week_count: dict[tuple, int] = defaultdict(int)
    by_week_tenants: dict[tuple, set] = defaultdict(set)
    for r in rows:
        wk = r.created_at.isocalendar()[:2]  # (año, semana)
        by_week_count[wk] += 1
        by_week_tenants[wk].add(r.tenant)
    weeks = sorted(by_week_count)

    # Retención tenant semana-a-semana.
    ret_lines = []
    for prev, cur in zip(weeks, weeks[1:], strict=False):
        a_prev, a_cur = by_week_tenants[prev], by_week_tenants[cur]
        retenidos = len(a_prev & a_cur)
        pct = retenidos / len(a_prev) if a_prev else 0.0
        ret_lines.append((cur, len(a_cur), retenidos, pct))

    # Recurrencia: preguntas repetidas.
    seen: set[str] = set()
    repetidas = 0
    for r in rows:
        k = _norm_q(r.question)
        if k in seen:
            repetidas += 1
        seen.add(k)
    ratio_rep = repetidas / total if total else 0.0

    print(
        f"\n=== Retención AvoRAG ({'tenant ' + args.tenant if args.tenant else 'todos los tenants'}) ==="
    )
    print(
        f"Consultas totales: {total} | desde {rows[0].created_at:%Y-%m-%d} hasta {rows[-1].created_at:%Y-%m-%d}"
    )
    print(
        f"Abstención: {abst / total:.0%} | con cita: {con_cita / total:.0%} | preguntas repetidas: {ratio_rep:.0%}"
    )
    print(f"\nPor semana (últimas {args.weeks}):")
    print(f"  {'semana':<12}{'consultas':>10}{'tenants':>9}")
    for wk in weeks[-args.weeks :]:
        print(f"  {wk[0]}-W{wk[1]:<8}{by_week_count[wk]:>10}{len(by_week_tenants[wk]):>9}")
    if ret_lines:
        print(
            "\nRetención de tenants semana-a-semana (activos que ya lo estaban la semana previa):"
        )
        for cur, n_cur, ret, pct in ret_lines[-args.weeks :]:
            print(
                f"  {cur[0]}-W{cur[1]:<8} activos {n_cur:>3} | retenidos {ret:>3} | retención {pct:.0%}"
            )
    print(
        "\nNOTA: retención a nivel de TENANT (no por productor): `queries` no guarda id de usuario."
    )
    print("Para retención por productor, añadir `user_ref` (p.ej. teléfono hasheado) a QueryLog.")


if __name__ == "__main__":
    main()
