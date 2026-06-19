"""Control de ROL para acciones sensibles del modo online (p. ej. firmar una decisión HITL).

Minimalista a propósito (no es un RBAC completo, que es follow-up): una ALLOWLIST de revisores
configurada por entorno. Patrón coherente con el auth del repo (sin claves ⇒ modo abierto de dev):
- `AVORAG_HITL_REVIEWERS` vacío  → sin restricción (dev/single-tenant).
- `AVORAG_HITL_REVIEWERS=a,b,c`  → solo esos `reviewer_id` pueden firmar decisiones HITL.

Colisión-safe: módulo NUEVO bajo `online/`. No edita `api/auth.py` (núcleo).
"""

from __future__ import annotations

import os


def reviewers() -> set[str]:
    """Allowlist de agrónomos-revisores autorizados (de `AVORAG_HITL_REVIEWERS`). Vacío ⇒ sin restricción."""
    raw = os.getenv("AVORAG_HITL_REVIEWERS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_reviewer(reviewer_id: str) -> bool:
    """True si `reviewer_id` puede firmar decisiones HITL. Allowlist vacía ⇒ se permite (modo dev)."""
    allow = reviewers()
    return (not allow) or (reviewer_id in allow)
