-- 002: Phase 3 extensions (SPEC §B6 Phase 3) + segmentation needed by Phase 4.

-- Run bookkeeping for --as-of backfills
ALTER TABLE sync_run ADD COLUMN IF NOT EXISTS as_of timestamptz;

-- dq_metric: ingestion time + payer/state segment ('' = whole table)
ALTER TABLE dq_metric ADD COLUMN IF NOT EXISTS ingested_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE dq_metric ADD COLUMN IF NOT EXISTS segment text NOT NULL DEFAULT '';
ALTER TABLE dq_metric DROP CONSTRAINT IF EXISTS dq_metric_asset_key_column_name_metric_measured_at_key;
CREATE UNIQUE INDEX IF NOT EXISTS dq_metric_uq ON dq_metric (asset_key, column_name, metric, segment, measured_at);
CREATE INDEX IF NOT EXISTS dq_metric_seg_idx ON dq_metric (asset_key, metric, segment, measured_at DESC);

-- dq_issue: segment + business impact; one open issue per (asset, column, type, segment)
ALTER TABLE dq_issue ADD COLUMN IF NOT EXISTS segment text NOT NULL DEFAULT '';
ALTER TABLE dq_issue ADD COLUMN IF NOT EXISTS resolved_at timestamptz;
DROP INDEX IF EXISTS dq_issue_open_uq;
CREATE UNIQUE INDEX IF NOT EXISTS dq_issue_open_uq ON dq_issue (asset_key, column_name, issue_type, segment)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS dq_issue_detected_idx ON dq_issue (first_detected DESC);

-- Business glossary (harvested from s3://...-glossary/*.md)
CREATE TABLE IF NOT EXISTS glossary_term (
    term        text PRIMARY KEY,
    definition  text NOT NULL,
    synonyms    text[] NOT NULL DEFAULT '{}',
    related     text[] NOT NULL DEFAULT '{}',
    source_key  text NOT NULL,
    doc_hash    text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Entitlements: asset (optionally column) -> Cognito group allowed to see it. No row = visible to all.
CREATE TABLE IF NOT EXISTS asset_entitlement (
    asset_key    text NOT NULL,
    column_name  text NOT NULL DEFAULT '',
    group_name   text NOT NULL,
    PRIMARY KEY (asset_key, column_name, group_name)
);

-- Steward review audit trail (the only write path from the assistant)
CREATE TABLE IF NOT EXISTS review_action (
    id           bigserial PRIMARY KEY,
    asset_key    text NOT NULL,
    column_name  text NOT NULL DEFAULT '',
    action       text NOT NULL CHECK (action IN ('approve','edit_approve','reject')),
    reviewer     text NOT NULL,
    old_text     text,
    new_text     text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- enrichment_task: allow 'failed'
ALTER TABLE enrichment_task DROP CONSTRAINT IF EXISTS enrichment_task_status_check;
ALTER TABLE enrichment_task ADD CONSTRAINT enrichment_task_status_check
    CHECK (status IN ('pending','submitted','drafted','skipped','failed'));
ALTER TABLE enrichment_task ADD COLUMN IF NOT EXISTS error text;
ALTER TABLE enrichment_task ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- asset: business domain + state tags, usage and enrichment metadata
ALTER TABLE asset ADD COLUMN IF NOT EXISTS business_domain text;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS state text;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS last_read_at timestamptz;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS read_count_30d int NOT NULL DEFAULT 0;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS owner text;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS ai_meta jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE asset ADD COLUMN IF NOT EXISTS created_in_source_at timestamptz;
CREATE INDEX IF NOT EXISTS asset_domain_idx ON asset (business_domain, state);

-- lineage: more edge types (spectrum, raw->silver, COPY loads, glossary links)
ALTER TABLE lineage_edge DROP CONSTRAINT IF EXISTS lineage_edge_edge_type_check;
ALTER TABLE lineage_edge ADD CONSTRAINT lineage_edge_edge_type_check CHECK (edge_type IN
    ('view_dependency','datashare','extract','query_consumer','glossary','spectrum','raw_to_silver','copy_load',
     'datashare_consumer','extract_target'));
CREATE INDEX IF NOT EXISTS lineage_src_idx ON lineage_edge (src_asset_key);

-- Keyword search support for search_assets
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS asset_object_trgm ON asset USING gin (object_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS embedding_content_fts ON embedding USING gin (to_tsvector('english', content));

-- Embedding dimension from config (templated by migrate.py; no-op when unchanged)
-- {{embed_dim_alter}}
