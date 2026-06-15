"""Esquema inicial: extensión pgvector, tablas e índices (HNSW + GIN español).

Revision ID: 0001
Revises:
Create Date: 2026-06-14
"""

from __future__ import annotations

from alembic import op

from avorag.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind, checkfirst=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_chunks_content_tsv ON chunks USING gin (content_tsv)")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP INDEX IF EXISTS ix_chunks_content_tsv")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    Base.metadata.drop_all(bind=bind)
