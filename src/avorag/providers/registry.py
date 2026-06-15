"""Fábrica de proveedores según la configuración. Instancias cacheadas."""

from __future__ import annotations

from functools import lru_cache

from avorag.config import get_settings
from avorag.providers.base import EmbeddingProvider, LLMProvider, RerankProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    p = get_settings().embedding_provider.lower()
    if p == "fake":
        from avorag.providers.fakes import FakeEmbedding

        return FakeEmbedding()
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
    if p == "fake":
        from avorag.providers.fakes import FakeLLM

        return FakeLLM()
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
def get_judge_llm_provider() -> LLMProvider:
    """Proveedor LLM para los JUECES (fidelidad/seguridad/corrección).

    Si `judge_llm_provider` está vacío, usa el MISMO que genera (autoevaluación correlacionada;
    cifra indicativa). Si se define uno distinto, da una segunda opinión independiente.
    """
    s = get_settings()
    p = (s.judge_llm_provider or s.llm_provider).lower()
    model = s.judge_llm_model or None
    if p == "fake":
        from avorag.providers.fakes import FakeLLM

        return FakeLLM()
    if p == "ollama":
        from avorag.providers.llm import OllamaLLM

        return OllamaLLM(model=model)
    if p == "anthropic":
        from avorag.providers.llm import AnthropicLLM

        return AnthropicLLM(model=model)
    if p == "openai":
        from avorag.providers.llm import OpenAILLM

        return OpenAILLM(model=model)
    raise ValueError(f"JUDGE_LLM_PROVIDER desconocido: {p!r}")


def judge_provider_label() -> str:
    """Etiqueta del juez para provider_info (transparencia: ¿se autoevalúa?)."""
    s = get_settings()
    p = s.judge_llm_provider or s.llm_provider
    m = s.judge_llm_model or {
        "ollama": s.llm_model,
        "anthropic": s.anthropic_model,
        "openai": s.openai_llm_model,
    }.get(p.lower(), s.llm_model)
    independent = bool(s.judge_llm_provider) and (
        s.judge_llm_provider.lower() != s.llm_provider.lower()
        or (s.judge_llm_model and s.judge_llm_model != s.llm_model)
    )
    return f"{p}:{m}{'' if independent else ' (autoevaluación)'}"


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
