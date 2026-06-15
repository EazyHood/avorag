"""Recuperación híbrida: denso (pgvector) + léxico (Postgres FTS español) → RRF.

La búsqueda híbrida es indispensable en este dominio: lo denso captura el
significado, y lo léxico acierta en SKUs, números de registro ICA y dosis exactas.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avorag.config import get_settings
from avorag.db import Chunk
from avorag.logging import get_logger
from avorag.retrieval.types import ScoredChunk

log = get_logger(__name__)


def _base_filters(tenant: str, country: str | None):
    filters = [Chunk.tenant == tenant]
    if country:
        filters.append(Chunk.meta["pais"].astext == country)
    # Excluir explícitamente lo marcado como caducado.
    filters.append(Chunk.meta["vigencia"].astext != "caducado")
    return filters


def dense_search(
    session: Session, query_embedding: list[float], *, tenant: str, country: str | None, top_k: int
) -> list[str]:
    stmt = (
        select(Chunk.id)
        .where(*_base_filters(tenant, country))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    return [str(cid) for cid in session.scalars(stmt)]


def lexical_search(
    session: Session, query_text: str, *, tenant: str, country: str | None, top_k: int
) -> list[str]:
    tsq = func.websearch_to_tsquery("spanish", query_text)
    stmt = (
        select(Chunk.id)
        .where(*_base_filters(tenant, country), Chunk.content_tsv.op("@@")(tsq))
        .order_by(func.ts_rank(Chunk.content_tsv, tsq).desc())
        .limit(top_k)
    )
    try:
        return [str(cid) for cid in session.scalars(stmt)]
    except Exception as exc:
        # Una query léxica malformada no debe tumbar la búsqueda: caemos al lado denso.
        session.rollback()
        log.warning("lexical_search_failed", error=str(exc))
        return []


def reciprocal_rank_fusion(ranked_lists: list[list[str]], *, k: int) -> list[tuple[str, float]]:
    """Fusiona varias listas ordenadas por RRF: score = Σ 1/(k + rank)."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def hybrid_search(
    session: Session,
    query_text: str,
    query_embedding: list[float],
    *,
    tenant: str,
    country: str | None = None,
    top_k: int | None = None,
) -> list[ScoredChunk]:
    """Devuelve candidatos fusionados (denso + léxico), ya cargados como Chunk."""
    settings = get_settings()
    top_k = top_k or settings.retrieval_top_k

    dense_ids = dense_search(session, query_embedding, tenant=tenant, country=country, top_k=top_k)
    lexical_ids = lexical_search(session, query_text, tenant=tenant, country=country, top_k=top_k)

    dense_rank = {cid: i for i, cid in enumerate(dense_ids)}
    lexical_rank = {cid: i for i, cid in enumerate(lexical_ids)}

    fused = reciprocal_rank_fusion([dense_ids, lexical_ids], k=settings.rrf_k)[:top_k]
    if not fused:
        return []

    ids = [cid for cid, _ in fused]
    chunks = {str(c.id): c for c in session.scalars(select(Chunk).where(Chunk.id.in_(ids)))}

    out: list[ScoredChunk] = []
    for cid, score in fused:
        chunk = chunks.get(cid)
        if chunk is None:
            continue
        out.append(
            ScoredChunk(
                chunk=chunk,
                score=score,
                dense_rank=dense_rank.get(cid),
                lexical_rank=lexical_rank.get(cid),
            )
        )
    return out
