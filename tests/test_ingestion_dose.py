"""Extracción estructurada de dosis y chunking consciente de tablas."""

from __future__ import annotations

from avorag.ingestion.chunking import chunk_text
from avorag.ingestion.metadata import (
    extract_active_ingredient,
    extract_chunk_fields,
    extract_dose_rows,
)

_TABLA = """### Tablas
| Registro ICA | Producto | Ingrediente activo | Cultivo | Plaga | Dosis | Categoria toxicologica | PC |
|---|---|---|---|---|---|---|---|
| 1234 | Vertimec | abamectina | Aguacate | Trips | 2,5 cc/L | II | 7 dias |
| 5678 | Tracer | spinetoram | Aguacate | Trips | 250 cc/100 L | III | 1 dia |
"""


def test_extract_dose_rows_parses_table() -> None:
    rows = extract_dose_rows(_TABLA)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0.ingrediente_activo == "abamectina"
    assert r0.producto == "Vertimec"
    assert r0.registro_ica == "1234"
    assert r0.categoria_toxicologica == "II"
    assert "trips" in (r0.plaga or "").lower()
    assert "cc/l" in (r0.dosis_texto or "").lower()
    assert "7" in (r0.carencia_texto or "")


def test_extract_chunk_fields_uses_structured_rows() -> None:
    fields = extract_chunk_fields(_TABLA)
    # Categoría más severa entre II y III -> II.
    assert fields["categoria_toxicologica"] == "II"
    assert fields["registro_ica"] == "1234"
    assert fields["ingrediente_activo"] == "abamectina"
    assert len(fields["dosis_estructurada"]) == 2


def test_extract_active_ingredient() -> None:
    assert extract_active_ingredient("Se recomienda abamectina al 1.8%") == "abamectina"
    assert extract_active_ingredient("aplicar agua y compost") is None


def test_chunking_does_not_split_table_rows() -> None:
    # Tabla forzada a trocearse (target pequeño): ninguna fila debe partirse y el
    # encabezado debe repetirse en cada sub-chunk.
    rows = "\n".join(
        f"| {i} | Prod{i} | abamectina | Aguacate | Trips | {i},5 cc/L | II | 7 dias |"
        for i in range(40)
    )
    tabla = (
        "| Reg | Producto | Ingrediente activo | Cultivo | Plaga | Dosis | Cat | PC |\n|---|---|---|---|---|---|---|---|\n"
        + rows
    )
    chunks = chunk_text(tabla, target_tokens=80)
    assert len(chunks) > 1
    for c in chunks:
        assert "Ingrediente activo" in c.text
        for line in c.text.splitlines():
            if line.strip().startswith("|") and "Prod" in line:
                assert line.strip().endswith("|"), f"fila partida: {line!r}"
