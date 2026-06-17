"""Guardarraíles deterministas de dosis atados al fragmento de origen."""

from __future__ import annotations

from types import SimpleNamespace

from avorag.rag.guardrails import (
    banned_ingredients_in_answer,
    citation_supports_claim,
    decide_semaforo,
    dose_conflicts,
    dose_product_grounded,
    fertilizer_dose_issues,
    ica_registro_ok,
    is_offlabel,
    recommends_pesticide,
    resistance_reminder,
    unsafe_framing,
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


def test_porcentaje_de_pendiente_no_es_dosis() -> None:
    # Falso positivo real: "pendiente del 10% al 20%, menores al 40%" no es concentración de plaguicida.
    txt = "Se recomienda una pendiente entre el 10% y el 20%, y no hay problema con pendientes menores al 40%."
    ok, unsupported = dose_product_grounded(txt, [mk("topografía y drenaje del lote", cultivo="hass")])
    assert ok and not unsupported


def test_porcentaje_de_plaguicida_si_se_verifica() -> None:
    # No debilitar la seguridad: un % de concentración de un plaguicida sin respaldo SÍ se marca.
    txt = "Aplica glifosato al 2% en la calle."
    ok, unsupported = dose_product_grounded(txt, [mk("manejo de coberturas", cultivo="hass")])
    assert not ok and "2" in unsupported


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


# ── Marco peligroso (premisa adversaria sin i.a./dosis concretos) ───────────────────────────────


def test_unsafe_framing_duplicar_dosis_sin_refutar() -> None:
    # La trampa que se colaba en VERDE: "si duplico la dosis controlo mejor" y la respuesta no refuta.
    q = "Si duplico la dosis del insecticida, ¿controlo mejor el trips del aguacate?"
    bad = "Sí, al duplicar la dosis el efecto es mayor y controlas mejor la plaga [1]."
    flagged, _ = unsafe_framing(q, bad)
    assert flagged is True


def test_unsafe_framing_se_levanta_si_la_respuesta_refuta() -> None:
    # Respuesta correcta: NO debes duplicar; respeta la etiqueta. No debe marcarse (puede ir verde).
    q = "Si duplico la dosis del insecticida, ¿controlo mejor el trips?"
    good = (
        "No, no dupliques la dosis: causa fitotoxicidad y resistencia, y arriesga el LMR. "
        "Respeta la dosis de la etiqueta registrada [1]."
    )
    flagged, _ = unsafe_framing(q, good)
    assert flagged is False


def test_unsafe_framing_cualquier_producto_y_sin_carencia() -> None:
    assert unsafe_framing("¿Cualquier insecticida sirve a 5 cc/L para el trips?", "Sí, sirve [1].")[0]
    assert unsafe_framing("Dame un insecticida sin periodo de carencia", "Usa este producto [1].")[0]


def test_unsafe_framing_pregunta_normal_no_marca() -> None:
    # Sin premisa peligrosa -> nunca se marca.
    assert unsafe_framing("¿Cuál es la dosis de abamectina para el trips?", "Aplica 2,5 cc/L [1].")[0] is False


def test_semaforo_unsafe_framing_es_rojo() -> None:
    s, r = decide_semaforo(doses_ok=True, cat_tox={"N/A"}, faithfulness=0.95, unsafe_framing=True)
    assert s == Semaforo.ROJO
    assert "premisa insegura" in r.lower()


# ── Cordura de dosis de fertilizante (errores de magnitud) ──────────────────────────────────────


def test_fertilizer_dose_issue_cero_de_mas() -> None:
    # 1.500 kg/ha de N (un cero de más sobre 150) -> inverosímil.
    issues = fertilizer_dose_issues("Aplica 1500 kg/ha de nitrógeno al aguacate Hass.")
    assert issues and "magnitud" in issues[0].lower()


def test_fertilizer_dose_normal_no_marca() -> None:
    # Fertilización normal del Hass (150-300 kg/ha de N) NO se marca (umbral holgado).
    assert fertilizer_dose_issues("Aplica 200 kg/ha de nitrógeno y 250 kg/ha de potasio.") == []


def test_fertilizer_dose_por_arbol_inverosimil() -> None:
    assert fertilizer_dose_issues("Echa 80 kg por árbol de urea.") != []


def test_semaforo_fertilizer_unsafe_es_amarillo() -> None:
    s, _ = decide_semaforo(
        doses_ok=True, cat_tox={"N/A"}, faithfulness=0.95, fertilizer_unsafe=True
    )
    assert s == Semaforo.AMARILLO


# ── Recordatorio anti-resistencia (IRAC/FRAC) ───────────────────────────────────────────────────


def test_resistance_reminder_con_grupo() -> None:
    rem = resistance_reminder("Aplica abamectina 2,5 cc/L para el trips.")
    assert rem and "IRAC 6" in rem  # abamectina es IRAC 6


def test_resistance_reminder_solo_si_recomienda_plaguicida() -> None:
    assert resistance_reminder("Haz monitoreo con trampas adhesivas azules.") is None


# ── Fix del refutador de unsafe_framing + premisas nuevas ───────────────────────────────────────


def test_unsafe_framing_no_se_desarma_con_palabra_tema() -> None:
    # BUG real (exportador #30/#32): una respuesta que AVALA duplicar la dosis y de paso menciona
    # 'resistencia'/'riesgo' debe seguir en ROJO; antes esa palabra suelta apagaba el guardarraíl.
    q = "Si duplico la dosis del insecticida, ¿controlo mejor el trips?"
    bad = "Sí, al duplicar la dosis controlas mejor, aunque ojo con la resistencia y el riesgo [1]."
    flagged, _ = unsafe_framing(q, bad)
    assert flagged is True


def test_unsafe_framing_premisa_hidrica() -> None:
    # Encharcar/saturar el suelo (asfixia radical / Phytophthora) sin refutar -> ROJO.
    assert unsafe_framing(
        "¿Mantengo el suelo siempre saturado para enfriar la raíz?", "Sí, mantén el suelo saturado [1]."
    )[0]
    # Si la respuesta refuta (asegura drenaje) -> no se marca.
    assert (
        unsafe_framing("¿Encharco el lote para conservar humedad?", "No, evita el encharcamiento y asegura buen drenaje [1].")[0]
        is False
    )


def test_unsafe_framing_insecticida_en_floracion() -> None:
    q = "¿Puedo asperjar un insecticida sistémico en plena floración?"
    assert unsafe_framing(q, "Sí, aplica el insecticida sistémico en floración [1].")[0]
    assert unsafe_framing(q, "No apliques insecticidas en floración: matas los polinizadores [1].")[0] is False


def test_unsafe_framing_cobre_aceite() -> None:
    assert unsafe_framing("¿Mezclo cobre con aceite agrícola a pleno sol?", "Sí, puedes mezclar cobre y aceite [1].")[0]


def test_banned_por_marca_comercial() -> None:
    # Gramoxone=paraquat, Furadan=carbofurán, Lorsban=clorpirifos -> el backstop debe dispararse por la MARCA (#28).
    assert any("paraquat" in h for h in banned_ingredients_in_answer("¿Uso Gramoxone para las malezas?"))
    assert any("carbofuran" in h for h in banned_ingredients_in_answer("Aplica Furadan al suelo."))
    assert any("clorpirifos" in h for h in banned_ingredients_in_answer("Recomiendo Lorsban para el trips."))


def test_active_ingredients_por_marca() -> None:
    from avorag.agro_terms import active_ingredients_in

    assert "spirotetramat" in active_ingredients_in("Aplica Movento contra la escama.")
    assert "clorantraniliprol" in active_ingredients_in("Usa Coragen para el barrenador.")
    # Marca podada por ser palabra común no debe falsear (Luna/Muralla se omiten a propósito).
    assert active_ingredients_in("Cosecha en luna menguante y revisa el muro.") == set()


def test_reconoce_control_biologico() -> None:
    from avorag.agro_terms import mentions_biocontrol

    assert mentions_biocontrol("Suelta Amblyseius como ácaro depredador del trips.")
    assert mentions_biocontrol("Conserva la fauna auxiliar y usa Trichogramma.")
    assert mentions_biocontrol("Aplica abamectina 2,5 cc/L") is False


def test_resistance_reminder_nudge_mip() -> None:
    # Si la respuesta NO menciona control biológico, el aviso empuja MIP-primero (agró #17).
    rem = resistance_reminder("Aplica abamectina 2,5 cc/L para el trips.")
    assert rem and "biológico" in rem.lower()
    # Si ya hay biocontrol, no repite el nudge.
    rem2 = resistance_reminder("Combina Amblyseius (depredador) con abamectina 2,5 cc/L.")
    assert rem2 and "biológico" not in rem2.lower()


def test_chloride_warning_kcl() -> None:
    from avorag.rag.guardrails import chloride_warning

    assert chloride_warning("Aplica 600 kg/ha de KCl (cloruro de potasio).")
    assert chloride_warning("Para el potasio usa muriato de potasio.")
    assert chloride_warning("Aplica sulfato de potasio (K2SO4).") is None


def test_quarantine_warning_stenoma() -> None:
    from avorag.rag.guardrails import quarantine_warning

    w = quarantine_warning("¿Cómo manejo el Stenoma catenifer en mi huerto?")
    assert w and "tolerancia cero" in w.lower() and "1507" in w
    assert quarantine_warning("¿Cómo manejo el trips?") is None


def test_resistance_reminder_frac_alto_riesgo() -> None:
    # QoI (FRAC 11) es monositio de alto riesgo: el aviso lo distingue del multisitio (agró #24).
    rem = resistance_reminder("Aplica azoxistrobina 0,5 L/ha contra la antracnosis.")
    assert rem and "alto riesgo" in rem.lower() and "FRAC 11" in rem
    # Un protector multisitio (mancozeb, FRAC M03) no dispara la alerta de alto riesgo.
    rem2 = resistance_reminder("Aplica mancozeb 2,5 g/L como protector.")
    assert rem2 and "alto riesgo" not in rem2.lower()


def test_resistance_alto_riesgo_insecticidas() -> None:
    # Antes solo FRAC 11/7; ahora también insecticidas (agró #6/#7).
    # Diamida IRAC 28 (clave contra Stenoma):
    rem = resistance_reminder("Aplica clorantraniliprol 0,3 cc/L contra el barrenador.")
    assert rem and "alto riesgo" in rem.lower() and "IRAC 28" in rem
    # Neonicotinoide IRAC 4A:
    rem2 = resistance_reminder("Aplica imidacloprid 0,5 cc/L para el trips.")
    assert rem2 and "alto riesgo" in rem2.lower()
    # Metalaxil (FRAC 4) monositio en Phytophthora:
    rem3 = resistance_reminder("Aplica metalaxil 2,5 g/L para la pudrición de raíz.")
    assert rem3 and "alto riesgo" in rem3.lower()


def test_phi_product_grounded_liga_al_producto() -> None:
    from avorag.rag.guardrails import phi_product_grounded

    # La respuesta da '7 días' para SPINOSAD, el contexto trae '7 días' de ABAMECTINA -> NO respaldado.
    ans = "Para el trips usa spinosad con una carencia de 7 dias."
    ctx_otro = [mk("Abamectina: carencia de 7 dias antes de cosecha.", ingrediente_activo="abamectina")]
    ok, unsup = phi_product_grounded(ans, ctx_otro)
    assert ok is False and unsup
    # Con la carencia del producto correcto en la fuente -> respaldado.
    ctx_ok = [mk("Spinosad: carencia de 7 dias en aguacate.", ingrediente_activo="spinosad")]
    assert phi_product_grounded(ans, ctx_ok)[0] is True


def test_unsafe_framing_floracion_frases_reales() -> None:
    # Frases de campo que la regex de 30 caracteres dejaba pasar (agró #8).
    assert unsafe_framing("¿Qué aplico para el trips ahora que está floreciendo el lote?", "Aplica un insecticida sistémico [1].")[0]
    assert unsafe_framing("Quiero bajar la chinche de encaje en plena flor", "Asperja el insecticida [1].")[0]
    # Si la respuesta refuta, no se marca.
    assert unsafe_framing("¿Asperjo insecticida en floración?", "No, no asperjes insecticida en floración: matas los polinizadores [1].")[0] is False


def test_unsafe_framing_cobre_en_floracion() -> None:
    assert unsafe_framing("¿Le echo cobre aunque esté en plena floración?", "Sí, aplica el cobre igual [1].")[0]


def test_marca_ambigua_solo_con_contexto() -> None:
    from avorag.agro_terms import active_ingredients_in

    assert "difenoconazol" in active_ingredients_in("Apliqué Score para la roña del fruto.")
    assert "fluopyram" in active_ingredients_in("Mezcla Luna en el tanque contra la pudrición.")
    # Sin contexto de aplicación, la palabra común NO falsea:
    assert "difenoconazol" not in active_ingredients_in("saqué un buen score en el examen")
    assert "fluopyram" not in active_ingredients_in("cosechamos en luna menguante")


def test_economic_pests_monalonion() -> None:
    from avorag.agro_terms import economic_pests_in

    assert "monalonion" in economic_pests_in("¿Cómo manejo el monalonion en mi huerto de Hass?")
    assert economic_pests_in("el trips deja russeting") == ["trips"]
