"""Tipos de recuperación desacoplados de la BD (permite testear el dominio sin Postgres)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ChunkLike(Protocol):
    """Contrato mínimo de un fragmento recuperado. Lo satisface avorag.db.Chunk."""

    id: Any
    content: str
    context: str | None
    pagina: int | None
    meta: dict


@dataclass
class ScoredChunk:
    """Un fragmento recuperado con su puntaje de relevancia y rangos por canal."""

    chunk: ChunkLike
    score: float
    dense_rank: int | None = None
    lexical_rank: int | None = None
