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


def test_foliar_un_elemento_da_nivel_absoluto() -> None:
    # Antes exigía 2 macros; ahora un solo valor da su NIVEL absoluto (sin relaciones).
    r = agro_calc.foliar_ratios(n=2.0)
    assert "n" in r.niveles and not r.relaciones
    assert agro_calc.foliar_ratios(n=2.0).niveles["n"].estado == "suficiente"


def test_foliar_sin_datos_rechaza() -> None:
    with pytest.raises(ValueError):
        agro_calc.foliar_ratios()


def test_foliar_detecta_boro_y_zinc_bajos() -> None:
    r = agro_calc.foliar_ratios(b=20.0, zn=15.0)  # ambos por debajo de suficiencia
    assert r.niveles["b"].estado == "deficiente" and r.niveles["zn"].estado == "deficiente"
    assert any("cuajado" in a.lower() or "boro" in a.lower() for a in r.alertas)


def test_foliar_nivel_absoluto_caza_la_doble_deficiencia() -> None:
    # Caso #5/#35: relaciones 'óptimas' pero árbol famélico (todo por debajo de suficiencia).
    r = agro_calc.foliar_ratios(n=0.8, k=0.4, ca=0.4, mg=0.16)
    assert r.relaciones["K/Ca"].estado == "óptimo"  # 0.4/0.4 = 1.0 (proporción ok)
    assert r.niveles["n"].estado == "deficiente" and r.niveles["k"].estado == "deficiente"
    assert r.alertas  # no da falsa tranquilidad


def test_foliar_estres_salino_cl() -> None:
    r = agro_calc.foliar_ratios(k=1.0, cl=0.8)  # Cl > 0.5% -> riesgo de quemado
    assert any("cloruro" in a.lower() or "sal" in a.lower() for a in r.alertas)


# ── Materia seca con muestreo ───────────────────────────────────────────────────────────────────


def test_dry_matter_un_fruto_avisa_muestreo() -> None:
    r = agro_calc.dry_matter(100.0, 24.0)
    assert r.n_muestras == 1
    assert "insuficiente" in r.nota.lower()  # un solo fruto no es muestreo válido


def test_dry_matter_sample_media_y_cv() -> None:
    # Muestra homogénea con todos los frutos ≥ umbral -> apto.
    r = agro_calc.dry_matter_sample([24.0, 24.0, 25.0, 24.0, 23.0, 24.0, 25.0, 24.0, 24.0, 23.0])
    assert r.n_muestras == 10
    assert r.materia_seca_pct == 24.0 and r.cv_pct is not None
    assert r.veredicto == "apto"


def test_dry_matter_brecha_al_umbral() -> None:
    bajo = agro_calc.dry_matter_sample([20.0] * 5, umbral_pct=23.0)
    assert bajo.brecha_pct == 3.0  # faltan 3 puntos
    alto = agro_calc.dry_matter_sample([25.0] * 5, umbral_pct=23.0)
    assert alto.brecha_pct == -2.0  # 2 puntos por encima


def test_foliar_limitante_senala_deficiencia_mas_severa() -> None:
    # Zn mucho más deficiente (15/30=50% del mínimo) que un leve desbalance -> Zn es el limitante.
    r = agro_calc.foliar_ratios(k=1.0, ca=1.0, zn=15.0, b=90.0)
    assert r.limitante and "ZN" in r.limitante
    # Sin deficiencias absolutas pero con relación fuera de banda -> señala la relación.
    r2 = agro_calc.foliar_ratios(k=3.0, ca=1.0)  # K/Ca alto
    assert r2.limitante and "K/Ca" in r2.limitante


def test_dry_matter_sample_heterogeneo_es_limitrofe() -> None:
    # Media supera el umbral pero hay frutos por debajo -> limítrofe (parte del lote no llega).
    r = agro_calc.dry_matter_sample([19.0, 20.0, 28.0, 29.0] * 3, umbral_pct=23.0)
    assert r.veredicto == "limítrofe"
    assert r.minimo_muestra_pct == 19.0


# ── Encalado en andisol ─────────────────────────────────────────────────────────────────────────


def test_encalado_andisol_advierte() -> None:
    r = agro_calc.liming_by_al_saturation(al=2.0, ca=1.0, mg=0.4, k=0.2, densidad_aparente=0.7)
    assert r.advertencia and "andisol" in r.advertencia.lower()


# ── Riego ───────────────────────────────────────────────────────────────────────────────────────


