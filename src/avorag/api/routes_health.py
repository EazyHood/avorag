"""Endpoints de salud y readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from avorag import __version__
from avorag.db import get_engine
from avorag.logging import get_logger

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/ready")
def ready() -> dict:
    """Comprueba conectividad con la base de datos sin exponer detalles internos."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception as exc:
        # No filtrar la traza/URL al cliente; registrar internamente.
        log.error("readiness_db_check_failed", error=str(exc))
        return {"status": "degraded", "db": "unavailable"}
