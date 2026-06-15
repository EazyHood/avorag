"""Suite red-team de modos de fallo (amplifica las fortalezas #1 y #36).

Cataloga, de forma VERSIONADA, cada modo de fallo que el sistema dice atacar, y prueba
end-to-end (por los guardarraíles deterministas, sin LLM) que CADA uno termina en el semáforo
esperado con la razón esperada. Si alguien rompe una rama de `decide_semaforo`, su modo cae.

`data/redteam/failure_modes.jsonl` es el catálogo; `_CANONICAL_MODES` lista los modos que el
sistema afirma cubrir y el test exige que TODOS tengan ≥1 fila (failure_mode_coverage = 100%).
El modo 'juez_caido' se cubre exhaustivamente en `test_failsafe_invariants.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from avorag.rag import guardrails as g
from avorag.retrieval.types import ScoredChunk

_DATA = Path(__file__).resolve().parents[1] / "data" / "redteam" / "failure_modes.jsonl"

_CANONICAL_MODES = {
    "dosis_producto_equivocado",
    "carencia_inventada",
    "dosis_sin_registro",
    "cita_fuera_de_rango",
    "cifra_citada_ausente",
    "ingrediente_prohibido",
    "off_label",
    "categoria_i",
    "conflicto_fuentes",
}


def _load() -> list[dict]:
    return [json.loads(ln) for ln in _DATA.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _chunks(rows: list[dict]) -> list[ScoredChunk]:
    out = []
    for i, c in enumerate(rows):
        chunk = SimpleNamespace(
            id=f"c{i}", content=c["content"], context=None, pagina=1, meta=c.get("meta", {})
        )
        out.append(ScoredChunk(chunk=chunk, score=1.0))
    return out


def _evaluate_deterministic(question: str, answer: str, chunks: list[ScoredChunk]):
    """Replica el subconjunto DETERMINISTA del guardarraíl del pipeline (sin jueces LLM)."""
    ctx = "\n".join(g._chunk_content(c) for c in chunks)
    doses_ok, _ = g.dose_product_grounded(answer, chunks)
    phi_ok, _ = g.phi_grounded(answer, ctx)
    banned = g.banned_ingredients_in_answer(question + "\n" + answer)
    offlabel = g.is_offlabel(answer, chunks)
    actionable = g.has_actionable_recommendation(answer)
    registro_required = g.recommends_pesticide(answer)
    registro_ok = g.ica_registro_ok(chunks)
    citation_ok, _ = g.citation_supports_claim(answer, chunks)
    conflicts = g.dose_conflicts(chunks)
    cat_tox = g.cited_categoria_toxicologica(chunks)
    return g.decide_semaforo(
        doses_ok=doses_ok,
        phi_ok=phi_ok,
        cat_tox=cat_tox,
        faithfulness=0.9,
        has_citations=True,
        judge_failed=False,
        safety=None,
        safety_required=False,  # determinista: el juez LLM se prueba aparte
        banned=banned,
        offlabel=offlabel,
        registro_ok=registro_ok,
        registro_required=registro_required and actionable,
        citation_ok=citation_ok,
        conflicts=conflicts,
    )


@pytest.mark.parametrize("row", _load(), ids=lambda r: r["failure_mode"])
def test_failure_mode_is_caught(row: dict) -> None:
    semaforo, reason = _evaluate_deterministic(
        row["question"], row["answer"], _chunks(row["chunks"])
    )
    assert semaforo.value == row["expected_semaforo"], f"{row['failure_mode']}: {reason}"
    assert row["expected_reason_substring"].lower() in reason.lower(), reason


def test_failure_mode_coverage_is_complete() -> None:
    covered = {r["failure_mode"] for r in _load()}
    missing = _CANONICAL_MODES - covered
    assert not missing, f"modos de fallo sin caso red-team: {missing}"
