"""Implementaciones de EmbeddingProvider: ollama (local), openai, local (GPU)."""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from avorag.config import get_settings
from avorag.providers.base import EmbeddingProvider

_RETRY = retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=20))


class OllamaEmbedding(EmbeddingProvider):
    """Embeddings vía Ollama local. Requiere `ollama pull <modelo>`."""

    def __init__(self) -> None:
        from ollama import Client

        s = get_settings()
        self._client = Client(host=s.ollama_host)
        self._model = s.embedding_model
        self.dim = s.embedding_dim

    @_RETRY
    def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embed(model=self._model, input=texts)
        return [list(v) for v in resp.embeddings]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


class OpenAIEmbedding(EmbeddingProvider):
    """Embeddings vía API de OpenAI."""

    def __init__(self) -> None:
        from openai import OpenAI

        s = get_settings()
        if not s.openai_api_key:
            raise ValueError("OPENAI_API_KEY vacío pero EMBEDDING_PROVIDER=openai")
        self._client = OpenAI(api_key=s.openai_api_key)
        self._model = (
            s.embedding_model if s.embedding_model.startswith("text-") else "text-embedding-3-small"
        )
        self.dim = s.embedding_dim

    @_RETRY
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class LocalEmbedding(EmbeddingProvider):
    """Embeddings self-hosted vía sentence-transformers. Requiere `uv sync --extra local`."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # import diferido (pesado)

        s = get_settings()
        model_name = s.embedding_model if "/" in s.embedding_model else "BAAI/bge-m3"
        self._model = SentenceTransformer(model_name, device=_pick_device())
        self.dim = s.embedding_dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def _pick_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"
