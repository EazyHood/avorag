"""Carga de documentos. PDF vía PyMuPDF preservando texto por página."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from avorag.logging import get_logger

log = get_logger(__name__)


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


# Pies de figura/foto/tabla: información valiosa para identificar plaga/enfermedad (#21).
_CAPTION_RE = re.compile(
    r"^\s*(figura|foto|fotograf[ií]a|tabla|gr[áa]fica|imagen)\s*\d", re.IGNORECASE
)


def _is_caption(line: str) -> bool:
    return bool(_CAPTION_RE.match(line))


def strip_running_headers(
    page_texts: list[str], *, min_pages: int = 4, ratio: float = 0.4
) -> list[str]:
    """Elimina encabezados/pies de página repetidos (basura que contamina la recuperación).

    Una línea cuya forma normalizada aparece en ≥ `ratio` de las páginas (y al menos
    `min_pages`) se considera encabezado/pie y se quita de todas las páginas. EXCEPCIÓN: los
    pies de figura/foto/tabla ('Figura 1.', 'Foto 2.'…) se conservan aunque se repitan, porque
    al normalizar el dígito coinciden y, en una guía visual, son la única info textual de la
    imagen (clave para identificar plaga/enfermedad).
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
        "\n".join(ln for ln in t.splitlines() if _is_caption(ln) or _norm_line(ln) not in headers)
        for t in page_texts
    ]


_OCR_MIN_CHARS = 40  # por debajo de esto, la página se considera 'solo imagen'


def _ocr_page(page) -> str:
    """OCR de una página-imagen. Requiere el extra 'ocr' (pytesseract + binario tesseract).
    Si no está disponible, devuelve '' y deja un aviso (no rompe la ingesta)."""
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        log.warning(
            "ocr_unavailable", hint="instala el extra: uv sync --extra ocr  +  binario tesseract"
        )
        return ""
    try:
        import fitz  # PyMuPDF

        pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return pytesseract.image_to_string(img, lang="spa").strip()
    except Exception as exc:
        log.warning("ocr_failed", error=str(exc))
        return ""


def load_pdf(path: Path, *, ocr: bool = False) -> list[LoadedPage]:
    """Extrae texto por página (quitando encabezados/pies repetidos) y las tablas como Markdown.

    Las tablas de dosis son críticas para el guardarraíl: se anexan en formato Markdown
    para preservar su estructura (no como texto plano que rompe filas/columnas). Con `ocr=True`,
    las páginas sin texto extraíble (PDF escaneado) se pasan por OCR — habilita documentos como
    la Resolución ICA 1507/2016 (#22).
    """
    import fitz  # PyMuPDF

    raw: list[tuple[int, str, str]] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            body = page.get_text("text")
            if ocr and len(body.strip()) < _OCR_MIN_CHARS:
                ocr_text = _ocr_page(page)
                if ocr_text:
                    body = ocr_text
            raw.append((i, body, _extract_tables_markdown(page)))

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


def load_document(path: Path, *, ocr: bool = False) -> list[LoadedPage]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path, ocr=ocr)
    if suffix in (".txt", ".md"):
        return load_text(path)
    raise ValueError(f"Formato no soportado: {suffix} (usa .pdf, .txt o .md)")
