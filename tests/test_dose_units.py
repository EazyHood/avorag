"""Propiedades de la normalización de unidades de dosis.

Congela las equivalencias físicas (kg↔g, L↔mL) y la auto-consistencia tabla↔regex.
"""

from __future__ import annotations

from avorag.rag.guardrails import _DOSE_PAIR_RE, _UNIT_FACTORS, _canonical_doses, doses_grounded


def test_equivalent_doses_share_canonical_key() -> None:
    assert _canonical_doses("5 kg/ha") == _canonical_doses("5000 g/ha")
    assert _canonical_doses("1 kg") == _canonical_doses("1000 g")
    assert _canonical_doses("1 L") == _canonical_doses("1000 ml")
    # Coma vs punto decimal.
    assert _canonical_doses("2,5 cc/L") == _canonical_doses("2.5 cc/L")


def test_non_equivalent_doses_differ() -> None:
    assert _canonical_doses("5 kg/ha") != _canonical_doses("6 kg/ha")
    # g/L (masa) y cc/L (volumen) no son equivalentes sin densidad.
    assert _canonical_doses("1 g/L") != _canonical_doses("1 cc/L")


def test_units_table_matches_regex() -> None:
    # Toda unidad con factor declarado debe ser reconocida por el regex de dosis.
    for unit in _UNIT_FACTORS:
        canon = _canonical_doses(f"1 {unit}")
        assert canon, f"la unidad {unit!r} de _UNIT_FACTORS no la captura _DOSE_PAIR_RE"


def test_perturbed_dose_becomes_unsupported() -> None:
    # ~+12% respecto a la fuente no debe quedar respaldado.
    contexto = "La dosis recomendada es 2,5 cc/L."
    ok, unsupported = doses_grounded("Aplica 2,8 cc/L.", contexto)
    assert ok is False and "2.8" in unsupported
    ok2, _ = doses_grounded("Aplica 2,5 cc/L.", contexto)
    assert ok2 is True


def test_dose_regex_basic() -> None:
    assert _DOSE_PAIR_RE.search("aplica 2,5 cc/L") is not None
    assert _DOSE_PAIR_RE.search("hace sol y calor") is None
