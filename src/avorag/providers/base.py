"""Interfaces de proveedores. Permiten cambiar LLM/embeddings/reranker por configuración."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator


class EmbeddingProvider(ABC):
    """`dim` debe coincidir con EMBEDDING_DIM."""

    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class RerankProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        """Devuelve [(índice_original, score)] ordenado desc."""


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...

    def stream(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        """Genera por trozos. Por defecto emite la respuesta completa de una vez."""
        yield self.complete(system, user, temperature=temperature, max_tokens=max_tokens)
