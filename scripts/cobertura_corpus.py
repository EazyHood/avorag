"""Diagnóstico de COBERTURA del corpus: dónde AvoRAG responderá bien y dónde se abstendrá / sonará genérico.

Resuelve la parte accionable de la objeción #5 («cuando le pregunté de mi zona, soltó una generalidad»):
el bot es tan bueno como su corpus curado. Este reporte muestra QUÉ temas/plagas están bien cubiertos
y cuáles están delgados o vacíos, para que el agrónomo sepa exactamente dónde la herramienta es útil
(y dónde, honestamente, todavía no). El contenido lo cura el experto; esto mide el hueco.

Uso:
    uv run python scripts/cobertura_corpus.py [--tenant finca1] \
        [--plagas trips,antracnosis,monalonion,roña,ácaros,marceño]

HONESTIDAD — límite real: la metadata de chunk tiene `tema` y `plaga_objetivo`, pero NO un campo de
REGIÓN/ZONA. Por eso la cobertura se mide por TEMA/PLAGA, no por zona agroclimática. Para que el bot
sea específico por zona (lo que pide el comprador) hay que (a) añadir un campo `region`/`zona` a
ChunkMetadata y (b) curar corpus por zona. Este reporte lo señala; el contenido regional es trabajo del
agrónomo (es el foso del producto, no algo que el software invente).
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DEFAULT_PLAGAS = "trips,antracnosis,monalonion,roña,ácaros,marceño,lenticelosis"


def _norm(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (s or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _bar(n: int, total: int, width: int = 24) -> str:
    fill = round(width * n / total) if total else 0
    return "█" * fill + "·" * (width - fill)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Cobertura del corpus por tema/plaga (dónde abstiene el bot)."
    )
    ap.add_argument("--tenant", default=None)
    ap.add_argument(
        "--plagas", default=_DEFAULT_PLAGAS, help="Plagas prioritarias a comprobar (coma)."
    )
    args = ap.parse_args()

    from sqlalchemy import select

    from avorag.config import get_settings
    from avorag.db import get_session
    from avorag.db.models import Chunk
    from avorag.logging import configure_logging

    configure_logging()

    # RLS fail-closed: el acceso a datos requiere tenant; sin --tenant, usa el tenant por defecto.
    tenant = args.tenant or get_settings().default_tenant
    with get_session(tenant=tenant) as s:
        stmt = select(Chunk).where(Chunk.tenant == tenant)
        chunks = list(s.scalars(stmt))

    if not chunks:
        print("Corpus vacío (sin chunks). Ingiere documentos con `avorag ingest`.")
        return

    total = len(chunks)
    temas = Counter((c.meta or {}).get("tema") or "(sin tema)" for c in chunks)
    autoridad = Counter((c.meta or {}).get("nivel_autoridad") or "(?)" for c in chunks)
    vigencia = Counter((c.meta or {}).get("vigencia") or "(?)" for c in chunks)
    contenidos = [_norm((c.context or "") + " " + c.content) for c in chunks]
    plaga_meta = [_norm((c.meta or {}).get("plaga_objetivo") or "") for c in chunks]

    print(
        f"\n=== Cobertura del corpus ({'tenant ' + args.tenant if args.tenant else 'todos'}) — {total} fragmentos ==="
    )

    print("\nPor TEMA:")
    for tema, n in temas.most_common():
        print(f"  {tema:<16}{n:>5}  {_bar(n, total)}")

    print("\nPor NIVEL DE AUTORIDAD de la fuente:")
    for a, n in autoridad.most_common():
        print(f"  {a:<20}{n:>5}  {_bar(n, total)}")

    print("\nVIGENCIA (¿datos caducados?):")
    for v, n in vigencia.most_common():
        print(f"  {v:<16}{n:>5}")

    print("\nPLAGAS PRIORITARIAS — fragmentos que las respaldan (0 = el bot se abstendrá):")
    for raw in [p.strip() for p in args.plagas.split(",") if p.strip()]:
        key = _norm(raw)
        n = sum(1 for i in range(total) if key in plaga_meta[i] or key in contenidos[i])
        flag = "  ⚠️ SIN cobertura" if n == 0 else ("  ⚠️ delgado" if n < 5 else "")
        print(f"  {raw:<16}{n:>5}  {_bar(n, total)}{flag}")

    print(
        "\nNOTA honesta: cobertura por TEMA/PLAGA, no por ZONA agroclimática (falta un campo `region`"
    )
    print(
        "en la metadata + curar corpus por zona). Donde un tema sale 0/delgado, el bot se abstiene o"
    )
    print(
        "generaliza: ahí NO es útil todavía. Eso se cierra curando corpus (trabajo del agrónomo), no código."
    )


if __name__ == "__main__":
    main()
