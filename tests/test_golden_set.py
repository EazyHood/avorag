"""Contrato del golden set (amplifica las fortalezas #18, #19, #20).

Corre en CI sin BD ni LLM: valida estructura, invariantes de seguridad y cobertura mínima por
eje de riesgo. Si alguien mete un id duplicado, una categoría inválida o baja la cobertura de
prohibidos/dosis/trampas, el CI lo caza.
"""

from __future__ import annotations

from pathlib import Path

from avorag.eval.golden_set import (
    CATEGORIES,
    COVERAGE_MINIMUMS,
    coverage_matrix,
    load_golden,
)

_GOLDEN = Path(__file__).resolve().parents[1] / "data" / "golden" / "hass_v1.jsonl"
_ITEMS = load_golden(_GOLDEN)
_UNSAFE_CATEGORIES = {"mezcla", "incompatibilidad", "fitotoxicidad", "prohibido"}


def test_ids_unique_and_questions_nonempty() -> None:
    ids = [i.id for i in _ITEMS]
    assert len(ids) == len(set(ids)), "ids duplicados en el golden set"
    assert all(i.question.strip() for i in _ITEMS)


def test_categories_are_in_closed_set() -> None:
    bad = {i.category for i in _ITEMS if i.category and i.category not in CATEGORIES}
    assert not bad, f"categorías fuera de CATEGORIES: {bad}"


def test_safety_invariants() -> None:
    for i in _ITEMS:
        assert not (i.is_trap and i.expect_unsafe), f"{i.id}: is_trap y expect_unsafe a la vez"
        if i.category in _UNSAFE_CATEGORIES:
            assert i.expect_unsafe, f"{i.id} ({i.category}) debería ser expect_unsafe"
        if i.expected_facts:
            assert not i.is_trap, f"{i.id}: expected_facts no aplica a una trampa"


def test_coverage_minimums_met() -> None:
    matrix = coverage_matrix(_ITEMS)
    for axis, minimum in COVERAGE_MINIMUMS.items():
        assert matrix.get(axis, 0) >= minimum, (
            f"cobertura '{axis}' = {matrix.get(axis, 0)} < mínimo {minimum}"
        )
