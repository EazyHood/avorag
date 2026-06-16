"""Tests de los guardarraíles de seguridad: carencia (PHI), asociación y categoría tox."""

from avorag.ingestion.metadata import extract_chunk_fields
from avorag.rag.guardrails import (
    DoseSafety,
    contains_foreign_script,
    decide_semaforo,
    has_actionable_recommendation,
    phi_grounded,
)
from avorag.rag.schemas import Semaforo


def test_phi_grounded_flags_invented_carencia():
    ok, unsupported = phi_grounded(
        "El periodo de carencia es de 12 días.", "La carencia del producto es de 21 días."
    )
    assert ok is False
    assert any("12" in u for u in unsupported)


def test_phi_grounded_ok_when_present():
    ok, _ = phi_grounded("Respeta una carencia de 21 días.", "Carencia: 21 días antes de cosechar.")
    assert ok is True


def test_has_actionable_recommendation():
    assert has_actionable_recommendation("Aplica 2.5 cc/L de producto.") is True
    assert has_actionable_recommendation("El periodo de carencia es 7 días.") is True
    assert has_actionable_recommendation("Haz monitoreo con trampas adhesivas azules.") is False


def test_semaforo_rojo_on_unsafe_association():
    s, r = decide_semaforo(
        doses_ok=True,
        cat_tox={"N/A"},
        faithfulness=0.9,
        safety=DoseSafety(
            safe=False, issues=["dosis de abamectina pegada a clorpirifos"], cat_i_ii=False
        ),
    )
    assert s == Semaforo.ROJO
    assert "asociaci" in r.lower()


def test_semaforo_rojo_on_phi_not_grounded():
    s, _ = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=0.9, phi_ok=False)
    assert s == Semaforo.ROJO


def test_semaforo_amarillo_when_safety_unavailable():
    s, _ = decide_semaforo(
        doses_ok=True, cat_tox={"N/A"}, faithfulness=0.9, safety=None, safety_required=True
    )
    assert s == Semaforo.AMARILLO


def test_semaforo_rojo_on_cat_i_ii_from_safety():
    s, _ = decide_semaforo(
        doses_ok=True,
        cat_tox={"N/A"},
        faithfulness=0.9,
        safety=DoseSafety(safe=True, issues=[], cat_i_ii=True),
    )
    assert s == Semaforo.ROJO


def test_contains_foreign_script():
    assert contains_foreign_script("Aplique potasio 的钾肥 en llenado") is True
    assert contains_foreign_script("施肥量") is True
    assert contains_foreign_script("La fertilización con nitrógeno según la región [1].") is False
    assert contains_foreign_script("Aplique 200 kg/ha de potasio.") is False


def test_semaforo_rojo_on_language_drift():
    # Aunque todo lo demás sea perfecto, si la generación se desvió de idioma -> rojo.
    s, r = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=0.95, language_ok=False)
    assert s == Semaforo.ROJO
    assert "idioma" in r.lower()


def test_extract_categoria_toxicologica_from_text():
    # Texto tipo etiqueta ICA: la categoría se extrae, no queda en N/A.
    f = extract_chunk_fields(
        "Producto X. Ingrediente activo: clorpirifos. Categoría Toxicológica II. Registro ICA No. 1234."
    )
    assert f["categoria_toxicologica"] == "II"
    assert f["registro_ica"] == "1234"


def test_extract_categoria_picks_most_severe():
    f = extract_chunk_fields("Categoría toxicológica III ... y otra Categoría toxicológica I ...")
    assert f["categoria_toxicologica"] == "I"


def test_extract_tema_fertilizacion():
    assert (
        extract_chunk_fields("Plan de fertilización con nitrógeno y potasio.")["tema"]
        == "fertilizacion"
    )
