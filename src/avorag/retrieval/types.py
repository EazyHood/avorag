"""Tipos de recuperación independientes de la capa de infraestructura.

`ScoredChunk` vive aquí (y no en `hybrid.py`) para que el DOMINIO puro —guardarraíles de
seguridad, semáforo, pipeline de razonamiento— pueda tiparse contra él SIN arrastrar
`avorag.db` (que al importarse construye un engine de Postgres). Romper ese acoplamiento
permite testear la lógica de seguridad sin una base de datos y mantener una frontera clara
entre dominio e infraestructura (regla sostenida por `tests/test_decoupling.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ChunkLike(Protocol):
    """Contrato mínimo de un fragmento recuperado que consume el dominio.

    Lo satisface estructuralmente el modelo ORM `avorag.db.Chunk`, pero el dominio solo
    depende de esta forma, no del ORM concreto.
    """

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
