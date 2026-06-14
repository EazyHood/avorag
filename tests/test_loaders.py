"""Tests del limpiador de encabezados/pies repetidos (puro)."""

from avorag.ingestion.loaders import strip_running_headers


def test_strip_removes_repeated_header_keeps_content():
    temas = ["trips", "acaros", "monalonion", "pega pega", "antracnosis",
             "roña", "barrenador", "chinche", "mosca", "escama"]
    pages = [
        f"[ {i + 1} ] Manejo fitosanitario del aguacate Hass\nContenido sobre {temas[i]}."
        for i in range(10)
    ]
    cleaned = strip_running_headers(pages)
    # El encabezado repetido desaparece…
    assert all("Manejo fitosanitario del aguacate Hass" not in c for c in cleaned)
    # …pero el contenido real se conserva.
    assert any("trips" in c for c in cleaned)
    assert any("antracnosis" in c for c in cleaned)


def test_strip_keeps_when_no_repeated_lines():
    pages = [f"Texto único número {w}" for w in ("uno", "dos", "tres", "cuatro", "cinco")]
    assert strip_running_headers(pages) == pages


def test_strip_noop_for_few_pages():
    pages = ["a", "b"]
    assert strip_running_headers(pages) == pages
