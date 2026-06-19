"""Modelos ORM del MODO ONLINE — tablas creadas por la migración 0005.

Archivo SEPARADO de `db/models.py` (núcleo compartido) para no colisionar con el trabajo paralelo
del modo offline. Reutiliza el mismo `Base`/metadata, así que estos modelos quedan registrados al
importar este módulo (lo hacen los servicios online; NO se auto-importa desde `db/__init__.py` para
no forzar su DDL en entornos sin PostgreSQL).

Tablas (ver `migrations/versions/0005_online_feeds_norms_hitl.py` y `docs/contracts/schema_online.sql`):
- FeedSnapshot  → feed_snapshots (GLOBAL): snapshots versionados de feeds en vivo (frescura P-5).
- NormTable     → norm_tables    (GLOBAL): normas/umbrales versionados de las calculadoras.
- HitlReview    → hitl_reviews   (tenant-scoped, RLS fail-closed): revisión/firma del agrónomo (P-2).
- Feedback      → feedback       (tenant-scoped, RLS fail-closed): feedback del usuario (HASH, P-4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from avorag.db.models import Base  # mismo metadata que el núcleo


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FeedSnapshot(Base):
    """Snapshot versionado de un feed en vivo (ICA/IDEAM/LMR-UE/40CFR/precios). GLOBAL (sin RLS)."""

    __tablename__ = "feed_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    feed_name: Mapped[str] = mapped_column(String(32))  # CHECK en la migración
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # fecha-de-dato de la fuente
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ttl_seconds: Mapped[int] = mapped_column(Integer)  # SLA de frescura
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|stale|error
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class NormTable(Base):
    """Norma/umbral versionado de las calculadoras (mueve los hardcoded a datos). GLOBAL (sin RLS)."""

    __tablename__ = "norm_tables"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    norm_key: Mapped[str] = mapped_column(String(64))  # foliar_suficiencia, ce_umbral_portainjerto…
    norm_version: Mapped[str] = mapped_column(String(32))
    scope: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # {mercado,cultivar,portainjerto,laboratorio,pais}
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    fuente: Mapped[str | None] = mapped_column(Text, nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class HitlReview(Base):
    """Revisión/firma del agrónomo (P-2). Tenant-scoped → RLS fail-closed (migración 0005)."""

    __tablename__ = "hitl_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("queries.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(16))  # pending|approved|rejected|edited
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)  # no-repudio (hash firmado)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
    """Feedback del usuario sobre una respuesta. Tenant-scoped → RLS fail-closed. Comentario por HASH (P-4)."""

    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    response_id: Mapped[uuid.UUID] = mapped_column(Uuid)  # correlaciona con queries.response_id
    util: Mapped[bool] = mapped_column(Boolean)
    motivo: Mapped[str | None] = mapped_column(String(16), nullable=True)  # incorrecta|incompleta|…
    comentario_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_ref: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # id de usuario hasheado
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
