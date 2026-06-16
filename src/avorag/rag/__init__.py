"""Núcleo RAG: prompt, guardarraíles y orquestación.

Esquemas reexportados eager; `answer()` se carga lazy para no arrastrar avorag.db al importar.
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
    from avorag.rag.pipeline import answer, answer_stream

__all__ = [
    "AbstentionType",
    "Answer",
    "Citation",
    "RetrievedContext",
    "Semaforo",
    "answer",
    "answer_stream",
]


def __getattr__(name: str) -> Any:
    if name in ("answer", "answer_stream"):
        from avorag.rag import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
