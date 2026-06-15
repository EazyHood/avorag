"""Blindaje arquitectónico: el DOMINIO puro no debe arrastrar la capa de BD.

Importar los guardarraíles de seguridad (o los esquemas) NO debe construir un engine de
Postgres ni importar `avorag.db.engine`. Esto mantiene la lógica de seguridad testeable sin
base de datos y evita que un `import` accidental abra conexiones a producción. Si esta
prueba se rompe, alguien volvió a acoplar infraestructura al dominio (ver Ola 1 de la
auditoría / `src/avorag/retrieval/types.py`).
"""

from __future__ import annotations

import subprocess
import sys

# Módulos de dominio que deben poder importarse SIN tocar la BD.
_PURE_DOMAIN = ["avorag.rag.guardrails", "avorag.rag.schemas", "avorag.rag.prompt"]


def test_domain_import_does_not_load_db_engine() -> None:
    code = (
        "import importlib, sys\n"
        f"for m in {_PURE_DOMAIN!r}:\n"
        "    importlib.import_module(m)\n"
        "leaked = [m for m in ('avorag.db.engine', 'avorag.db') if m in sys.modules]\n"
        "assert not leaked, f'el dominio arrastró la BD: {leaked}'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"importar el dominio cargó la capa de BD.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
