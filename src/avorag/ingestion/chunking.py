"""Chunking recursivo por separadores semánticos, con solape. Tamaño en tokens (~4 chars/token)."""

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


def _is_separator_row(line: str) -> bool:
    return set(line.replace("|", "").strip()) <= set("-: ")


def _segment_blocks(text: str) -> list[tuple[str, str]]:
    """Separa el texto en bloques de prosa y bloques de tabla Markdown (líneas con '|')."""
    segments: list[tuple[str, str]] = []
    cur_kind: str | None = None
    cur: list[str] = []
    for ln in text.splitlines():
        kind = "table" if ln.strip().startswith("|") else "prose"
        if cur_kind is not None and kind != cur_kind and cur:
            segments.append((cur_kind, "\n".join(cur)))
            cur = []
        cur_kind = kind
        cur.append(ln)
    if cur and cur_kind is not None:
        segments.append((cur_kind, "\n".join(cur)))
    return segments


def _split_table(block: str, max_chars: int) -> list[str]:
    """Trocea una tabla Markdown por filas, re-anteponiendo el encabezado a cada sub-chunk."""
    lines = [ln for ln in block.splitlines() if ln.strip()]
    if not lines:
        return []
    header = [lines[0]]
    body_start = 1
    if len(lines) > 1 and _is_separator_row(lines[1]):
        header.append(lines[1])
        body_start = 2
    if len(block) <= max_chars:
        return [block.strip()]
    header_len = len("\n".join(header))
    chunks: list[str] = []
    cur = list(header)
    cur_len = header_len
    for ln in lines[body_start:]:
        if cur_len + len(ln) + 1 > max_chars and len(cur) > len(header):
            chunks.append("\n".join(cur))
            cur = [*header, ln]
            cur_len = header_len + len(ln) + 1
        else:
            cur.append(ln)
            cur_len += len(ln) + 1
    if len(cur) > len(header):
        chunks.append("\n".join(cur))
    return chunks


def chunk_text(
    text: str,
    *,
    target_tokens: int = 480,
    overlap_ratio: float = 0.15,
    page: int | None = None,
    start_ordinal: int = 0,
) -> list[TextChunk]:
    """Divide un texto en chunks con solape. Las tablas se trocean por filas (con encabezado
    repetido) y la prosa por separadores semánticos. Devuelve TextChunk numerados."""
    max_chars = target_tokens * _CHARS_PER_TOKEN
    overlap_chars = int(max_chars * overlap_ratio)
    pieces: list[str] = []
    for kind, block in _segment_blocks(text):
        if kind == "table":
            pieces.extend(_split_table(block, max_chars))
        else:
            prose = _split_recursive(block, max_chars, _SEPARATORS)
            pieces.extend(_apply_overlap(prose, overlap_chars))
    pieces = [p for p in pieces if p.strip()]
    return [TextChunk(text=t, ordinal=start_ordinal + i, page=page) for i, t in enumerate(pieces)]
