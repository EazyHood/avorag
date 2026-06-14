"""Reranking de candidatos con el proveedor configurado (none/cohere/local)."""

from __future__ import annotations

from avorag.config import get_settings
from avorag.providers import get_rerank_provider
from avorag.retrieval.hybrid import ScoredChunk


def rerank_chunks(
    query: str, candidates: list[ScoredChunk], *, final_k: int | None = None
) -> list[ScoredChunk]:
    """Reordena los candidatos y recorta a final_k. Con RERANK_PROVIDER=none, conserva el orden RRF."""
    settings = get_settings()
    final_k = final_k or settings.final_top_k
    if not candidates:
        return []

    provider = get_rerank_provider()
    # El reranker ve el contenido enriquecido (contexto + texto), igual que el índice.
    # Se trunca a rerank_max_chars: el cross-encoder en CPU es mucho más rápido con secuencias
    # cortas y la relevancia se decide casi siempre en el inicio del fragmento.
    maxc = settings.rerank_max_chars
    docs = [
        (((c.chunk.context + "\n") if c.chunk.context else "") + c.chunk.content)[:maxc]
        for c in candidates
    ]
    ranking = provider.rerank(query, docs, final_k)

    out: list[ScoredChunk] = []
    for original_index, score in ranking:
        sc = candidates[original_index]
        out.append(
            ScoredChunk(
                chunk=sc.chunk, score=score, dense_rank=sc.dense_rank, lexical_rank=sc.lexical_rank
            )
        )
    return out
