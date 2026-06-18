"""Endpoints de PLATAFORMA del modo ONLINE.

- `GET  /api/capabilities`     → estado por subsistema + mode_hint (1/2) para que el cliente degrade.
- `GET  /api/hitl/pending`     → cola de respuestas 🔴 del tenant pendientes de revisión (P-2).
- `POST /api/hitl/decision`    → decisión firmada del agrónomo sobre una respuesta en cola.

Ver docs/ARQUITECTURA_ONLINE.md y docs/contracts/openapi.online.yaml.
Nota: el control de ROL (solo agrónomo-revisor) es un follow-up; hoy basta con auth de tenant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from avorag.api.auth import rate_limit, require_api_key
from avorag.db import get_session
from avorag.online import hitl
from avorag.online.capabilities import current_capabilities

router = APIRouter(prefix="/api", tags=["platform"])


@router.get("/capabilities")
def capabilities() -> dict:
    """Capacidades del servidor + mode_hint (1/2). Los modos 3 (caché) y 4 (offline) los decide el cliente."""
    return current_capabilities()


@router.get("/hitl/pending")
def hitl_pending(
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> dict:
    """Cola de respuestas 🔴 del tenant pendientes de revisión del agrónomo (P-2)."""
    with get_session(tenant=auth_tenant) as session:
        rows = hitl.pending_for_review(session, auth_tenant)
        return {"pending": [hitl.review_summary(r) for r in rows]}


class HitlDecisionIn(BaseModel):
    query_id: str
    reviewer_id: str = Field(..., min_length=1, max_length=64)
    decision: str = Field(..., pattern="^(approved|rejected|edited)$")
    edited_text: str | None = Field(None, max_length=8000)
    notes: str | None = Field(None, max_length=2000)


@router.post("/hitl/decision")
def hitl_decision(
    body: HitlDecisionIn,
    auth_tenant: str = Depends(require_api_key),
    _rl: None = Depends(rate_limit),
) -> dict:
    """Registra la decisión firmada del agrónomo sobre una respuesta en cola."""
    try:
        qid = uuid.UUID(body.query_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="query_id no es un UUID válido.") from exc
    with get_session(tenant=auth_tenant) as session:
        try:
            review = hitl.submit_decision(
                session,
                query_id=qid,
                reviewer_id=body.reviewer_id,
                decision=body.decision,
                edited_text=body.edited_text,
                notes=body.notes,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "id": str(review.id),
            "query_id": body.query_id,
            "decision": review.decision,
            "signature": review.signature,
        }
