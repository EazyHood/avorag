"""Proveedor REAL de feed por archivo CSV (export oficial → esquema canónico)."""

from __future__ import annotations

import csv
from pathlib import Path

from avorag.online import feeds
from avorag.rag.freshness import FeedName


def _csv(path, rows, fields):
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return str(path)


def test_csv_ica_normaliza(tmp_path):
    p = _csv(
        tmp_path / "ica.csv",
        [
            {
                "ingrediente_activo": "Clorpirifos",
                "registro_ica": "1",
                "estado": "Cancelado",
                "cultivo": "varios",
            },
            {
                "ingrediente_activo": "abamectina",
                "registro_ica": "2",
                "estado": "vigente",
                "cultivo": "hass",
            },
        ],
        ["ingrediente_activo", "registro_ica", "estado", "cultivo"],
    )
    f = feeds.CsvFileProvider(FeedName.ICA, p).fetch()
    assert feeds.ica_status(f.payload, "clorpirifos") == "cancelado"
    assert feeds.ica_status(f.payload, "abamectina") == "vigente"


def test_csv_lmr_normaliza(tmp_path):
    p = _csv(
        tmp_path / "lmr.csv",
        [
            {"ingrediente_activo": "clorpirifos", "lmr_mg_kg": "", "aprobado": "no"},
            {"ingrediente_activo": "abamectina", "lmr_mg_kg": "0.01", "aprobado": "si"},
        ],
        ["ingrediente_activo", "lmr_mg_kg", "aprobado"],
    )
    f = feeds.CsvFileProvider(FeedName.LMR_UE, p).fetch()
    assert feeds.ue_lmr(f.payload, "clorpirifos") == ("no_aprobado", None)
    assert feeds.ue_lmr(f.payload, "abamectina") == ("aprobado", 0.01)


def test_csv_eeuu_normaliza(tmp_path):
    p = _csv(
        tmp_path / "tol.csv",
        [
            {"ingrediente_activo": "paraquat", "tolerancia_ppm": "0.05", "tiene_tolerancia": "si"},
            {"ingrediente_activo": "clorpirifos", "tolerancia_ppm": "", "tiene_tolerancia": "no"},
        ],
        ["ingrediente_activo", "tolerancia_ppm", "tiene_tolerancia"],
    )
    f = feeds.CsvFileProvider(FeedName.TOL_EEUU, p).fetch()
    assert feeds.eeuu_tolerance(f.payload, "paraquat") == (True, 0.05)
    assert feeds.eeuu_tolerance(f.payload, "clorpirifos") == (False, None)


def test_get_provider_real_prefiere_csv(tmp_path, monkeypatch):
    p = _csv(
        tmp_path / "ica.csv",
        [{"ingrediente_activo": "x", "registro_ica": "1", "estado": "vigente", "cultivo": "hass"}],
        ["ingrediente_activo", "registro_ica", "estado", "cultivo"],
    )
    monkeypatch.setenv("AVORAG_FEED_ICA_FILE", p)
    assert isinstance(feeds.get_provider(FeedName.ICA, mode="real"), feeds.CsvFileProvider)
