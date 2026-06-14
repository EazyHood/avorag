"""Tests del chunking recursivo (puro, sin dependencias externas)."""

from avorag.ingestion.chunking import chunk_text


def test_chunk_short_text_single_chunk():
    chunks = chunk_text("Una frase corta sobre el aguacate Hass.", target_tokens=480)
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0


def test_chunk_long_text_splits_with_sequential_ordinals():
    parrafo = "El trips ataca el aguacate Hass causando daño en hojas y frutos. " * 60
    chunks = chunk_text(parrafo, target_tokens=80, overlap_ratio=0.1)
    assert len(chunks) > 1
    ordinals = [c.ordinal for c in chunks]
    assert ordinals == list(range(len(chunks)))


def test_chunk_respects_max_size_roughly():
    texto = "palabra " * 2000
    chunks = chunk_text(texto, target_tokens=100, overlap_ratio=0.0)
    max_chars = 100 * 4
    # Permite holgura por el solape/separadores, pero no debe desbordar mucho.
    assert all(len(c.text) <= max_chars * 1.6 for c in chunks)


def test_chunk_keeps_page_number():
    chunks = chunk_text("Texto de la página 7.", page=7)
    assert chunks[0].page == 7


def test_empty_text_yields_no_chunks():
    assert chunk_text("   ") == []