def test_riego_etc_y_volumen() -> None:
    r = agro_calc.irrigation_requirement(eto_mm_dia=5.0, kc=0.8, eficiencia=0.9, area_ha=2.0)
    assert r.etc_mm_dia == 4.0  # 5 * 0.8
    assert r.lamina_bruta_mm_dia == round(4.0 / 0.9, 2)
    assert r.volumen_m3_ha_dia == round(r.lamina_bruta_mm_dia * 10 * 2.0, 1)


def test_riego_descuenta_lluvia() -> None:
    r = agro_calc.irrigation_requirement(eto_mm_dia=5.0, kc=1.0, precip_efectiva_mm_dia=2.0)
    assert r.lamina_neta_mm_dia == 3.0  # 5 - 2


# ── Salinidad ───────────────────────────────────────────────────────────────────────────────────


def test_salinidad_fraccion_lavado_y_sar() -> None:
    r = agro_calc.salinity_assessment(ce_agua_dsm=1.0, na_meq_l=8.0, ca_meq_l=2.0, mg_meq_l=2.0)
    assert r.fraccion_lavado == round(1.0 / (5 * 1.3 - 1.0), 3)
    assert r.sar == round(8.0 / (((2.0 + 2.0) / 2) ** 0.5), 2)


def test_salinidad_agua_muy_salina_alerta() -> None:
    r = agro_calc.salinity_assessment(ce_agua_dsm=3.0)
    assert r.alertas  # CE 3 > umbral 1,3 del Hass


# ── Grados-día / calibre / umbral MIP ───────────────────────────────────────────────────────────


def test_grados_dia_acumula_y_progreso() -> None:
    # 3 días a (20,10): media 15, base 10 -> 5 GDD/día -> 15 acumulados.
    r = agro_calc.growing_degree_days([(20.0, 10.0)] * 3, objetivo_gdd=30.0)
    assert r.gdd_acumulado == 15.0 and r.n_dias == 3
    assert r.progreso_pct == 50.0


def test_grados_dia_no_cuenta_dias_frios() -> None:
    # Día por debajo de la base no resta (GDD del día = 0).
    r = agro_calc.growing_degree_days([(8.0, 4.0)])  # media 6 < base 10
    assert r.gdd_acumulado == 0.0


def test_calibre_por_peso() -> None:
    # Caja de 4 kg: 250 g -> ~16 frutos/caja -> calibre 16.
    r = agro_calc.fruit_caliber(250.0)
    assert r.calibre == 16
    # Fruto más grande -> número de calibre menor.
    assert agro_calc.fruit_caliber(330.0).calibre < 16


def test_umbral_mip_decide() -> None:
    r = agro_calc.mip_action_threshold(40, 10, 3.0, unidad="trampa")  # media 4 >= 3
    assert r.media_por_unidad == 4.0 and r.decision == "intervenir"
    r2 = agro_calc.mip_action_threshold(10, 10, 3.0)  # media 1 < 3
    assert r2.decision == "monitorear"


def test_dry_matter_objetivo_por_mercado() -> None:
    assert agro_calc.resolve_dry_matter_target("premium") == 25.0
    assert agro_calc.resolve_dry_matter_target(None) == 23.0
    with pytest.raises(ValueError):
        agro_calc.resolve_dry_matter_target("inexistente")


