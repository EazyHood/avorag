"""Carga de documentos. PDF vía PyMuPDF preservando texto por página."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LoadedPage:
    page_number: int  # 1-based
    text: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _extract_tables_markdown(page) -> str:
    """Extrae tablas (clave para dosis) como Markdown. Falla en silencio si no hay/error."""
    try:
        finder = page.find_tables()
    except Exception:
        return ""
    parts: list[str] = []
    for table in getattr(finder, "tables", []):
        try:
            md = table.to_markdown()
        except Exception:
            continue
        if md and md.strip():
            parts.append(md.strip())
    return "\n\n".join(parts)


def _norm_line(line: str) -> str:
    """Normaliza una línea (colapsa espacios y reemplaza dígitos) para detectar repetidos."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line)).strip()


def strip_running_headers(
    page_texts: list[str], *, min_pages: int = 4, ratio: float = 0.4
) -> list[str]:
    """Elimina encabezados/pies de página repetidos (basura que contamina la recuperación).

    Una línea cuya forma normalizada aparece en ≥ `ratio` de las páginas (y al menos
    `min_pages`) se considera encabezado/pie y se quita de todas las páginas.
    """
    if len(page_texts) < min_pages:
        return page_texts
    counts: Counter[str] = Counter()
    for t in page_texts:
        for n in {_norm_line(ln) for ln in t.splitlines() if len(_norm_line(ln)) >= 8}:
            counts[n] += 1
    threshold = max(min_pages, int(len(page_texts) * ratio))
    headers = {n for n, c in counts.items() if c >= threshold}
    if not headers:
        return page_texts
    return [
        "\n".join(ln for ln in t.splitlines() if _norm_line(ln) not in headers)
        for t in page_texts
    ]


def load_pdf(path: Path) -> list[LoadedPage]:
    """Extrae texto por página (quitando encabezados/pies repetidos) y las tablas como Markdown.

    Las tablas de dosis son críticas para el guardarraíl: se anexan en formato Markdown
    para preservar su estructura (no como texto plano que rompe filas/columnas).
    """
    import fitz  # PyMuPDF

    raw: list[tuple[int, str, str]] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            raw.append((i, page.get_text("text"), _extract_tables_markdown(page)))

    cleaned = strip_running_headers([body for _, body, _ in raw])

    pages: list[LoadedPage] = []
    for (i, _, tables_md), body in zip(raw, cleaned, strict=True):
        text = body.strip()
        if tables_md:
            text = (text + "\n\n### Tablas\n" + tables_md).strip()
        if text:
            pages.append(LoadedPage(page_number=i, text=text))
    return pages


def load_text(path: Path) -> list[LoadedPage]:
    """Carga un .txt/.md como una sola 'página'."""
    return [LoadedPage(page_number=1, text=path.read_text(encoding="utf-8").strip())]


def load_document(path: Path) -> list[LoadedPage]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix in (".txt", ".md"):
        return load_text(path)
    raise ValueError(f"Formato no soportado: {suffix} (usa .pdf, .txt o .md)")
