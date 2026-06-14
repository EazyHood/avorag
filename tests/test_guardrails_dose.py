"""Tests del guardarraíl de dosis (el más crítico para seguridad)."""

from avorag.rag.guardrails import decide_semaforo, doses_grounded, extract_dose_numbers
from avorag.rag.schemas import Semaforo


def test_extract_dose_numbers_variants():
    txt = "Aplicar 2.5 cc/L y luego 300 g/ha; máximo 1,5 L/ha."
    nums = extract_dose_numbers(txt)
    assert "2.5" in nums
    assert "300" in nums
    assert "1.5" in nums  # coma normalizada a punto


def test_doses_grounded_true_when_present_in_context():
    answer = "Aplica 2.5 cc/L de producto X [1]."
    context = "La etiqueta indica una dosis de 2.5 cc/L para trips."
    ok, unsupported = doses_grounded(answer, context)
    assert ok is True
    assert unsupported == []


def test_doses_grounded_false_when_invented():
    answer = "Aplica 7 L/ha de producto X."
    context = "La etiqueta indica 2.5 cc/L para trips."
    ok, unsupported = doses_grounded(answer, context)
    assert ok is False
    assert "7" in unsupported


def test_semaforo_rojo_on_unsupported_dose():
    s, _ = decide_semaforo(doses_ok=False, cat_tox={"N/A"}, faithfulness=0.9)
    assert s == Semaforo.ROJO


def test_semaforo_rojo_on_cat_i_ii():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"I"}, faithfulness=0.9)
    assert s == Semaforo.ROJO


def test_semaforo_amarillo_on_low_faithfulness():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=0.3)
    assert s == Semaforo.AMARILLO


def test_semaforo_verde_when_all_ok():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"N/A", "III"}, faithfulness=0.85)
    assert s == Semaforo.VERDE


def test_doses_grounded_false_positive_bare_number_fixed():
    # "100" aparece en el contexto pero como ÁREA (hectáreas), no como dosis.
    answer = "Aplica 100 g/ha de producto."
    context = "El lote tiene 100 hectáreas y se trató con 2.5 cc/L."
    ok, unsupported = doses_grounded(answer, context)
    assert ok is False
    assert "100" in unsupported


def test_doses_grounded_unit_equivalence_kg_g():
    # 5 kg/ha == 5000 g/ha → debe reconocerse como respaldada (misma cantidad física).
    ok, unsupported = doses_grounded("Aplica 5 kg/ha.", "La dosis registrada es 5000 g/ha.")
    assert ok is True
    assert unsupported == []


def test_doses_grounded_real_mismatch_flagged():
    # 5 kg/ha vs 3 kg/ha → cantidades distintas, debe marcarse.
    ok, unsupported = doses_grounded("Aplica 5 kg/ha.", "La dosis registrada es 3 kg/ha.")
    assert ok is False
    assert "5" in unsupported


def test_doses_grounded_volume_equivalence_l_ml():
    # 1 L == 1000 ml.
    ok, _ = doses_grounded("Diluir en 1 l de agua.", "Usar 1000 ml de agua.")
    assert ok is True


def test_semaforo_amarillo_without_citations():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=0.9, has_citations=False)
    assert s == Semaforo.AMARILLO


def test_semaforo_amarillo_when_judge_failed():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=None, judge_failed=True)
    assert s == Semaforo.AMARILLO