def test_api_materia_seca_objetivo_premium() -> None:
    r = _client().post(
        "/api/calc/materia-seca", json={"muestras": [24, 24, 24, 24, 24], "objetivo": "premium"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["umbral_pct"] == 25.0 and body["veredicto"] == "limítrofe"  # 24 < 25 (premium)


def test_api_grados_dia_calibre_umbral() -> None:
    c = _client()
    r = c.post("/api/calc/grados-dia", json={"temps": [[20, 10], [22, 12]], "objetivo_gdd": 100})
    assert r.status_code == 200 and r.json()["gdd_acumulado"] > 0
    r = c.post("/api/calc/calibre", json={"peso_g": 250})
    assert r.status_code == 200 and r.json()["calibre"] == 16
    r = c.post("/api/calc/umbral-mip", json={"conteo_total": 40, "n_unidades": 10, "umbral": 3})
    assert r.status_code == 200 and r.json()["decision"] == "intervenir"


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
    r = _client().post("/api/calc/encalado", json={"al": 2.0, "ca": 3.0, "mg": 1.0, "k": 0.4})
    assert r.status_code == 200
    assert r.json()["requiere_encalado"] is True


def test_api_relaciones_foliares_ok() -> None:
    r = _client().post("/api/calc/relaciones-foliares", json={"k": 1.0, "ca": 1.0})
    assert r.status_code == 200
    assert "K/Ca" in r.json()["relaciones"]


def test_api_foliar_con_boro_zinc() -> None:
    r = _client().post("/api/calc/relaciones-foliares", json={"b": 20, "zn": 15})
    assert r.status_code == 200
    body = r.json()
    assert body["niveles"]["b"]["estado"] == "deficiente"
    assert body["alertas"]
    assert body["limitante"]  # el factor limitante se expone en la respuesta de la API


def test_api_materia_seca_muestras() -> None:
    r = _client().post(
        "/api/calc/materia-seca", json={"muestras": [22, 23, 24, 25, 23], "umbral_pct": 23}
    )
    assert r.status_code == 200
    assert r.json()["n_muestras"] == 5


def test_api_riego_ok() -> None:
    r = _client().post("/api/calc/riego", json={"eto_mm_dia": 5, "kc": 0.8, "area_ha": 2})
    assert r.status_code == 200
    assert r.json()["etc_mm_dia"] == 4.0


def test_api_salinidad_ok() -> None:
    r = _client().post("/api/calc/salinidad", json={"ce_agua_dsm": 1.0})
    assert r.status_code == 200
    assert r.json()["fraccion_lavado"] is not None


# ── Cluster B: GDD seno vs media, salinidad RSC/portainjerto, riego balance, calibre muestra ──────


def test_gdd_seno_vs_media_noche_fria() -> None:
    # Noche fría (Tmin < T_base): el promedio simple INFRAESTIMA porque la noche fría arrastra hacia
    # abajo el calor del día; el seno simple solo anula el tramo bajo la base y acumula MÁS GDD.
    temps = [(20.0, 5.0)] * 10  # Tmin 5 < base 10, Tmax 20 > base
    seno = agro_calc.growing_degree_days(temps, metodo="seno")
    media = agro_calc.growing_degree_days(temps, metodo="media")
    assert seno.metodo == "seno"
    assert seno.gdd_acumulado > media.gdd_acumulado  # corrige el sesgo de noche fría


def test_gdd_metodos_coinciden_sin_noche_fria() -> None:
    # Si Tmin >= T_base ambos métodos dan lo mismo.
    temps = [(25.0, 15.0)] * 5
    seno = agro_calc.growing_degree_days(temps, metodo="seno")
    media = agro_calc.growing_degree_days(temps, metodo="media")
    assert seno.gdd_acumulado == media.gdd_acumulado


def test_gdd_metodo_invalido() -> None:
    with pytest.raises(ValueError):
        agro_calc.growing_degree_days([(20.0, 10.0)], metodo="lineal")


def test_salinidad_portainjerto_ajusta_umbral() -> None:
    mex = agro_calc.salinity_assessment(ce_agua_dsm=1.2, portainjerto="mexicano")
    ant = agro_calc.salinity_assessment(ce_agua_dsm=1.2, portainjerto="antillano")
    assert mex.ce_umbral_suelo_dsm == 1.0  # raza mexicana: más sensible
    assert ant.ce_umbral_suelo_dsm == 2.0  # antillano: más tolerante
    # Con el mismo agua, el mexicano la supera y el antillano no.
    assert any("supera el umbral" in a for a in mex.alertas)
    assert not any("supera el umbral" in a for a in ant.alertas)


def test_salinidad_rsc_bicarbonatos() -> None:
    # HCO3 alto frente a Ca+Mg bajo -> RSC alto -> agua no apta sin enmienda.
    r = agro_calc.salinity_assessment(ce_agua_dsm=0.8, ca_meq_l=1.0, mg_meq_l=0.5, hco3_meq_l=5.0)
    assert r.rsc_meq_l == 3.5  # (5+0) - (1+0.5)
    assert any("RSC" in a for a in r.alertas)


def test_riego_fraccion_lavado_sube_bruta() -> None:
    sin = agro_calc.irrigation_requirement(eto_mm_dia=5, kc=0.8)
    con = agro_calc.irrigation_requirement(eto_mm_dia=5, kc=0.8, fraccion_lavado=0.2)
    assert con.lamina_bruta_mm_dia > sin.lamina_bruta_mm_dia  # el lavado exige más lámina


def test_riego_balance_suelo_intervalo() -> None:
    r = agro_calc.irrigation_requirement(
        eto_mm_dia=5,
        kc=0.8,
        capacidad_campo_pct=30,
        pmp_pct=15,
        densidad_aparente=1.2,
        profundidad_radical_cm=40,
    )
    assert r.taw_mm is not None and r.raw_mm is not None
    assert r.intervalo_riego_dias is not None
    assert r.raw_mm < r.taw_mm  # RAW = p·TAW con p<1


def test_kc_aguacate_por_etapa() -> None:
    assert agro_calc.kc_aguacate("llenado") > agro_calc.kc_aguacate("reposo")
    with pytest.raises(ValueError):
        agro_calc.kc_aguacate("inexistente")


def test_foliar_micro_contaminacion() -> None:
    # Fe foliar alto -> alerta de posible contaminación superficial (no clorosis).
    r = agro_calc.foliar_ratios(fe=500)
    assert any("contamina" in a.lower() or "residuo" in a.lower() for a in r.alertas)


def test_calibre_muestra_distribucion() -> None:
    pesos = [200, 205, 210, 195, 400]  # 4 frutos ~calibre similar + 1 grande
    r = agro_calc.fruit_caliber_sample(pesos)
    assert r.n == 5
    assert sum(r.distribucion.values()) == 5
    assert r.calibre_dominante in r.distribucion


def test_calibre_muestra_heterogeneo_alerta() -> None:
    pesos = [150, 300, 600, 200, 450]  # muy disperso
    r = agro_calc.fruit_caliber_sample(pesos)
    assert r.homogeneidad_pct < 70
    assert "heterog" in r.nota.lower()


def test_calibre_muestra_vacio() -> None:
    with pytest.raises(ValueError):
        agro_calc.fruit_caliber_sample([])


def test_materia_seca_nota_aceite() -> None:
    r = agro_calc.dry_matter_sample([23, 24, 23, 25])
    assert "aceite" in r.nota.lower()


# ── Cluster B: API de los nuevos parámetros ──────────────────────────────────────────────────────


def test_api_riego_por_etapa() -> None:
    r = _client().post("/api/calc/riego", json={"eto_mm_dia": 5, "etapa": "llenado"})
    assert r.status_code == 200
    assert r.json()["etc_mm_dia"] == 4.0  # 5 * 0.8


def test_api_riego_sin_kc_ni_etapa() -> None:
    r = _client().post("/api/calc/riego", json={"eto_mm_dia": 5})
    assert r.status_code == 400


def test_api_grados_dia_metodo() -> None:
    r = _client().post("/api/calc/grados-dia", json={"temps": [[20, 5], [20, 5]], "metodo": "seno"})
    assert r.status_code == 200
    assert r.json()["metodo"] == "seno"


def test_api_salinidad_portainjerto() -> None:
    r = _client().post("/api/calc/salinidad", json={"ce_agua_dsm": 1.2, "portainjerto": "mexicano"})
    assert r.status_code == 200
    assert r.json()["ce_umbral_suelo_dsm"] == 1.0


def test_api_calibre_muestra() -> None:
    r = _client().post("/api/calc/calibre-muestra", json={"pesos_g": [200, 210, 205, 195]})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 4
    assert "calibre_dominante" in body


# ── Cluster B: fraccionamiento de nitrógeno ──────────────────────────────────────────────────────


def test_nitrogeno_reparto_por_defecto() -> None:
    r = agro_calc.nitrogen_split(100.0)
    assert abs(sum(r.reparto_kg_ha.values()) - 100.0) < 0.5  # reparte el total
    assert abs(sum(r.reparto_pct.values()) - 100.0) < 0.5
    assert r.n_arbol_g is None


def test_nitrogeno_g_por_arbol() -> None:
    r = agro_calc.nitrogen_split(100.0, arboles_por_ha=400)
    assert r.n_arbol_g is not None
    # 100 kg/ha · 0.25 (cuaje) · 1000 / 400 = 62.5 g/árbol
    assert r.n_arbol_g["cuaje"] == 62.5


def test_nitrogeno_alerta_floracion_alta() -> None:
    r = agro_calc.nitrogen_split(100.0, fracciones={"floracion": 0.5, "cuaje": 0.5})
    assert any("floración" in a.lower() for a in r.alertas)


def test_nitrogeno_normaliza_fracciones() -> None:
    # Fracciones que no suman 1 se normalizan.
    r = agro_calc.nitrogen_split(100.0, fracciones={"cuaje": 2, "llenado": 2})
    assert r.reparto_kg_ha["cuaje"] == 50.0


def test_nitrogeno_fracciones_invalidas() -> None:
    with pytest.raises(ValueError):
        agro_calc.nitrogen_split(100.0, fracciones={"cuaje": 0})


def test_api_nitrogeno() -> None:
    r = _client().post("/api/calc/nitrogeno", json={"n_total_kg_ha": 120, "arboles_por_ha": 400})
    assert r.status_code == 200
    body = r.json()
    assert "reparto_kg_ha" in body
    assert body["n_arbol_g"] is not None
