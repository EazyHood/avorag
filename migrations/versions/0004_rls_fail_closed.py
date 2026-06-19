"""RLS fail-closed: una sesión sin `app.current_tenant` NO ve filas (antes era fail-open).

La migración 0003 creó políticas PERMISIVAS: `current_setting('app.current_tenant', true) IS NULL OR
tenant = ...`. Con esa cláusula, si una sesión NO fijaba el tenant (un script nuevo, un bug, la
ingesta), `current_setting(..., true)` devolvía NULL, la condición resolvía a TRUE y la fila pasaba el
filtro: se veía el cruce de TODOS los tenants (fail-OPEN).

Esta migración cambia las políticas a ESTRICTAS: solo se ven/insertan filas cuyo `tenant` coincide
EXACTAMENTE con `app.current_tenant`. Si el GUC no está fijado, `tenant = NULL` es NULL → la fila NO
pasa: fail-CLOSED (ves nada en vez de todo). El acceso a datos pasa a requerir tenant explícito
(`get_session(tenant=...)`), y la ingesta ya lo fija.

`ENABLE`/`FORCE ROW LEVEL SECURITY` los dejó puestos 0003; aquí solo se reemplaza la POLÍTICA.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-16
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLES = ("documents", "chunks", "queries")

# Política ESTRICTA (fail-closed): GUC no fijado → tenant = NULL → NULL → la fila no pasa.
_STRICT = (
    "USING (tenant = current_setting('app.current_tenant', true)) "
    "WITH CHECK (tenant = current_setting('app.current_tenant', true))"
)
# Política PERMISIVA original de 0003 (fail-open); solo se usa al revertir.
_PERMISSIVE = (
    "USING (current_setting('app.current_tenant', true) IS NULL "
    "OR tenant = current_setting('app.current_tenant', true)) "
    "WITH CHECK (current_setting('app.current_tenant', true) IS NULL "
    "OR tenant = current_setting('app.current_tenant', true))"
)


def _apply_policy(clause: str) -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {clause}")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS es específico de PostgreSQL
    _apply_policy(_STRICT)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    _apply_policy(_PERMISSIVE)
