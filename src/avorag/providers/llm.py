"""Implementaciones de LLMProvider: ollama (local), anthropic, openai."""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from avorag.config import get_settings
from avorag.providers.base import LLMProvider

_RETRY = retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=15))


class OllamaLLM(LLMProvider):
    """Generación con Ollama local."""

    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        from ollama import Client

        s = get_settings()
        self._client = Client(host=s.ollama_host)
        self._model = model or s.llm_model
        self._temperature = s.llm_temperature
        self._max_tokens = s.llm_max_tokens

    @_RETRY
    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        resp = self._client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={
                "temperature": self._temperature if temperature is None else temperature,
                "num_predict": self._max_tokens if max_tokens is None else max_tokens,
            },
        )
        return resp.message.content or ""


class AnthropicLLM(LLMProvider):
    """Generación con Claude (Anthropic)."""

    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        from anthropic import Anthropic

        s = get_settings()
        if not s.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY vacío pero LLM_PROVIDER=anthropic")
        self._client = Anthropic(api_key=s.anthropic_api_key)
        self._model = model or s.anthropic_model
        self._temperature = s.llm_temperature
        self._max_tokens = s.llm_max_tokens

    @_RETRY
    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            temperature=self._temperature if temperature is None else temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")


class OpenAILLM(LLMProvider):
    """Generación con un modelo de OpenAI."""

    name = "openai"

    def __init__(self, model: str | None = None) -> None:
        from openai import OpenAI

        s = get_settings()
        if not s.openai_api_key:
            raise ValueError("OPENAI_API_KEY vacío pero LLM_PROVIDER=openai")
        self._client = OpenAI(api_key=s.openai_api_key)
        self._model = model or s.openai_llm_model
        self._temperature = s.llm_temperature
        self._max_tokens = s.llm_max_tokens

    @_RETRY
    def complete(self, system, user, *, temperature=None, max_tokens=None) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=self._temperature if temperature is None else temperature,
            max_tokens=self._max_tokens if max_tokens is None else max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""
