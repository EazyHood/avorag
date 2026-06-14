"""Implementaciones de RerankProvider: none, cohere, local (GPU)."""

from __future__ import annotations

from avorag.config import get_settings
from avorag.providers.base import RerankProvider


class NoRerank(RerankProvider):
    """Sin reranking: conserva el orden de la fusión (RRF). Default del MVP."""

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        return [(i, 1.0 / (i + 1)) for i in range(len(docs))][:top_k]


class CohereRerank(RerankProvider):
    """Reranking por API de Cohere (multilingüe)."""

    def __init__(self) -> None:
        import cohere

        s = get_settings()
        if not s.cohere_api_key:
            raise ValueError("COHERE_API_KEY vacío pero RERANK_PROVIDER=cohere")
        self._client = cohere.ClientV2(api_key=s.cohere_api_key)
        self._model = "rerank-v3.5"

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        if not docs:
            return []
        resp = self._client.rerank(
            model=self._model, query=query, documents=docs, top_n=min(top_k, len(docs))
        )
        return [(r.index, r.relevance_score) for r in resp.results]


class LocalRerank(RerankProvider):
    """Cross-encoder self-hosted vía sentence-transformers (compatible con transformers 5).

    Requiere `uv sync --extra local`. Auto-detecta GPU; en CPU corre igual de fiable
    (para reordenar pocos candidatos basta CPU, sin pelear con versiones de CUDA).
    """

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder  # import perezoso (pesado)

        s = get_settings()
        self._model = CrossEncoder(s.rerank_model)

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        if not docs:
            return []
        scores = self._model.predict([(query, d) for d in docs])
        ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
        return [(i, float(s)) for i, s in ranked[:top_k]]
