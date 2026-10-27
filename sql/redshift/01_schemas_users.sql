-- Schemas, consumer users (for the usage simulator) and a calendar helper. Idempotent.
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS careempower;
CREATE SCHEMA IF NOT EXISTS vbc_mart;
CREATE SCHEMA IF NOT EXISTS outbound;
COMMENT ON SCHEMA core IS 'Conformed tables COPY-loaded from eqh_silver';
COMMENT ON SCHEMA vbc_mart IS 'Value-based-care marts';

-- @users: svc_bi_tableau svc_careempower_sync svc_extract_runner actuary_ro analyst_quality analyst_ops

CREATE TABLE IF NOT EXISTS core.dim_calendar_month (month_start date NOT NULL, month_end date NOT NULL) DISTSTYLE ALL;
