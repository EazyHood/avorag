"""Capa de base de datos (construcción perezosa del engine)."""

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
