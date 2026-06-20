"""Endpoints de consulta del asistente (respuesta directa y en streaming)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from avorag.api.auth import rate_limit, require_api_key
from avorag.config import get_settings
from avorag.markets import SUPPORTED_MARKETS, normalize_market
from avorag.rag import Answer, answer, answer_stream

router = APIRouter(prefix="/api", tags=["chat"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    # En prod el tenant viene del API key, no del body.
    tenant: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    soil_type: str | None = Field(None, max_length=64)  # arenoso, arcilloso, franco…
    region: str | None = Field(None, max_length=80)
    # Mercado de DESTINO para el guardarraíl de LMR/tolerancias en vivo. Se acepta cualquier grafía
    # soportada (ue/eeuu y alias us/usa/estados_unidos/EE.UU./union_europea…) y se CANONIZA en backend a
    # {ue, eeuu} (DRY con el núcleo, vía markets); una grafía sin cobertura da 422 (no se acepta en
    # silencio un destino sin feed de residuo). El guardarraíl online solo actúa si AVORAG_ONLINE_FEEDS
    # está activo; sin `export_market` en el request, se usa EXPORT_MARKET de la config.
    export_market: str | None = Field(None, max_length=40)

    @field_validator("export_market", mode="after")
    @classmethod
    def _canonize_market(cls, v: str | None) -> str | None:
        """Canoniza el mercado a su clave soportada o devuelve None (vacío). Grafía no soportada → 422."""
        if v is None or not v.strip():
            return None
        canon = normalize_market(v)
        if canon not in SUPPORTED_MARKETS:
            soportados = ", ".join(sorted(SUPPORTED_MARKETS))
            raise ValueError(
                f"export_market no soportado: {v!r} (soportados: {soportados}; "
                "alias: us/usa/estados_unidos→eeuu, eu/europa/union_europea→ue)."
            )
        return canon


def _tenant_for(req: AskRequest, auth_tenant: str) -> str:
    return auth_tenant if get_settings().api_keys else (req.tenant or auth_tenant)


@router.post("/ask", response_model=Answer)
def ask(
    req: AskRequest,
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> Answer:
    return answer(
        req.question,
        tenant=_tenant_for(req, auth_tenant),
        country=req.country,
        soil_type=req.soil_type,
        region=req.region,
        export_market=req.export_market,
    )


@router.post("/ask/stream")
def ask_stream(
    req: AskRequest,
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> StreamingResponse:
    """Respuesta en streaming (SSE): emite el texto a medida que se genera y, al final, un
    evento con el Answer completo (semáforo, citas, guardarraíles)."""
    tenant = _tenant_for(req, auth_tenant)

    def events():
        try:
            for kind, payload in answer_stream(
                req.question,
                tenant=tenant,
                country=req.country,
                soil_type=req.soil_type,
                region=req.region,
                export_market=req.export_market,
            ):
                if kind == "delta":
                    yield f"data: {json.dumps({'type': 'delta', 't': payload})}\n\n"
                elif kind == "reset":
                    yield 'data: {"type": "reset"}\n\n'
                elif kind == "verifying":
                    yield 'data: {"type": "verifying"}\n\n'
                else:
                    body = json.dumps({"type": "final", "answer": payload.model_dump()})
                    yield f"data: {body}\n\n"
        except Exception as exc:  # noqa: BLE001 — comunicar el error al cliente, no romper el stream
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
