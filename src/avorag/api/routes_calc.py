"""Endpoints de calculadoras agronómicas deterministas (materia seca, encalado, relaciones foliares).

Son cálculos exactos (sin LLM ni recuperación): la misma lógica sirve OFFLINE en el móvil. Validan
la entrada y devuelven el resultado con su nota honesta (umbrales/bandas orientativos)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from avorag import agro_calc
from avorag.logging import get_logger

router = APIRouter(prefix="/api/calc", tags=["calc"])
log = get_logger(__name__)


class DryMatterIn(BaseModel):
    peso_fresco_g: float = Field(..., gt=0, description="Peso de la muestra de pulpa fresca (g).")
    peso_seco_g: float = Field(..., gt=0, description="Peso de la muestra seca a peso constante (g).")
    umbral_pct: float = Field(
        agro_calc.DRY_MATTER_EXPORT_DEFAULT, gt=0, le=100, description="Umbral de corte (%)."
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


class FoliarIn(BaseModel):
    n: float | None = Field(None, gt=0, description="Nitrógeno foliar (% MS).")
    k: float | None = Field(None, gt=0, description="Potasio foliar (% MS).")
    ca: float | None = Field(None, gt=0, description="Calcio foliar (% MS).")
    mg: float | None = Field(None, gt=0, description="Magnesio foliar (% MS).")


@router.post("/materia-seca")
def materia_seca(body: DryMatterIn) -> dict:
    try:
        r = agro_calc.dry_matter(
            body.peso_fresco_g, body.peso_seco_g, umbral_pct=body.umbral_pct
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/encalado")
def encalado(body: LimingIn) -> dict:
    try:
        r = agro_calc.liming_by_al_saturation(
            al=body.al, ca=body.ca, mg=body.mg, k=body.k, na=body.na,
            psa_objetivo_pct=body.psa_objetivo_pct, factor_campo=body.factor_campo,
            prnt_pct=body.prnt_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(r)


@router.post("/relaciones-foliares")
def relaciones_foliares(body: FoliarIn) -> dict:
    try:
        r = agro_calc.foliar_ratios(n=body.n, k=body.k, ca=body.ca, mg=body.mg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "relaciones": {k: asdict(v) for k, v in r.relaciones.items()},
        "nota": r.nota,
    }
