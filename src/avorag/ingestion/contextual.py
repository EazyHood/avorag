"""Contextual Retrieval: antepone a cada chunk una frase de contexto generada en ingesta."""

from __future__ import annotations

import re

from avorag.logging import get_logger
from avorag.providers import get_llm_provider

log = get_logger(__name__)

_INDEX_LINE_RE = re.compile(r"\.{4,}|\s\d{1,3}\s*$")

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


def _looks_like_heading(line: str) -> bool:
    """Heurística de título de sección: corto, con letras, sin punto final."""
    s = line.strip()
    if not (3 <= len(s) <= 80) or s.endswith("."):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    return upper / len(letters) > 0.4  # MAYÚSCULAS o Título


def build_doc_summary(full_text: str, max_chars: int = 3000) -> str:
    """Resumen-ancla del documento: títulos detectados + inicio + muestra del medio.

    Evita anclar al índice/portada en PDFs largos.
    """
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    content_lines = [ln for ln in lines if not _INDEX_LINE_RE.search(ln)] or lines
    uniq_headings: list[str] = []
    for ln in content_lines:
        if _looks_like_heading(ln) and ln not in uniq_headings:
            uniq_headings.append(ln)
    uniq_headings = uniq_headings[:15]

    body = " ".join(content_lines)
    head = body[: max_chars // 2]
    mid = len(body) // 2
    middle = body[max(0, mid - max_chars // 4) : mid + max_chars // 4]

    parts: list[str] = []
    if uniq_headings:
        parts.append("Secciones: " + " · ".join(uniq_headings))
    parts.append(head)
    if middle and middle not in head:
        parts.append("[…] " + middle)
    return "\n".join(parts)[:max_chars]


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
    except Exception as exc:  # no romper la ingesta por el contexto
        log.warning("contextual_retrieval_failed", error=str(exc))
        return ""
