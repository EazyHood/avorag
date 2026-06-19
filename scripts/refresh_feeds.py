"""Refresca los FEEDS EN VIVO del modo online (entrypoint de cron).

Uso:
    python scripts/refresh_feeds.py [--mode fake|real]

`feed_snapshots` es GLOBAL (sin RLS) → se usa una sesión de SISTEMA. El upsert es idempotente por
sha256, así que correrlo de más no duplica. Resiliente: un feed que falla no detiene el ciclo.
Activar el guardarraíl que los consume con AVORAG_ONLINE_FEEDS=1 en el servidor.
"""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresca los feeds en vivo de AvoRAG (modo online).")
    ap.add_argument("--mode", default="fake", choices=["fake", "real"], help="Proveedores a usar.")
    args = ap.parse_args()

    from avorag.db import get_session
    from avorag.logging import configure_logging
    from avorag.online.worker import refresh_all_feeds

    configure_logging()
    with get_session(system=True) as session:  # tabla global, sin tenant
        snaps = refresh_all_feeds(session, mode=args.mode)
    print(f"Feeds refrescados ({args.mode}): {len(snaps)}")


if __name__ == "__main__":
    main()
