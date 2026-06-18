"""Endpoints de PLATAFORMA del modo ONLINE.

`GET /api/capabilities`: estado por subsistema (modelo fuerte, juez independiente, reranker y cada
feed en vivo) para que el cliente Flutter decida a qué MODO degradar (1 = online-pleno … 4 =
fallback-offline). Ver docs/ARQUITECTURA_ONLINE.md (Parte 1) y docs/contracts/openapi.online.yaml.
"""

from __future__ import annotations

from fastapi import APIRouter

from avorag.online.capabilities import current_capabilities

router = APIRouter(prefix="/api", tags=["platform"])


@router.get("/capabilities")
def capabilities() -> dict:
    """Capacidades del servidor + `mode_hint` (1/2). Los modos 3 (caché) y 4 (offline) los decide el cliente."""
    return current_capabilities()
