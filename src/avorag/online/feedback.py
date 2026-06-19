"""Feedback del usuario sobre una respuesta (cierra el bucle de eval online).

Escribe en `feedback` (migración 0005, tenant-scoped, RLS fail-closed). Privacidad por diseño (P-4):
el comentario se guarda como **HASH** (SHA-256), nunca en claro. Colisión-safe: módulo NUEVO bajo `online/`.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from avorag.db.models_online import Feedback

ALLOWED_MOTIVOS = frozenset({"incorrecta", "incompleta", "desactualizada", "peligrosa", "otra"})


def _hash(text: str | None) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def submit_feedback(
    session: Session,
    *,
    tenant: str,
    response_id: uuid.UUID,
    util: bool,
    motivo: str | None = None,
    comentario: str | None = None,
    user_ref: str | None = None,
) -> Feedback:
    """Registra el feedback. `comentario` se persiste como hash (P-4). `user_ref` debe venir ya hasheado."""
    if motivo is not None and motivo not in ALLOWED_MOTIVOS:
        raise ValueError(f"Motivo inválido «{motivo}». Usa: {', '.join(sorted(ALLOWED_MOTIVOS))}.")
    fb = Feedback(
        tenant=tenant,
        response_id=response_id,
        util=util,
        motivo=motivo,
        comentario_sha256=_hash(comentario),
        user_ref=user_ref,
    )
    session.add(fb)
    session.flush()
    return fb
