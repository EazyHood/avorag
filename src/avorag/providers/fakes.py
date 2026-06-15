"""Proveedores FAKE deterministas (amplifica la fortaleza #27).

Permiten ejecutar el pipeline `answer()` y los jueces SIN Ollama ni claves de API: habilitan
tests end-to-end de la orquestación en CI (sin GPU/red) y un modo demo offline. Se seleccionan
con LLM_PROVIDER=fake / EMBEDDING_PROVIDER=fake. No son inteligentes: producen salidas fijas y
reproducibles, suficientes para ejercitar el flujo (intención → recuperación → prompt → juez →
guardarraíl → semáforo).
"""

from __future__ import annotations

import hashlib

from avorag.config import get_settings
from avorag.providers.base import EmbeddingProvider, LLMProvider, RerankProvider


class FakeEmbedding(EmbeddingProvider):
    """Vectores deterministas derivados del hash del texto (misma entrada → mismo vector)."""

    name = "fake"

    def __init__(self) -> None:
        self.dim = get_settings().embedding_dim

    def _vec(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Repite el hash hasta cubrir dim; valores en [0,1). Determinista y barato.
        return [h[i % len(h)] / 255.0 for i in range(self.dim)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class FakeRerank(RerankProvider):
    """No reordena: conserva el orden de entrada con score 1/(i+1)."""

    name = "fake"

    def rerank(self, query: str, docs: list[str], top_k: int) -> list[tuple[int, float]]:
        return [(i, 1.0 / (i + 1)) for i in range(len(docs))][:top_k]


class FakeLLM(LLMProvider):
    """LLM determinista. Detecta por el prompt de sistema si actúa como JUEZ (devuelve JSON) o
    como GENERADOR (devuelve una respuesta corta con una cita [1])."""

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
        if "faithful" in s:  # juez de fidelidad
            return '{"faithful": true, "score": 0.9, "unsupported": []}'
        if "seguro" in s or "categoria_i_ii" in s:  # juez de seguridad de dosis
            return '{"seguro": true, "problemas": [], "categoria_I_II": false}'
        if "hechos esperados" in s or "faltantes" in s:  # juez de corrección
            return '{"score": 0.8, "faltantes": [], "contradichos": []}'
        if "sitúa fragmentos" in s or "contexto" in s and "una sola frase" in s:  # contextual
            return "Contexto: fragmento sobre manejo del aguacate Hass."
        # Generación: respuesta breve y citada (apta para el guardarraíl de citación).
        return "Según la fuente, se recomienda el manejo integrado del cultivo [1]."
