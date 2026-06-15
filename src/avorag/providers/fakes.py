"""Proveedores fake deterministas para CI offline (LLM_PROVIDER=fake / EMBEDDING_PROVIDER=fake)."""

from __future__ import annotations

import hashlib

from avorag.config import get_settings
from avorag.providers.base import EmbeddingProvider, LLMProvider, RerankProvider


class FakeEmbedding(EmbeddingProvider):
    """Vectores deterministas por SHA-256 del texto."""

    name = "fake"

    def __init__(self) -> None:
        self.dim = get_settings().embedding_dim

    def _vec(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        return [h[i % len(h)] / 255.0 for i in range(self.dim)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FakeRerank(RerankProvider):
    """Conserva el orden de entrada con score 1/(i+1)."""

    name = "fake"

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        return [(i, 1.0 / (i + 1)) for i in range(len(docs))][:top_k]


class FakeLLM(LLMProvider):
    """LLM determinista: devuelve JSON de juez o respuesta corta citada según el system prompt."""

    name = "fake"

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        s = system.lower()
        if "faithful" in s:
            return '{"faithful": true, "score": 0.9, "unsupported": []}'
        if "seguro" in s or "categoria_i_ii" in s:
            return '{"seguro": true, "problemas": [], "categoria_I_II": false}'
        if "hechos esperados" in s or "faltantes" in s:
            return '{"score": 0.8, "faltantes": [], "contradichos": []}'
        if "sitúa fragmentos" in s or "contexto" in s and "una sola frase" in s:
            return "Contexto: fragmento sobre manejo del aguacate Hass."
        return "Según la fuente, se recomienda el manejo integrado del cultivo [1]."
