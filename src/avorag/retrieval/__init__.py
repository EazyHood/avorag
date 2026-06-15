"""Recuperación híbrida y reranking.

`ScoredChunk` se reexporta de forma EAGER (no depende de la BD). Las funciones que sí
tocan la BD/proveedores (`hybrid_search`, `reciprocal_rank_fusion`, `rerank_chunks`) se
cargan de forma PEREZOSA vía `__getattr__`: así importar `avorag.retrieval.types` (o
`ScoredChunk`) desde el dominio no arrastra `avorag.db`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avorag.retrieval.types import ChunkLike, ScoredChunk

if TYPE_CHECKING:
    from avorag.retrieval.hybrid import hybrid_search, reciprocal_rank_fusion
    from avorag.retrieval.rerank import rerank_chunks

__all__ = [
    "ChunkLike",
    "ScoredChunk",
    "hybrid_search",
    "reciprocal_rank_fusion",
    "rerank_chunks",
]


def __getattr__(name: str) -> Any:
    if name in ("hybrid_search", "reciprocal_rank_fusion"):
        from avorag.retrieval import hybrid

        return getattr(hybrid, name)
    if name == "rerank_chunks":
        from avorag.retrieval.rerank import rerank_chunks

        return rerank_chunks
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
