"""Modelos SQLAlchemy 2.0. Multi-tenant desde el día 1 (columna `tenant`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from avorag.config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Document(Base):
    """Un documento fuente del corpus (PDF, ficha, etiqueta…)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    fuente: Mapped[str] = mapped_column(String(256))  # nombre oficial citable
    titulo: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pais: Mapped[str] = mapped_column(String(2), default="CO")
    cultivo: Mapped[str] = mapped_column(String(64), default="hass")
    licencia: Mapped[str] = mapped_column(String(128), default="por-verificar")
    nivel_autoridad: Mapped[str] = mapped_column(String(64), default="oficial-regulador")
    fecha_publicacion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    raw_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    corpus_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # descarga directa
    doi: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    """Fragmento vectorizado de un documento, con su metadata citable."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    pagina: Mapped[int | None] = mapped_column(Integer, nullable=True)

    content: Mapped[str] = mapped_column(Text)
    # Contexto antepuesto (Contextual Retrieval de Anthropic) — mejora recuperación.
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    # Búsqueda léxica BM25-like en español (columna generada + índice GIN en la migración).
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('spanish', coalesce(context,'') || ' ' || content)",
            persisted=True,
        ),
    )

    # Metadata rica para geofiltro y citación a fuente.
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    document: Mapped[Document] = relationship(back_populates="chunks")


class QueryLog(Base):
    """Auditoría inmutable de cada consulta (exigida por la due diligence B2B)."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    semaforo: Mapped[str] = mapped_column(String(16), default="verde")  # verde|amarillo|rojo
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    abstention_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)

    citations: Mapped[list] = mapped_column(JSONB, default=list)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    corpus_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_info: Mapped[dict] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Human-in-the-loop (se usa en la Ruta B; presente desde ya para no reescribir).
    reviewer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), default="none")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
