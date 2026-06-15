"""Capa de base de datos.

Se exportan las FUNCIONES perezosas (`get_engine`, `get_session_factory`, `get_session`):
importar `avorag.db` no construye el engine. `engine` y `SessionLocal` siguen disponibles por
compatibilidad, materializados al primer acceso vía `__getattr__`.
"""

from __future__ import annotations

from typing import Any

from avorag.db.engine import get_engine, get_session, get_session_factory
from avorag.db.models import Base, Chunk, Document, QueryLog

__all__ = [
    "Base",
    "Chunk",
    "Document",
    "QueryLog",
    "get_engine",
    "get_session",
    "get_session_factory",
]


def __getattr__(name: str) -> Any:
    if name in ("engine", "SessionLocal"):
        from avorag.db import engine as _engine_mod

        return getattr(_engine_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
