"""Blindaje arquitectónico: el DOMINIO puro no debe arrastrar la capa de BD.

Importar los guardarraíles de seguridad (o los esquemas) NO debe construir un engine de
Postgres ni importar `avorag.db.engine`. Esto mantiene la lógica de seguridad testeable sin
base de datos y evita que un `import` accidental abra conexiones a producción. Si esta
prueba se rompe, alguien volvió a acoplar infraestructura al dominio (ver Ola 1 de la
auditoría / `src/avorag/retrieval/types.py`).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# Módulos de dominio que deben poder importarse SIN tocar la BD.
_PURE_DOMAIN = ["avorag.rag.guardrails", "avorag.rag.schemas", "avorag.rag.prompt"]

_SRC = Path(__file__).resolve().parents[1] / "src" / "avorag"


def _imported_modules(path: Path) -> set[str]:
    """Módulos importados por un archivo, leyendo su AST (sin ejecutarlo)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def test_domain_modules_do_not_import_db_statically() -> None:
    # Contrato de capas: el dominio puro NO importa la capa de infraestructura.
    for rel in (
        "rag/guardrails.py",
        "rag/prompt.py",
        "rag/schemas.py",
        "retrieval/types.py",
        "agro_terms.py",
    ):
        mods = _imported_modules(_SRC / rel)
        assert not any(m.startswith("avorag.db") for m in mods), f"{rel} importa avorag.db"
        assert not any(
            m.startswith(
                ("avorag.providers.embeddings", "avorag.providers.llm", "avorag.providers.rerank")
            )
            for m in mods
        ), f"{rel} importa una implementación concreta de proveedor (red)"


def test_routes_chat_uses_only_rag_layer() -> None:
    # La API de chat habla con el dominio (avorag.rag), no con la BD/recuperación directamente.
    mods = _imported_modules(_SRC / "api" / "routes_chat.py")
    forbidden = [
        m for m in mods if m.startswith(("avorag.db", "avorag.retrieval", "avorag.ingestion"))
    ]
    assert not forbidden, f"routes_chat importa capas internas: {forbidden}"


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
