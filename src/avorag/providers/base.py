"""Interfaces de proveedores. Permiten cambiar LLM/embeddings/reranker por configuración."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Genera vectores. `dim` debe coincidir con EMBEDDING_DIM."""

    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embebe varios textos (para ingesta)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embebe una consulta."""


class RerankProvider(ABC):
    """Reordena documentos por relevancia frente a una consulta."""

    @abstractmethod
    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        """Devuelve [(índice_original, score)] ordenado desc, recortado a top_k."""


class LLMProvider(ABC):
    """Genera texto a partir de un prompt de sistema + usuario."""

    name: str

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Devuelve la respuesta del modelo como texto."""
