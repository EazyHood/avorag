-- =====================================================================================
-- AvoRAG — Esquema SQL del modo ONLINE (PostgreSQL 16 + pgvector)
-- Artefacto de arquitectura (docs/ARQUITECTURA_ONLINE.md). NO sustituye a las migraciones
-- Alembic: es la referencia normativa para escribir la migración 0005. Lenguaje DEBE/NO DEBE.
--
-- Construye SOBRE lo ya existente (NO recrear): documents, chunks, queries (db/models.py),
-- tenants + RLS (migración 0003), RLS FAIL-CLOSED (migración 0004). Aquí van solo los
-- objetos NUEVOS que el online necesita: feeds en vivo, normas versionadas, HITL, feedback,
-- y la extensión de trazabilidad de `queries`.
--
-- Convenciones: cmol(+)/kg, %MS, ppm, dS/m según las calculadoras. Tiempos en timestamptz (UTC).
-- =====================================================================================

BEGIN;

-- Requisitos (idempotentes).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- -------------------------------------------------------------------------------------
-- 0) Recordatorio de RLS FAIL-CLOSED (migración 0004) — patrón a reutilizar.
--    Política estricta: si `app.current_tenant` no está fijado ⇒ current_setting(...,true)=NULL
--    ⇒ `tenant = NULL` ⇒ NULL ⇒ la fila NO pasa (fail-closed). El rol de la app NO DEBE tener
--    BYPASSRLS ni ser superusuario. Toda sesión de datos DEBE fijar el tenant (get_session(tenant=...)).
-- -------------------------------------------------------------------------------------

-- =====================================================================================
-- 1) FEEDS EN VIVO (datos regulatorios/clima) — GLOBALES, no por tenant (referencia compartida).
--    P-5 (frescura): cada snapshot lleva `as_of` (fecha del dato en la fuente) y `fetched_at`
--    (cuándo lo trajimos). El guardarraíl cruza contra el snapshot MÁS RECIENTE dentro de su
--    SLA (ttl_seconds); fuera de SLA ⇒ degradar a Modo 2 y PROHIBIR verde sobre ese dato.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS feed_snapshots (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_name    text NOT NULL CHECK (feed_name IN ('ica_simplifica','ideam','lmr_ue','tol_eeuu_40cfr180','precios')),
    source_url   text,
    as_of        timestamptz NOT NULL,            -- fecha-de-dato declarada por la fuente
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    ttl_seconds  integer NOT NULL CHECK (ttl_seconds > 0),  -- SLA de frescura del feed (SLO-4)
    status       text NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','stale','error')),
    sha256       char(64) NOT NULL,               -- integridad/dedup del payload
    payload      jsonb NOT NULL,                  -- datos normalizados al esquema canónico del feed
    created_at   timestamptz NOT NULL DEFAULT now()
);
-- Último snapshot por feed (consulta caliente del guardarraíl).
CREATE INDEX IF NOT EXISTS ix_feed_snapshots_feed_asof ON feed_snapshots (feed_name, as_of DESC);
-- Idempotencia de ingesta: no re-insertar el mismo contenido del mismo feed.
CREATE UNIQUE INDEX IF NOT EXISTS uq_feed_snapshots_feed_sha ON feed_snapshots (feed_name, sha256);
-- Búsqueda por activo dentro del payload (LMR/tolerancias/registros).
CREATE INDEX IF NOT EXISTS gin_feed_snapshots_payload ON feed_snapshots USING gin (payload jsonb_path_ops);

COMMENT ON TABLE feed_snapshots IS
  'Snapshots versionados de feeds en vivo (P-5). Globales (no RLS). El online cruza contra el snapshot vigente; fuera de TTL prohíbe verde.';

