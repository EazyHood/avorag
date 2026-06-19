"""Capa de datos del modo ONLINE: feeds en vivo, normas versionadas, HITL, feedback + trazabilidad.

Materializa `docs/contracts/schema_online.sql`. Objetos NUEVOS (no toca documents/chunks):
- `feed_snapshots` (GLOBAL): snapshots versionados de feeds en vivo (ICA/SimplifICA, IDEAM, LMR UE,
  40 CFR 180, precios) con `as_of` + `ttl_seconds` (frescura, principio P-5).
- `norm_tables` (GLOBAL): umbrales/normas de las calculadoras movidos de código a DATOS versionados
  (suficiencia foliar, CEe por portainjerto, T_base, objetivos de %MS, factor de cal…).
- `hitl_reviews` (tenant-scoped, RLS FAIL-CLOSED): revisión/firma del agrónomo (P-2).
- `feedback` (tenant-scoped, RLS FAIL-CLOSED): feedback del usuario; comentario por HASH (P-4).
- Extensión de `queries`: response_id, *_version, feed_versions, judge_independent, idempotency_key (P-3/P-6).

Específico de PostgreSQL (jsonb/timestamptz/RLS). En otros dialectos es un no-op.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17
"""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Tablas tenant-scoped que llevan RLS fail-closed (mismo patrón que 0004).
_RLS_TABLES = ("hitl_reviews", "feedback")

# Cláusula de política ESTRICTA (fail-closed): GUC sin fijar ⇒ tenant=NULL ⇒ la fila no pasa.
_STRICT = (
    "USING (tenant = current_setting('app.current_tenant', true)) "
    "WITH CHECK (tenant = current_setting('app.current_tenant', true))"
)

_UPGRADE = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    # 1) feed_snapshots (GLOBAL)
    """
    CREATE TABLE IF NOT EXISTS feed_snapshots (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        feed_name   text NOT NULL CHECK (feed_name IN
                      ('ica_simplifica','ideam','lmr_ue','tol_eeuu_40cfr180','precios')),
        source_url  text,
        as_of       timestamptz NOT NULL,
        fetched_at  timestamptz NOT NULL DEFAULT now(),
        ttl_seconds integer NOT NULL CHECK (ttl_seconds > 0),
        status      text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','stale','error')),
        sha256      char(64) NOT NULL,
        payload     jsonb NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feed_snapshots_feed_asof ON feed_snapshots (feed_name, as_of DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_feed_snapshots_feed_sha ON feed_snapshots (feed_name, sha256)",
    "CREATE INDEX IF NOT EXISTS gin_feed_snapshots_payload ON feed_snapshots USING gin (payload jsonb_path_ops)",
    # 2) norm_tables (GLOBAL)
    """
    CREATE TABLE IF NOT EXISTS norm_tables (
        id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        norm_key     text NOT NULL,
        norm_version text NOT NULL,
        scope        jsonb NOT NULL DEFAULT '{}'::jsonb,
        params       jsonb NOT NULL,
        fuente       text,
        as_of        timestamptz,
        vigente      boolean NOT NULL DEFAULT true,
        created_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_norm_key_version_scope ON norm_tables (norm_key, norm_version, md5(scope::text))",
    "CREATE INDEX IF NOT EXISTS ix_norm_key_vigente ON norm_tables (norm_key) WHERE vigente",
    # 3) trazabilidad en queries (P-3/P-6)
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS response_id uuid",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS prompt_version text",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS model_version text",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS norm_version text",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS feed_versions jsonb NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS judge_independent boolean",
    "ALTER TABLE queries ADD COLUMN IF NOT EXISTS idempotency_key uuid",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_queries_response_id ON queries (response_id) WHERE response_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_queries_tenant_idemp ON queries (tenant, idempotency_key) WHERE idempotency_key IS NOT NULL",
    # 4) hitl_reviews (tenant-scoped)
    """
    CREATE TABLE IF NOT EXISTS hitl_reviews (
        id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant      text NOT NULL,
        query_id    uuid NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
        reviewer_id text NOT NULL,
        decision    text NOT NULL CHECK (decision IN ('pending','approved','rejected','edited')),
        edited_text text,
        notes       text,
        signature   text,
        created_at  timestamptz NOT NULL DEFAULT now(),
        decided_at  timestamptz
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_hitl_tenant_status ON hitl_reviews (tenant, decision)",
    "CREATE INDEX IF NOT EXISTS ix_hitl_query ON hitl_reviews (query_id)",
    # 5) feedback (tenant-scoped)
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant            text NOT NULL,
        response_id       uuid NOT NULL,
        util              boolean NOT NULL,
        motivo            text CHECK (motivo IN ('incorrecta','incompleta','desactualizada','peligrosa','otra')),
        comentario_sha256 char(64),
        user_ref          text,
        created_at        timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_feedback_tenant_resp ON feedback (tenant, response_id)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_motivo ON feedback (motivo) WHERE motivo IS NOT NULL",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # objetos específicos de PostgreSQL
    for stmt in _UPGRADE:
        op.execute(stmt)
    # RLS fail-closed en las tablas tenant-scoped (mismo patrón que 0004).
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_tenant_isolation ON {table} {_STRICT}")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.execute("DROP TABLE IF EXISTS feedback")
    op.execute("DROP TABLE IF EXISTS hitl_reviews")
    for col in (
        "idempotency_key", "judge_independent", "feed_versions",
        "norm_version", "model_version", "prompt_version", "response_id",
    ):
        op.execute(f"ALTER TABLE queries DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS norm_tables")
    op.execute("DROP TABLE IF EXISTS feed_snapshots")
