"""Siembra las NORMAS versionadas de las calculadoras en `norm_tables` (modo online).

Uso:
    python scripts/seed_norms.py

`norm_tables` es GLOBAL (sin RLS) → sesión de SISTEMA. Idempotente (no duplica por norm_key+version).
Las calculadoras seguirán usando sus defaults hasta que se las cablee a `online.norms.get_norm`.
"""

from __future__ import annotations


def main() -> None:
    from avorag.db import get_session
    from avorag.logging import configure_logging
    from avorag.online.norms import seed_norms

    configure_logging()
    with get_session(system=True) as session:  # tabla global, sin tenant
        n = seed_norms(session)
    print(f"Normas sembradas: {n}")


if __name__ == "__main__":
    main()
