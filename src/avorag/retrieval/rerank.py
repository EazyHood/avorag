"""Reranking de candidatos con el proveedor configurado (none/cohere/local)."""

from __future__ import annotations

from avorag.config import get_settings
from avorag.logging import get_logger
from avorag.providers import get_rerank_provider
from avorag.retrieval.types import ScoredChunk

log = get_logger(__name__)


def rerank_chunks(
    query: str, candidates: list[ScoredChunk], *, final_k: int | None = None
) -> list[ScoredChunk]:
    """Reordena los candidatos y recorta a final_k. Con RERANK_PROVIDER=none, conserva el orden RRF.

    Es TOLERANTE A FALLO: si el reranker (modelo local o API) lanza, se DEGRADA al orden RRF en
    vez de tumbar la consulta — misma filosofía que la búsqueda léxica y la auditoría.
    """
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
    try:
        ranking = provider.rerank(query, docs, final_k)
    except Exception as exc:  # degradación a orden RRF, nunca romper la consulta
        log.warning("rerank_failed_degrading_to_rrf", error=str(exc))
        return candidates[:final_k]

    out: list[ScoredChunk] = []
    for original_index, score in ranking:
        sc = candidates[original_index]
        out.append(
            ScoredChunk(
                chunk=sc.chunk, score=score, dense_rank=sc.dense_rank, lexical_rank=sc.lexical_rank
            )
        )
    return out
