"""Tests del describidor visual de síntomas (lógica pura + FakeDescriber; sin VLM, RAG ni red)."""

from __future__ import annotations

import base64
import io

import pytest

from avorag.vision.describe import (
    FakeDescriber,
    _report_from_text,
    _to_jpeg_b64,
    build_health_query,
)


def test_fake_describer_reporta_sintomas():
    r = FakeDescriber().describe(b"x")
    assert not r.sin_sintomas
    assert r.descripcion
    assert r.provider == "fake"


def test_build_health_query_incluye_la_descripcion():
    r = FakeDescriber().describe(b"x")
    q = build_health_query(r)
    assert q is not None
    assert "aguacate Hass" in q
    assert r.descripcion[:25] in q  # la descripción de síntomas va dentro de la consulta al RAG


def test_build_health_query_none_si_sin_sintomas():
    r = _report_from_text("SIN SINTOMAS CLAROS", provider="fake")
    assert r.sin_sintomas is True
    assert build_health_query(r) is None


def test_report_from_text_vacio_es_sin_sintomas():
    assert _report_from_text("   ", provider="x").sin_sintomas is True


def test_to_jpeg_b64_convierte_png_transparente_a_jpeg():
    Image = pytest.importorskip("PIL.Image")  # extra 'vision' (Pillow); se salta en CI puro

    buf = io.BytesIO()
    Image.new("RGBA", (40, 30), (0, 255, 0, 128)).save(buf, format="PNG")  # con transparencia
    raw = base64.b64decode(_to_jpeg_b64(buf.getvalue()))
    assert raw[:3] == b"\xff\xd8\xff"  # cabecera JPEG (transparencia aplanada, formato normalizado)


def test_to_jpeg_b64_rechaza_archivo_no_imagen():
    pytest.importorskip("PIL")  # _to_jpeg_b64 importa Pillow (extra 'vision'); se salta en CI puro
    with pytest.raises(ValueError):
        _to_jpeg_b64(b"esto no es una imagen")
