"""Endpoint de consulta del asistente."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from avorag.api.auth import rate_limit, require_api_key
from avorag.config import get_settings
from avorag.rag import Answer, answer

router = APIRouter(prefix="/api", tags=["chat"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    # En modo autenticado el tenant se deriva del API key (no del body). El campo se conserva
    # solo para el modo desarrollo (sin api_keys).
    tenant: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    # Contexto de la finca: afina la recomendación (sobre todo de fertilización).
    soil_type: str | None = Field(None, max_length=64)  # p.ej. arenoso, arcilloso, franco
    region: str | None = Field(None, max_length=80)  # p.ej. Quindío, Antioquia


@router.post("/ask", response_model=Answer)
def ask(
    req: AskRequest,
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> Answer:
    # Con autenticación activa, el tenant viene del token; nunca se confía en el del body.
    effective_tenant = auth_tenant if get_settings().api_keys else (req.tenant or auth_tenant)
    return answer(
        req.question,
        tenant=effective_tenant,
        country=req.country,
        soil_type=req.soil_type,
        region=req.region,
    )
