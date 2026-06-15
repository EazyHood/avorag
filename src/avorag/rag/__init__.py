"""Núcleo RAG: prompt, guardarraíles y orquestación.

Los esquemas (sin dependencia de BD) se reexportan EAGER. `answer()` —que arrastra el
pipeline completo y, con él, `avorag.db`— se carga PEREZOSAMENTE para que importar los
guardarraíles o los esquemas no construya un engine de Postgres.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avorag.rag.schemas import (
    AbstentionType,
    Answer,
    Citation,
    RetrievedContext,
    Semaforo,
)

if TYPE_CHECKING:
    from avorag.rag.pipeline import answer

__all__ = [
    "AbstentionType",
    "Answer",
    "Citation",
    "RetrievedContext",
    "Semaforo",
    "answer",
]


def __getattr__(name: str) -> Any:
    if name == "answer":
        from avorag.rag.pipeline import answer

        return answer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
