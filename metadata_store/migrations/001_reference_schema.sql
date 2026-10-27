-- Aurora PostgreSQL schema for the EQH AI Data Quality Assistant metadata store.
-- Requires Aurora PostgreSQL 15.4+ / 16.x with the pgvector extension.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per daily run. Every write is stamped with run_id so runs are auditable and re-runnable.
CREATE TABLE IF NOT EXISTS sync_run (
    run_id        uuid PRIMARY KEY,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running','succeeded','failed')),
    stats         jsonb NOT NULL DEFAULT '{}'::jsonb,
    error         text
);

-- Canonical data asset: Glue table, Redshift table/view, datashare object, outbound extract.
-- asset_key is a stable URI, e.g. redshift://analytics/vbc/member_month
CREATE TABLE IF NOT EXISTS asset (
    asset_id              bigserial PRIMARY KEY,
    asset_key             text UNIQUE NOT NULL,
    platform              text NOT NULL,           -- glue | redshift | datashare | extract
    asset_type            text NOT NULL,           -- table | view | external_table | share_object | extract
    database_name         text,
    schema_name           text,
    object_name           text NOT NULL,
    source_comment        text,                    -- comment/description as it exists in the source system
    steward_description   text,                    -- human-approved text; never overwritten by the job
    ai_description        text,                    -- latest AI draft (from the enrichment job)
    ai_description_status text NOT NULL DEFAULT 'none'
                          CHECK (ai_description_status IN ('none','pending','draft','approved','rejected')),
    tags                  text[] NOT NULL DEFAULT '{}',
    struct_hash           text NOT NULL,           -- hash of structure (columns/types/nullability)
    doc_hash              text NOT NULL,           -- hash of the text that feeds embeddings
    source_updated_at     timestamptz,
    first_seen_run        uuid REFERENCES sync_run(run_id),
    last_seen_run         uuid REFERENCES sync_run(run_id),
    last_seen_at          timestamptz,
    missed_runs           int NOT NULL DEFAULT 0,
    is_deleted            boolean NOT NULL DEFAULT false,
    updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS asset_platform_idx ON asset (platform, schema_name);

CREATE TABLE IF NOT EXISTS asset_column (
    asset_id            bigint NOT NULL REFERENCES asset(asset_id) ON DELETE CASCADE,
    column_name         text NOT NULL,
    ordinal             int,
    data_type           text,
    is_nullable         boolean,
    source_comment      text,
    steward_description text,
    ai_description      text,
    PRIMARY KEY (asset_id, column_name)
);

-- Lineage / dependency graph. Edges not seen for N runs are expired, not hard-deleted.
CREATE TABLE IF NOT EXISTS lineage_edge (
    src_asset_key  text NOT NULL,
    dst_key        text NOT NULL,                  -- asset_key, or consumer identity for usage edges
    edge_type      text NOT NULL CHECK (edge_type IN
                   ('view_dependency','datashare','extract','query_consumer','glossary')),
    attrs          jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at  timestamptz NOT NULL DEFAULT now(),
    last_seen_run  uuid REFERENCES sync_run(run_id),
    last_seen_at   timestamptz NOT NULL DEFAULT now(),
    is_active      boolean NOT NULL DEFAULT true,
    PRIMARY KEY (src_asset_key, dst_key, edge_type)
);
CREATE INDEX IF NOT EXISTS lineage_dst_idx ON lineage_edge (dst_key);

-- Schema drift log, appended whenever struct_hash changes.
CREATE TABLE IF NOT EXISTS schema_change (
    id           bigserial PRIMARY KEY,
    run_id       uuid REFERENCES sync_run(run_id),
    asset_key    text NOT NULL,
    change_type  text NOT NULL CHECK (change_type IN
                 ('asset_added','asset_removed','column_added','column_removed','type_changed','nullability_changed')),
    column_name  text,
    old_value    text,
    new_value    text,
    detected_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS schema_change_asset_idx ON schema_change (asset_key, detected_at DESC);

-- DQ metrics are an append-only time series of AGGREGATES only (no row values => no PHI).
CREATE TABLE IF NOT EXISTS dq_metric (
    id           bigserial PRIMARY KEY,
    run_id       uuid REFERENCES sync_run(run_id),
    asset_key    text NOT NULL,
    column_name  text NOT NULL DEFAULT '',          -- '' = table-level metric
    metric       text NOT NULL,                     -- row_count | null_rate | dup_rate | hours_since_update | rule:<name>
    value        double precision,
    measured_at  timestamptz NOT NULL,
    UNIQUE (asset_key, column_name, metric, measured_at)
);
CREATE INDEX IF NOT EXISTS dq_metric_lookup_idx ON dq_metric (asset_key, metric, measured_at DESC);

-- Open/resolved DQ issues derived from metrics. One open row per (asset, column, issue_type).
CREATE TABLE IF NOT EXISTS dq_issue (
    id             bigserial PRIMARY KEY,
    asset_key      text NOT NULL,
    column_name    text NOT NULL DEFAULT '',
    issue_type     text NOT NULL,                   -- stale | volume_anomaly | null_spike | duplicates | rule_failed | schema_drift
    severity       text NOT NULL CHECK (severity IN ('low','medium','high')),
    detail         jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_detected timestamptz NOT NULL DEFAULT now(),
    last_detected  timestamptz NOT NULL DEFAULT now(),
    status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved'))
);
CREATE UNIQUE INDEX IF NOT EXISTS dq_issue_open_uq
    ON dq_issue (asset_key, column_name, issue_type) WHERE status = 'open';

-- Work queue for the separate LLM enrichment job (Bedrock batch inference -> steward review).
CREATE TABLE IF NOT EXISTS enrichment_task (
    asset_key   text NOT NULL,
    doc_hash    text NOT NULL,
    reason      text NOT NULL,                      -- new_asset | structure_changed | missing_description
    status      text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','submitted','drafted','skipped')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_key, doc_hash)
);

-- Vector store. One 'asset' chunk per asset plus 'columns' chunks for wide tables.
-- Dimension must match EMBED_DIM in daily_sync.py.
CREATE TABLE IF NOT EXISTS embedding (
    asset_key   text NOT NULL,
    chunk_type  text NOT NULL CHECK (chunk_type IN ('asset','columns','glossary')),
    chunk_ix    int  NOT NULL DEFAULT 0,
    model_id    text NOT NULL,
    doc_hash    text NOT NULL,
    content     text NOT NULL,
    embedding   vector(1024) NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_key, chunk_type, chunk_ix, model_id)
);
CREATE INDEX IF NOT EXISTS embedding_hnsw_idx
    ON embedding USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
