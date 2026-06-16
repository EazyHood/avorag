"""Calidad de ingesta: resumen de documento real y conservación de pies de figura."""

from __future__ import annotations

from avorag.ingestion.contextual import build_doc_summary
from avorag.ingestion.loaders import strip_running_headers


def test_doc_summary_skips_cover_and_captures_structure() -> None:
    indice = "\n".join(f"Capitulo {i} .................... {i}" for i in range(1, 20))
    cuerpo = (
        "MANEJO DEL TRIPS\n"
        + ("El trips se monitorea con trampas azules. " * 200)
        + "La dosis recomendada figura en la tabla. "
        + ("Continua el texto tecnico. " * 200)
        + "FERTILIZACION\nEl nitrogeno se aplica fraccionado."
    )
    summary = build_doc_summary("PORTADA DEL DOCUMENTO\n" + indice + "\n" + cuerpo)
    # Capta títulos de sección reales, no líneas de índice con puntos guía.
    assert "MANEJO DEL TRIPS" in summary or "FERTILIZACION" in summary
    assert "...................." not in summary


def test_captions_survive_header_stripping() -> None:
    # 'Figura N.' se repite pero NO debe eliminarse como encabezado corriente.
    pages = [
        f"Figura {i}. Dano de trips en fruto\nTexto distinto de la pagina {i}." for i in range(8)
    ]
    cleaned = strip_running_headers(pages)
    assert all("Figura" in c for c in cleaned)
