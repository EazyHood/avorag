"""Chunking recursivo orientado a documentos técnicos en español.

Estrategia (ver docs/adr/0003): partir por separadores semánticos (párrafo →
línea → oración → palabra) hasta acercarse a un tamaño objetivo, con solape.
El tamaño se expresa en tokens aproximados (~4 caracteres/token).
"""

from __future__ import annotations

from dataclasses import dataclass

_CHARS_PER_TOKEN = 4
_SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " "]


@dataclass
class TextChunk:
    text: str
    ordinal: int
    page: int | None = None


def _split_recursive(text: str, max_chars: int, separators: list[str]) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars or not separators:
        return [text] if text else []

    sep = separators[0]
    parts = text.split(sep)
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        piece = part + sep
        if len(buffer) + len(piece) <= max_chars:
            buffer += piece
        else:
            if buffer.strip():
                chunks.append(buffer.strip())
            if len(piece) > max_chars:
                chunks.extend(_split_recursive(part, max_chars, separators[1:]))
                buffer = ""
            else:
                buffer = piece
    if buffer.strip():
        chunks.append(buffer.strip())
    return [c for c in chunks if c]


def _apply_overlap(chunks: list[str], overlap_chars: int) -> list[str]:
    if overlap_chars <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        tail = prev[-overlap_chars:]
        out.append((tail + " " + cur).strip())
    return out


def chunk_text(
    text: str,
    *,
    target_tokens: int = 480,
    overlap_ratio: float = 0.15,
    page: int | None = None,
    start_ordinal: int = 0,
) -> list[TextChunk]:
    """Divide un texto en chunks con solape. Devuelve TextChunk numerados."""
    max_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = int(max_chars * overlap_ratio)
    raw = _split_recursive(text, max_chars, _SEPARATORS)
    raw = _apply_overlap(raw, overlap_chars)
    return [TextChunk(text=t, ordinal=start_ordinal + i, page=page) for i, t in enumerate(raw)]
