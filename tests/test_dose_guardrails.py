"""Guardarraíles deterministas de dosis atados al fragmento de origen."""

from __future__ import annotations

from types import SimpleNamespace

from avorag.rag.guardrails import (
    banned_ingredients_in_answer,
    citation_supports_claim,
    decide_semaforo,
    dose_conflicts,
    dose_product_grounded,
    ica_registro_ok,
    is_offlabel,
    recommends_pesticide,
)
from avorag.rag.schemas import Semaforo
from avorag.retrieval.types import ScoredChunk


def mk(content: str, **meta) -> ScoredChunk:
    chunk = SimpleNamespace(id="c", content=content, context=None, pagina=1, meta=meta)
    return ScoredChunk(chunk=chunk, score=1.0)


def test_dose_with_wrong_product_is_unsupported() -> None:
    # La respuesta asocia 2,5 cc/L a abamectina, pero el único fragmento con esa dosis es de
    # clorpirifos -> dosis no respaldada para el producto correcto.
    answer = "Aplica abamectina a una dosis de 2,5 cc/L."
    chunks = [mk("Lorsban (clorpirifos) se usa a 2,5 cc/L en otros cultivos.")]
    ok, unsupported = dose_product_grounded(answer, chunks)
    assert ok is False
    assert "2.5" in unsupported


def test_dose_with_correct_product_is_grounded() -> None:
    answer = "Aplica abamectina a una dosis de 2,5 cc/L."
    chunks = [mk("Vertimec (abamectina) para trips: 2,5 cc/L.")]
    ok, _ = dose_product_grounded(answer, chunks)
    assert ok is True


def test_ica_registro_ok_requires_official_non_expired() -> None:
    good = [
        mk(
            "...",
            registro_ica="1234",
            vigencia="por-verificar",
            nivel_autoridad="oficial-regulador",
        )
    ]
    assert ica_registro_ok(good) is True
    expired = [
        mk("...", registro_ica="1234", vigencia="caducado", nivel_autoridad="oficial-regulador")
    ]
    assert ica_registro_ok(expired) is False
    no_reg = [mk("...", nivel_autoridad="oficial-regulador")]
    assert ica_registro_ok(no_reg) is False


def test_citation_supports_claim_detects_unsupported_figure() -> None:
    chunks = [mk("La carencia es de 14 dias."), mk("Dosis de abamectina 2,5 cc/L.")]
    ok, issues = citation_supports_claim("Aplica 9 cc/L [1] segun la fuente.", chunks)
    assert ok is False
    assert any("[1]" in i for i in issues)
    ok2, _ = citation_supports_claim("Aplica 2,5 cc/L [2].", chunks)
    assert ok2 is True


def test_banned_ingredient_flagged() -> None:
    hits = banned_ingredients_in_answer("Puedes usar clorpirifos para el trips.")
    assert hits and "clorpirifos" in hits[0]


def test_recommends_pesticide() -> None:
    assert recommends_pesticide("Aplica abamectina 2,5 cc/L") is True
    assert recommends_pesticide("Aplica 150 kg/ha de nitrogeno") is False  # fertilizante


def test_lluvia_y_suelo_no_son_dosis() -> None:
    # Falso positivo: "2.000 mm de lluvia" o pH no deben tratarse como dosis fitosanitaria.
    txt = "El Hass requiere suelo bien drenado, pH 5,5 a 6,5 y 1.000 a 2.000 mm de lluvia al año."
    ch = [mk("pH 5,5 a 6,5; 1.000 a 2.000 mm de lluvia", cultivo="hass")]
    ok, unsupported = dose_product_grounded(txt, ch)
    assert ok and not unsupported  # ya no marca "2.000" como dosis sin respaldo
    assert not recommends_pesticide(txt)


def test_dose_conflicts_across_sources() -> None:
    chunks = [mk("abamectina 2,5 cc/L"), mk("abamectina 10 cc/L")]
    conflicts = dose_conflicts(chunks)
    assert conflicts and "abamectina" in conflicts[0]


def test_dose_conflicts_ratio_exacto_1_5_se_detecta() -> None:
    # Un ratio exacto de 1.5 (50% de diferencia) es crítico en dosis y SÍ debe avisar.
    chunks = [mk("abamectina 2,0 cc/L"), mk("abamectina 3,0 cc/L")]
    conflicts = dose_conflicts(chunks)
    assert conflicts and "abamectina" in conflicts[0]


def test_dose_conflicts_compacta_muchos_valores() -> None:
    # Con >3 valores dispares se resume (rango + nº), no se vuelca la lista completa.
    chunks = [mk(f"abamectina {v} cc/L") for v in ("1", "2", "5", "10", "20")]
    conflicts = dose_conflicts(chunks)
    assert conflicts and "valores distintos" in conflicts[0]


def test_is_offlabel_when_only_other_crop_supports() -> None:
    answer = "Aplica abamectina 2,5 cc/L."
    chunks = [mk("abamectina 2,5 cc/L en tomate", cultivo="tomate")]
    assert is_offlabel(answer, chunks) is True
    chunks_hass = [mk("abamectina 2,5 cc/L en aguacate", cultivo="hass")]
    assert is_offlabel(answer, chunks_hass) is False


def test_semaforo_new_branches() -> None:
    base = {"cat_tox": {"N/A"}, "faithfulness": 0.9, "doses_ok": True}
    assert decide_semaforo(**base, banned=["clorpirifos (restringido)"])[0] == Semaforo.ROJO
    assert decide_semaforo(**base, offlabel=True)[0] == Semaforo.ROJO
    assert decide_semaforo(**base, registro_required=True, registro_ok=False)[0] == Semaforo.ROJO
    assert decide_semaforo(**base, citation_ok=False)[0] == Semaforo.AMARILLO
    assert decide_semaforo(**base, conflicts=["abamectina: 2,5 vs 10"])[0] == Semaforo.AMARILLO
    assert decide_semaforo(**base)[0] == Semaforo.VERDE


def test_semaforo_cat_i_rojo_cat_ii_amarillo() -> None:
    # Cat I (extrema) -> ROJO; cat II del fragmento -> AMARILLO.
    assert decide_semaforo(doses_ok=True, cat_tox={"I"}, faithfulness=0.9)[0] == Semaforo.ROJO
    assert decide_semaforo(doses_ok=True, cat_tox={"II"}, faithfulness=0.9)[0] == Semaforo.AMARILLO
    assert decide_semaforo(doses_ok=True, cat_tox={"III"}, faithfulness=0.9)[0] == Semaforo.VERDE
