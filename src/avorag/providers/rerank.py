"""Implementaciones de RerankProvider: none, cohere, local (GPU)."""

from __future__ import annotations

from avorag.config import get_settings
from avorag.providers.base import RerankProvider


class NoRerank(RerankProvider):
    """Sin reranking; conserva el orden de la fusión RRF."""

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
    """Cross-encoder self-hosted vía sentence-transformers. Requiere `uv sync --extra local`.

    Usa GPU + fp16 si hay CUDA disponible (en CPU tarda ~12 s; en GPU ~20 ms)."""

    def __init__(self) -> None:
        import threading

        import torch  # import diferido (pesado)
        from sentence_transformers import CrossEncoder

        s = get_settings()
        if torch.cuda.is_available():
            self._model = CrossEncoder(
                s.rerank_model, device="cuda", model_kwargs={"torch_dtype": torch.float16}
            )
        else:
            self._model = CrossEncoder(s.rerank_model)
        # La inferencia en GPU no es thread-safe; serializa el precálculo de fondo con las peticiones.
        self._lock = threading.Lock()

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        if not docs:
            return []
        with self._lock:
            scores = self._model.predict([(query, d) for d in docs])
        ranked = sorted(enumerate(scores), key=lambda x: float(x[1]), reverse=True)
        return [(i, float(s)) for i, s in ranked[:top_k]]
