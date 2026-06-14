"""Fábrica de proveedores según la configuración. Instancias cacheadas."""

from __future__ import annotations

from functools import lru_cache

from avorag.config import get_settings
from avorag.providers.base import EmbeddingProvider, LLMProvider, RerankProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    p = get_settings().embedding_provider.lower()
    if p == "ollama":
        from avorag.providers.embeddings import OllamaEmbedding

        return OllamaEmbedding()
    if p == "openai":
        from avorag.providers.embeddings import OpenAIEmbedding

        return OpenAIEmbedding()
    if p == "local":
        from avorag.providers.embeddings import LocalEmbedding

        return LocalEmbedding()
    raise ValueError(f"EMBEDDING_PROVIDER desconocido: {p!r}")


@lru_cache
def get_llm_provider() -> LLMProvider:
    p = get_settings().llm_provider.lower()
    if p == "ollama":
        from avorag.providers.llm import OllamaLLM

        return OllamaLLM()
    if p == "anthropic":
        from avorag.providers.llm import AnthropicLLM

        return AnthropicLLM()
    if p == "openai":
        from avorag.providers.llm import OpenAILLM

        return OpenAILLM()
    raise ValueError(f"LLM_PROVIDER desconocido: {p!r}")


@lru_cache
def get_rerank_provider() -> RerankProvider:
    p = get_settings().rerank_provider.lower()
    if p in ("none", "", "off"):
        from avorag.providers.rerank import NoRerank

        return NoRerank()
    if p == "cohere":
        from avorag.providers.rerank import CohereRerank

        return CohereRerank()
    if p == "local":
        from avorag.providers.rerank import LocalRerank

        return LocalRerank()
    raise ValueError(f"RERANK_PROVIDER desconocido: {p!r}")
