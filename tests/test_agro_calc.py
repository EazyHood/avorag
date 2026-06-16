"""Calculadoras agronómicas deterministas: materia seca, encalado por Al, relaciones foliares.

Lógica pura (sin LLM/DB) + sus endpoints API. La aritmética debe ser exacta y la entrada inválida
debe rechazarse limpiamente (las decisiones de campo dependen de estas cifras)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from avorag import agro_calc
from avorag.api.app import create_app

# ── Materia seca ────────────────────────────────────────────────────────────────────────────────


def test_materia_seca_apto() -> None:
    r = agro_calc.dry_matter(100.0, 25.0)  # 25% >= 23% umbral
    assert r.materia_seca_pct == 25.0
    assert r.veredicto == "apto"


def test_materia_seca_por_debajo() -> None:
    r = agro_calc.dry_matter(100.0, 19.0)  # 19% < 23% y < mínimo legal 20,8%
    assert r.veredicto == "por debajo"
    assert "legal" in r.nota.lower()


def test_materia_seca_limitrofe() -> None:
    r = agro_calc.dry_matter(100.0, 22.5)  # a 0,5 pts del umbral 23%
    assert r.veredicto == "limítrofe"


def test_materia_seca_umbral_personalizado() -> None:
    r = agro_calc.dry_matter(200.0, 50.0, umbral_pct=25.0)  # 25% exacto, umbral 25
    assert r.materia_seca_pct == 25.0 and r.veredicto == "apto"


def test_materia_seca_rechaza_seco_mayor_que_fresco() -> None:
    with pytest.raises(ValueError):
        agro_calc.dry_matter(50.0, 60.0)


def test_materia_seca_rechaza_pesos_no_positivos() -> None:
    with pytest.raises(ValueError):
        agro_calc.dry_matter(0.0, 0.0)


# ── Encalado por saturación de Al ─────────────────────────────────────────────────────────────


def test_encalado_requiere_cuando_alta_saturacion() -> None:
    # Al alto frente a bases: saturación alta -> requiere cal.
    r = agro_calc.liming_by_al_saturation(al=2.0, ca=3.0, mg=1.0, k=0.4)
    cice = 2.0 + 3.0 + 1.0 + 0.4
    assert r.cice_cmol_kg == round(cice, 2)
    assert r.saturacion_al_pct == round(2.0 / cice * 100, 1)
    assert r.requiere_encalado is True
    # requerimiento = Al - 0.15*CICE; cal = req*1.5
    req = 2.0 - 0.15 * cice
    assert r.requerimiento_cmol_kg == round(req, 2)
    assert r.cal_t_ha == round(req * 1.5, 2)


def test_encalado_no_requiere_cuando_baja_saturacion() -> None:
    r = agro_calc.liming_by_al_saturation(al=0.1, ca=8.0, mg=2.0, k=0.5)
    assert r.requiere_encalado is False
    assert r.cal_t_ha == 0.0


def test_encalado_ajusta_por_prnt() -> None:
    # Con PRNT 50% la dosis se duplica frente a 100%.
    r100 = agro_calc.liming_by_al_saturation(al=2.0, ca=3.0, mg=1.0, k=0.4, prnt_pct=100.0)
    r50 = agro_calc.liming_by_al_saturation(al=2.0, ca=3.0, mg=1.0, k=0.4, prnt_pct=50.0)
    assert r50.cal_t_ha == pytest.approx(r100.cal_t_ha * 2, rel=1e-6)


def test_encalado_rechaza_cice_cero() -> None:
    with pytest.raises(ValueError):
        agro_calc.liming_by_al_saturation(al=0.0, ca=0.0, mg=0.0, k=0.0)


# ── Relaciones foliares ─────────────────────────────────────────────────────────────────────────


def test_foliar_ratios_calcula_y_clasifica() -> None:
    r = agro_calc.foliar_ratios(n=2.0, k=1.0, ca=1.0, mg=0.3)
    assert r.relaciones["K/Ca"].valor == 1.0 and r.relaciones["K/Ca"].estado == "óptimo"
    assert r.relaciones["N/K"].valor == 2.0 and r.relaciones["N/K"].estado == "óptimo"
    assert r.relaciones["Ca/Mg"].valor == round(1.0 / 0.3, 2)  # 3.33 -> óptimo (2–5)


def test_foliar_ratios_detecta_desbalance() -> None:
    r = agro_calc.foliar_ratios(k=3.0, ca=1.0)  # K/Ca = 3 > 1.5 -> alto
    assert r.relaciones["K/Ca"].estado == "alto"


def test_foliar_ratios_requiere_dos_macros() -> None:
    with pytest.raises(ValueError):
        agro_calc.foliar_ratios(n=2.0)  # solo uno: no se puede formar ninguna relación


# ── API ───────────────────────────────────────────────────────────────────────────────────────


def _client() -> TestClient:
    return TestClient(create_app())  # sin `with`: no dispara el lifespan (warmup)


def test_api_materia_seca_ok() -> None:
    r = _client().post("/api/calc/materia-seca", json={"peso_fresco_g": 100, "peso_seco_g": 24})
    assert r.status_code == 200
    assert r.json()["veredicto"] == "apto"


def test_api_materia_seca_input_invalido_400() -> None:
    r = _client().post("/api/calc/materia-seca", json={"peso_fresco_g": 50, "peso_seco_g": 60})
    assert r.status_code == 400


def test_api_encalado_ok() -> None:
    r = _client().post(
        "/api/calc/encalado", json={"al": 2.0, "ca": 3.0, "mg": 1.0, "k": 0.4}
    )
    assert r.status_code == 200
    assert r.json()["requiere_encalado"] is True


def test_api_relaciones_foliares_ok() -> None:
    r = _client().post("/api/calc/relaciones-foliares", json={"k": 1.0, "ca": 1.0})
    assert r.status_code == 200
    assert "K/Ca" in r.json()["relaciones"]