-- =====================================================================================
-- 2) NORMAS VERSIONADAS de las calculadoras — GLOBALES (mueve los umbrales HARDCODEADOS a datos).
--    Suficiencia foliar, umbral CEe por portainjerto, T_base, objetivos de %MS, factor de cal…
--    DEBEN dejar de ser constantes en código y volverse filas citables y versionadas (norm_version
--    estampado en cada respuesta de calc). Cierra la crítica "normas genéricas hardcodeadas".
-- =====================================================================================
CREATE TABLE IF NOT EXISTS norm_tables (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    norm_key      text NOT NULL,        -- p.ej. 'foliar_suficiencia','ce_umbral_portainjerto','ms_objetivo','t_base'
    norm_version  text NOT NULL,        -- versión citada (estampada en la respuesta de calc)
    scope         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {mercado,cultivar,portainjerto,laboratorio,pais}
    params        jsonb NOT NULL,       -- el contenido normativo (rangos/umbrales/factores)
    fuente        text,                 -- referencia citable de la norma
    as_of         timestamptz,
    vigente       boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_norm_key_version_scope
    ON norm_tables (norm_key, norm_version, md5(scope::text));
CREATE INDEX IF NOT EXISTS ix_norm_key_vigente ON norm_tables (norm_key) WHERE vigente;

COMMENT ON TABLE norm_tables IS
  'Normas/umbrales versionados de las calculadoras (paridad online/offline). El cliente offline empaqueta una norm_version concreta; el online sirve la vigente. Determinismo: mismo input + misma norm_version = mismo resultado bit-a-bit.';

-- =====================================================================================
-- 3) TRAZABILIDAD de respuesta (P-3): extiende `queries` con el correlador de versiones.
--    (En Alembic: ALTER TABLE; aquí idempotente con IF NOT EXISTS.)
-- =====================================================================================
ALTER TABLE queries ADD COLUMN IF NOT EXISTS response_id    uuid;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS prompt_version text;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS model_version  text;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS norm_version   text;
ALTER TABLE queries ADD COLUMN IF NOT EXISTS feed_versions  jsonb NOT NULL DEFAULT '{}'::jsonb;  -- {feed: as_of}
ALTER TABLE queries ADD COLUMN IF NOT EXISTS judge_independent boolean;  -- juez ≠ generador (anti-autoeval)
CREATE UNIQUE INDEX IF NOT EXISTS uq_queries_response_id ON queries (response_id) WHERE response_id IS NOT NULL;
-- Idempotencia de petición (P-6): misma Idempotency-Key ⇒ misma respuesta.
ALTER TABLE queries ADD COLUMN IF NOT EXISTS idempotency_key uuid;
CREATE UNIQUE INDEX IF NOT EXISTS uq_queries_tenant_idemp ON queries (tenant, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- =====================================================================================
-- 4) HITL — revisión y firma del agrónomo (P-2). Tenant-scoped ⇒ RLS FAIL-CLOSED.
--    Toda respuesta 🔴 o con recomendación química accionable DEBE pasar por aquí antes de
--    entregarse como consejo firme. La firma es revisión técnica, NO exoneración legal.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS hitl_reviews (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant       text NOT NULL,
    query_id     uuid NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
    reviewer_id  text NOT NULL,                 -- agrónomo colegiado (id de usuario)
    decision     text NOT NULL CHECK (decision IN ('pending','approved','rejected','edited')),
    edited_text  text,                          -- si el agrónomo corrige la respuesta
    notes        text,
    signature    text,                          -- firma/no-repudio (hash firmado de la decisión)
    created_at   timestamptz NOT NULL DEFAULT now(),
    decided_at   timestamptz
);
CREATE INDEX IF NOT EXISTS ix_hitl_tenant_status ON hitl_reviews (tenant, decision);
CREATE INDEX IF NOT EXISTS ix_hitl_query ON hitl_reviews (query_id);

ALTER TABLE hitl_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE hitl_reviews FORCE ROW LEVEL SECURITY;
CREATE POLICY hitl_reviews_tenant_isolation ON hitl_reviews
    USING (tenant = current_setting('app.current_tenant', true))
    WITH CHECK (tenant = current_setting('app.current_tenant', true));

-- =====================================================================================
-- 5) FEEDBACK del usuario (bucle de eval online). Tenant-scoped ⇒ RLS FAIL-CLOSED.
--    Privacidad (P-4): el comentario se guarda como HASH, nunca texto en claro.
-- =====================================================================================
CREATE TABLE IF NOT EXISTS feedback (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant        text NOT NULL,
    response_id   uuid NOT NULL,                 -- correlaciona con queries.response_id
    util          boolean NOT NULL,
    motivo        text CHECK (motivo IN ('incorrecta','incompleta','desactualizada','peligrosa','otra')),
    comentario_sha256 char(64),                  -- HASH del comentario (no el texto)
    user_ref      text,                          -- id de usuario hasheado (Habeas Data)
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feedback_tenant_resp ON feedback (tenant, response_id);
CREATE INDEX IF NOT EXISTS ix_feedback_motivo ON feedback (motivo) WHERE motivo IS NOT NULL;

ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback FORCE ROW LEVEL SECURITY;
CREATE POLICY feedback_tenant_isolation ON feedback
    USING (tenant = current_setting('app.current_tenant', true))
    WITH CHECK (tenant = current_setting('app.current_tenant', true));

-- =====================================================================================
-- 6) Índices de recuperación (recordatorio — ya deberían existir sobre chunks).
--    DEBEN existir para el RAG online de alta fidelidad:
--      - HNSW sobre el embedding (coseno) para el lado denso.
--      - GIN sobre content_tsv (columna generada) para el lado léxico (FTS español).
--    Se incluyen idempotentes por si la migración base no los creó con estos parámetros.
-- =====================================================================================
-- Ajusta la dimensión del Vector a EMBEDDING_DIM real (bge-m3 = 1024).
CREATE INDEX IF NOT EXISTS hnsw_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS gin_chunks_content_tsv
    ON chunks USING gin (content_tsv);

COMMIT;

-- =====================================================================================
-- NOTAS DE OPERACIÓN (no-SQL, para la migración/runbook):
--  - El rol de la aplicación NO DEBE ser superusuario ni tener BYPASSRLS (anularía el RLS).
--  - feed_snapshots y norm_tables son GLOBALES: las sirve un rol de solo-lectura distinto del
--    de datos de tenant; su escritura la hace el worker de ingesta de feeds (rol dedicado).
--  - Reindex de embeddings: BLUE-GREEN (índice nuevo en paralelo + swap) al cambiar de modelo,
--    nunca DROP-then-CREATE en caliente (ver ADR de reindex).
--  - Backups: PITR; probar restauración (un backup no probado no es un backup).
-- =====================================================================================
