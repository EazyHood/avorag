"""Human-in-the-loop (P-2): cola de revisión y firma del agrónomo para respuestas de riesgo.

Arquitectura (docs/ARQUITECTURA_ONLINE.md, P-2): toda respuesta 🔴 (o con recomendación química
accionable) DEBE poder revisarse y firmarse por un ingeniero agrónomo antes de entregarse como
consejo firme. Aquí la cola se DERIVA de la auditoría (`queries` con semáforo rojo aún sin decidir),
así que NO hace falta un paso de "encolado" acoplado al pipeline; y la decisión queda como
`HitlReview` (migración 0005) + se refleja en `QueryLog.review_status`.

Colisión-safe: módulo NUEVO bajo `online/`. Lee `QueryLog` (núcleo) sin modificar su modelo.

Nota de alcance: la firma es un HASH de tamper-evidence (no PKI). Para revisar el TEXTO de la
respuesta, el tenant debe tener `audit_store_text=True` (con False, `queries.answer` es un hash y la
revisión solo ve metadatos); un payload de revisión cifrado aparte es un follow-up.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from avorag.db.models import QueryLog
from avorag.db.models_online import HitlReview
from avorag.rag.schemas import Semaforo

ALLOWED_DECISIONS = frozenset({"approved", "rejected", "edited"})
_PENDING = ("none", "pending", None)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def needs_hitl(semaforo: Semaforo | str) -> bool:
    """True si la respuesta requiere revisión humana (semáforo ROJO)."""
    value = semaforo.value if isinstance(semaforo, Semaforo) else str(semaforo)
    return value == Semaforo.ROJO.value


def decision_signature(query_id, decision: str, reviewer_id: str, edited_text: str | None) -> str:
    """Hash de tamper-evidence de la decisión (no-repudio básico; no es una firma PKI)."""
    blob = json.dumps(
        {"q": str(query_id), "d": decision, "r": reviewer_id, "e": edited_text or ""},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def pending_for_review(session: Session, tenant: str, *, limit: int = 50) -> list[QueryLog]:
    """Consultas 🔴 del tenant aún sin decidir (la cola de revisión, derivada de la auditoría)."""
    stmt = (
        select(QueryLog)
        .where(
            QueryLog.tenant == tenant,
            QueryLog.semaforo == Semaforo.ROJO.value,
            QueryLog.review_status.in_(_PENDING),
        )
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def review_summary(q: QueryLog) -> dict:
    """Resumen citable de una consulta en cola (texto solo si `audit_store_text=True`)."""
    return {
        "query_id": str(q.id),
        "tenant": q.tenant,
        "semaforo": q.semaforo,
        "question": q.question,
        "answer": q.answer,
        "review_status": q.review_status,
        "corpus_version": q.corpus_version,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def submit_decision(
    session: Session,
    *,
    query_id: uuid.UUID,
    reviewer_id: str,
    decision: str,
    edited_text: str | None = None,
    notes: str | None = None,
    now: datetime | None = None,
) -> HitlReview:
    """Registra la decisión del agrónomo: crea el `HitlReview` (con firma) y actualiza `QueryLog`."""
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            f"Decisión inválida «{decision}». Usa: {', '.join(sorted(ALLOWED_DECISIONS))}."
        )
    q = session.scalar(select(QueryLog).where(QueryLog.id == query_id))
    if q is None:
        raise LookupError(f"No existe la consulta {query_id} (o no es de tu tenant).")
    review = HitlReview(
        tenant=q.tenant,
        query_id=q.id,
        reviewer_id=reviewer_id,
        decision=decision,
        edited_text=edited_text,
        notes=notes,
        signature=decision_signature(q.id, decision, reviewer_id, edited_text),
        decided_at=now or _utcnow(),
    )
    q.review_status = decision
    q.reviewer_id = reviewer_id
    session.add(review)
    session.flush()
    return review
