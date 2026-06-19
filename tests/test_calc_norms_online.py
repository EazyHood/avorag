"""Enriquecimiento de calculadoras con norm_tables: mapeo puro + gate + lectura."""

from __future__ import annotations

from avorag.online import calc_norms


def test_disabled_no_resuelve(monkeypatch):
    monkeypatch.delenv("AVORAG_ONLINE_NORMS", raising=False)
    assert calc_norms.resolve_ms_umbral("exportacion") == (None, None)
    assert calc_norms.resolve_ce_umbral("mexicano") == (None, None)


def test_ms_umbral_from_params():
    p = {"minimo_legal": 20.8, "exportacion": 23.0, "premium": 25.0}
    assert calc_norms.ms_umbral_from_params(p, "premium") == 25.0
    assert calc_norms.ms_umbral_from_params(p, None) == 23.0  # default = exportacion
    assert calc_norms.ms_umbral_from_params(p, "inexistente") is None


def test_ce_umbral_from_params():
    p = {"mexicano": 1.0, "guatemalteco": 1.3, "_default": 1.3}
    assert calc_norms.ce_umbral_from_params(p, "mexicano") == 1.0
    assert calc_norms.ce_umbral_from_params(p, "otro") == 1.3  # cae al _default
    assert calc_norms.ce_umbral_from_params(p, None) == 1.3


def test_enabled_lee_la_norma(monkeypatch):
    monkeypatch.setenv("AVORAG_ONLINE_NORMS", "1")
    monkeypatch.setattr(
        calc_norms, "_norm_params", lambda key, scope: ({"exportacion": 24.0}, "v2")
    )
    assert calc_norms.resolve_ms_umbral("exportacion") == (24.0, "v2")
