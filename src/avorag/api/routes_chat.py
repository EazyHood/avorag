"""Endpoint de consulta del asistente."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from avorag.rag import Answer, answer

router = APIRouter(prefix="/api", tags=["chat"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    # Validados server-side para evitar valores basura/abuso (el aislamiento real
    # por tenant llega con autenticación en la Ruta 🅱️ — ver docs/SECURITY.md).
    tenant: str | None = Field(None, min_length=1, max_length=64, pattern=r"^[a-z0-9_-]+$")
    country: str | None = Field(None, pattern=r"^[A-Z]{2}$")


@router.post("/ask", response_model=Answer)
def ask(req: AskRequest) -> Answer:
    return answer(req.question, tenant=req.tenant, country=req.country)
