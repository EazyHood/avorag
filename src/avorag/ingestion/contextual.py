"""Contextual Retrieval (Anthropic): antepone a cada chunk un contexto breve
generado por el LLM que lo sitúa dentro del documento. Mejora la recuperación.

Se ejecuta en ingesta (no en consulta), así que su costo es único. Con Ollama
local es gratis. Se puede desactivar pasando `enabled=False`.
"""

from __future__ import annotations

from avorag.logging import get_logger
from avorag.providers import get_llm_provider

log = get_logger(__name__)

_SYSTEM = (
    "Eres un asistente que sitúa fragmentos de documentos técnicos agronómicos. "
    "Devuelves UNA sola frase breve en español, sin preámbulos."
)

_USER_TMPL = (
    "Documento (fuente): {fuente}\n"
    "Resumen del documento:\n<doc>\n{doc_summary}\n</doc>\n\n"
    "Fragmento a situar:\n<chunk>\n{chunk}\n</chunk>\n\n"
    "Escribe una sola frase de contexto que ubique este fragmento dentro del "
    "documento (tema, cultivo, sección), para mejorar su recuperación. "
    "No repitas el fragmento; solo el contexto."
)


def build_doc_summary(full_text: str, max_chars: int = 3000) -> str:
    """Resumen barato: primeros N caracteres del documento (suficiente como ancla)."""
    return full_text[:max_chars]


def contextualize_chunk(chunk: str, doc_summary: str, fuente: str) -> str:
    """Devuelve una frase de contexto para el chunk. Si falla, cadena vacía."""
    try:
        llm = get_llm_provider()
        ctx = llm.complete(
            _SYSTEM,
            _USER_TMPL.format(fuente=fuente, doc_summary=doc_summary, chunk=chunk),
            max_tokens=120,
        )
        return ctx.strip()
    except Exception as exc:  # nunca romper la ingesta por el contexto
        log.warning("contextual_retrieval_failed", error=str(exc))
        return ""
