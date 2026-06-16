"""Tabla de tenants + políticas RLS de PostgreSQL (aislamiento multi-tenant a nivel de BD).

Política permisiva cuando `app.current_tenant` no está fijado (compatible con ingesta/migraciones).
ADVERTENCIA: activar en producción solo tras verificar que el código fija el tenant en cada sesión.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TABLES = ("documents", "chunks", "queries")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS es específico de PostgreSQL

    op.create_table(
        "tenants",
        sa.Column("slug", sa.String(length=64), primary_key=True),
        sa.Column("nombre", sa.String(length=200), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    # Backfill: registra los tenants ya presentes en los datos.
    for table in _TABLES:
        op.execute(
            f"INSERT INTO tenants (slug) SELECT DISTINCT tenant FROM {table} "
            "WHERE tenant IS NOT NULL ON CONFLICT (slug) DO NOTHING"
        )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            "USING (current_setting('app.current_tenant', true) IS NULL "
            "OR tenant = current_setting('app.current_tenant', true)) "
            "WITH CHECK (current_setting('app.current_tenant', true) IS NULL "
            "OR tenant = current_setting('app.current_tenant', true))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("tenants")
