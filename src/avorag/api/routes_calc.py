"""Endpoints de calculadoras agronómicas deterministas.

Materia seca (con muestreo), encalado por Al (con densidad/andisol), diagnóstico foliar (relaciones +
niveles absolutos + estrés salino), riego (ETc=ETo·Kc) y salinidad (fracción de lavado + SAR). Son
cálculos exactos (sin LLM ni recuperación): la misma lógica sirve OFFLINE en el móvil."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from avorag import agro_calc
from avorag.logging import get_logger

router = APIRouter(prefix="/api/calc", tags=["calc"])
log = get_logger(__name__)


def _asdict_ratios(d: dict) -> dict:
    return {k: asdict(v) for k, v in d.items()}


class DryMatterIn(BaseModel):
    peso_fresco_g: float | None = Field(None, gt=0, description="Peso de pulpa fresca (g), para 1 fruto.")
    peso_seco_g: float | None = Field(None, gt=0, description="Peso seco a peso constante (g), para 1 fruto.")
    muestras: list[float] | None = Field(
        None, description="%MS por fruto (muestreo de 10-20 frutos). Si se da, prevalece sobre los pesos."
    )
    umbral_pct: float | None = Field(None, gt=0, le=100, description="Umbral de corte (%); por defecto 23.")
    objetivo: str | None = Field(
        None, description="Objetivo nombrado: minimo_legal | exportacion | premium (si se da, fija el umbral)."
    )


class LimingIn(BaseModel):
    al: float = Field(..., ge=0, description="Aluminio intercambiable (cmol+/kg).")
    ca: float = Field(..., ge=0, description="Calcio (cmol+/kg).")
    mg: float = Field(..., ge=0, description="Magnesio (cmol+/kg).")
    k: float = Field(..., ge=0, description="Potasio (cmol+/kg).")
    na: float = Field(0.0, ge=0, description="Sodio (cmol+/kg), opcional.")
    psa_objetivo_pct: float = Field(agro_calc.AL_SAT_TARGET_DEFAULT, ge=0, le=100)
    factor_campo: float = Field(agro_calc.LIME_FIELD_FACTOR_DEFAULT, gt=0)
    prnt_pct: float = Field(100.0, gt=0, le=100)
    densidad_aparente: float | None = Field(None, gt=0, description="Densidad aparente (g/cm³). <1,0 ⇒ andisol.")
    profundidad_cm: float = Field(20.0, gt=0, description="Profundidad de incorporación (cm).")


class FoliarIn(BaseModel):
    n: float | None = Field(None, ge=0, description="Nitrógeno (% MS).")
    p: float | None = Field(None, ge=0, description="Fósforo (% MS).")
    k: float | None = Field(None, ge=0, description="Potasio (% MS).")
    ca: float | None = Field(None, ge=0, description="Calcio (% MS).")
    mg: float | None = Field(None, ge=0, description="Magnesio (% MS).")
    s: float | None = Field(None, ge=0, description="Azufre (% MS).")
    b: float | None = Field(None, ge=0, description="Boro (ppm).")
    zn: float | None = Field(None, ge=0, description="Zinc (ppm).")
    fe: float | None = Field(None, ge=0, description="Hierro (ppm).")
    mn: float | None = Field(None, ge=0, description="Manganeso (ppm).")
    cu: float | None = Field(None, ge=0, description="Cobre (ppm).")
    cl: float | None = Field(None, ge=0, description="Cloruro (% MS).")
    na: float | None = Field(None, ge=0, description="Sodio (% MS).")


class IrrigationIn(BaseModel):
    eto_mm_dia: float = Field(..., ge=0, description="Evapotranspiración de referencia (mm/día).")
    kc: float = Field(..., gt=0, description="Coeficiente de cultivo (etapa fenológica).")
    precip_efectiva_mm_dia: float = Field(0.0, ge=0, description="Lluvia efectiva (mm/día).")
    eficiencia: float = Field(0.9, gt=0, le=1, description="Eficiencia del sistema de riego (0-1).")
    area_ha: float | None = Field(None, gt=0, description="Área (ha) para calcular volumen.")


class SalinityIn(BaseModel):
    ce_agua_dsm: float = Field(..., ge=0, description="Conductividad eléctrica del agua (dS/m).")
    ce_umbral_suelo_dsm: float = Field(agro_calc.HASS_CE_THRESHOLD_DSM, gt=0, description="CEe umbral del Hass.")
    na_meq_l: float | None = Field(None, ge=0, description="Sodio del agua (meq/L), para SAR.")
    ca_meq_l: float | None = Field(None, ge=0, description="Calcio del agua (meq/L), para SAR.")
    mg_meq_l: float | None = Field(None, ge=0, description="Magnesio del agua (meq/L), para SAR.")


class GddIn(BaseModel):
    temps: list[tuple[float, float]] = Field(..., description="Lista de (Tmax, Tmin) diarias desde cuaje.")
    t_base: float = Field(agro_calc.AVOCADO_TBASE_DEFAULT, description="Temperatura base (°C).")
    t_tope: float | None = Field(None, description="Tope superior opcional (°C).")
    objetivo_gdd: float | None = Field(None, gt=0, description="GDD objetivo (para % de progreso).")


class CaliberIn(BaseModel):
    peso_g: float = Field(..., gt=0, description="Peso del fruto (g).")
    caja_kg: float = Field(4.0, gt=0, description="Peso de la caja de referencia (kg). UE = 4.")


class MipThresholdIn(BaseModel):
    conteo_total: float = Field(..., ge=0, description="Conteo total observado (suma de las unidades).")
    n_unidades: int = Field(..., gt=0, description="Número de unidades de monitoreo (trampas/plantas).")
    umbral: float = Field(..., ge=0, description="Umbral de acción por unidad (de TU protocolo).")
    unidad: str = Field("trampa", description="Unidad de monitoreo (trampa/planta/rama).")


@router.post("/materia-seca")
def materia_seca(body: DryMatterIn) -> dict:
    try:
        umbral = body.umbral_pct if body.umbral_pct is not None else agro_calc.resolve_dry_matter_target(body.objetivo)
        if body.muestras:
            r = agro_calc.dry_matter_sample(body.muestras, umbral_pct=umbral)
        elif body.peso_fresco_g and body.peso_seco_g:
            r = agro_calc.dry_matter(body.peso_fresco_g, body.peso_seco_g, umbral_pct=umbral)
        else:
            raise ValueError("Aporta `muestras` (%MS por fruto) o `peso_fresco_g` + `peso_seco_g`.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/encalado")
def encalado(body: LimingIn) -> dict:
    try:
        r = agro_calc.liming_by_al_saturation(
            al=body.al, ca=body.ca, mg=body.mg, k=body.k, na=body.na,
            psa_objetivo_pct=body.psa_objetivo_pct, factor_campo=body.factor_campo,
            prnt_pct=body.prnt_pct, densidad_aparente=body.densidad_aparente,
            profundidad_cm=body.profundidad_cm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/relaciones-foliares")
def relaciones_foliares(body: FoliarIn) -> dict:
    try:
        r = agro_calc.foliar_ratios(
            n=body.n, p=body.p, k=body.k, ca=body.ca, mg=body.mg, s=body.s,
            b=body.b, zn=body.zn, fe=body.fe, mn=body.mn, cu=body.cu, cl=body.cl, na=body.na,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "relaciones": _asdict_ratios(r.relaciones),
        "niveles": _asdict_ratios(r.niveles),
        "alertas": r.alertas,
        "nota": r.nota,
    }


@router.post("/riego")
def riego(body: IrrigationIn) -> dict:
    try:
        r = agro_calc.irrigation_requirement(
            eto_mm_dia=body.eto_mm_dia, kc=body.kc, precip_efectiva_mm_dia=body.precip_efectiva_mm_dia,
            eficiencia=body.eficiencia, area_ha=body.area_ha,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/salinidad")
def salinidad(body: SalinityIn) -> dict:
    try:
        r = agro_calc.salinity_assessment(
            ce_agua_dsm=body.ce_agua_dsm, ce_umbral_suelo_dsm=body.ce_umbral_suelo_dsm,
            na_meq_l=body.na_meq_l, ca_meq_l=body.ca_meq_l, mg_meq_l=body.mg_meq_l,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/grados-dia")
def grados_dia(body: GddIn) -> dict:
    try:
        r = agro_calc.growing_degree_days(
            [tuple(t) for t in body.temps], t_base=body.t_base, t_tope=body.t_tope,
            objetivo_gdd=body.objetivo_gdd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/calibre")
def calibre(body: CaliberIn) -> dict:
    try:
        r = agro_calc.fruit_caliber(body.peso_g, caja_kg=body.caja_kg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/umbral-mip")
def umbral_mip(body: MipThresholdIn) -> dict:
    try:
        r = agro_calc.mip_action_threshold(
            body.conteo_total, body.n_unidades, body.umbral, unidad=body.unidad
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)
