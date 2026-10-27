"""Redshift bootstrap (DDL, users, datashares) and daily COPY loads from the silver layer."""
from __future__ import annotations

import logging
from datetime import date

from datagen.domain import reference as R
from datagen.redshift_ddl import comments_sql
from datagen.writer import LAB_TYPE_CHANGE_DAY, SILVER_TYPES
from jobs.common import settings
from jobs.common.db import split_sql
from jobs.common.redshift import Redshift

log = logging.getLogger("load")
SQL = R.ROOT / "sql" / "redshift"
CONSUMERS = ["svc_bi_tableau", "svc_careempower_sync", "svc_extract_runner", "actuary_ro", "analyst_quality",
             "analyst_ops"]
HARVEST_DB_USER = '"IAMR:eqh-dq-harvest-task-role"'
MERGE_KEYS = {"eligibility_span": "span_id", "care_gap": "care_gap_id"}
SCHEMAS = ["core", "careempower", "vbc_mart", "outbound"]


def admin() -> Redshift:
    return Redshift(secret_arn=settings.get()["redshift_admin_secret_arn"])


def run_file(rs: Redshift, name: str) -> None:
    for stmt in split_sql((SQL / name).read_text()):
        try:
            rs.query(stmt)
        except RuntimeError as e:
            if "already exists" in str(e):
                continue
            raise


def bootstrap() -> None:
    rs = admin()
    run_file(rs, "01_schemas_users.sql")
    rs.query("CREATE EXTERNAL SCHEMA IF NOT EXISTS spectrum_silver FROM DATA CATALOG DATABASE 'eqh_silver' "
             "IAM_ROLE default")
    existing = {r["usename"] for r in rs.query("select usename from pg_user")}
    for u in CONSUMERS + [HARVEST_DB_USER.strip('"')]:
        if u not in existing:
            rs.query(f'CREATE USER "{u}" PASSWORD DISABLE')
    if not rs.query("select 1 from core.dim_calendar_month limit 1"):
        months = []
        for y in range(2024, 2028):
            for m in range(1, 13):
                start = date(y, m, 1)
                end = date(y + (m == 12), m % 12 + 1, 1)
                months.append(f"('{start}', dateadd(day, -1, '{end}'::date))")
        rs.query("INSERT INTO core.dim_calendar_month VALUES " + ",".join(months))
    run_file(rs, "02_core_tables.sql")
    log.info("redshift core ready")


def create_marts() -> None:
    """Views/MVs/shares need loaded tables (MVs) so they are created after the day-0 load."""
    rs = admin()
    for f in ("03_careempower.sql", "04_vbc_mart.sql", "05_outbound.sql"):
        run_file(rs, f)
    shares = {r["share_name"] for r in rs.query("select share_name from svv_datashares")}
    if "eqh_actuarial_share" not in shares:
        run_file(rs, "06_datashares.sql")
    if not rs.query("select 1 from vbc_mart.legacy_pmpm_2023 limit 1"):
        rs.query("INSERT INTO vbc_mart.legacy_pmpm_2023 SELECT month, practice_id, total_paid / "
                 "nullif(members_with_claims, 0) FROM vbc_mart.pmpm_cost_by_practice WHERE month < '2026-01-01'")
    grants()


def grants() -> None:
    rs = admin()
    stmts = []
    for u in CONSUMERS + [HARVEST_DB_USER]:
        uq = u if u.startswith('"') else f'"{u}"'
        for s in SCHEMAS + ["spectrum_silver"]:
            stmts.append(f"GRANT USAGE ON SCHEMA {s} TO {uq}")
            if s != "spectrum_silver":
                stmts.append(f"GRANT SELECT ON ALL TABLES IN SCHEMA {s} TO {uq}")
    # the harvest identity reads system views for all users (query history, datashares)
    stmts.append(f"GRANT ROLE sys:monitor TO {HARVEST_DB_USER}")
    rs.batch(stmts)


def copy_day(day: int) -> None:
    """COPY one ingest day from silver into core (MERGE for SCD-style tables)."""
    rs, s = admin(), settings.get()
    d = R.day_date(day).isoformat()
    if day == LAB_TYPE_CHANGE_DAY:
        lab_result_to_varchar(rs)
    stmts = []
    for entity in SILVER_TYPES:
        src = f"s3://{s['bucket_silver']}/{entity}/ingest_date={d}/"
        copy = f"COPY {{t}} FROM '{src}' IAM_ROLE default FORMAT AS PARQUET"
        if entity in MERGE_KEYS:
            k = MERGE_KEYS[entity]
            stmts.append([f"CREATE TEMP TABLE stg_{entity} (LIKE core.{entity})",
                          copy.format(t=f"stg_{entity}"),
                          f"DELETE FROM core.{entity} USING stg_{entity} WHERE core.{entity}.{k} = stg_{entity}.{k}",
                          f"INSERT INTO core.{entity} SELECT * FROM stg_{entity}"])
        else:
            stmts.append([copy.format(t=f"core.{entity}")])
    present = _present_prefixes(d)
    work = [b for e, b in zip(SILVER_TYPES, stmts) if e in present]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(rs.batch, work))
    log.info("day %s: copied %d tables", day, len(work))


def _present_prefixes(d: str) -> set[str]:
    import boto3
    s3 = boto3.client("s3", region_name=settings.get()["region"])
    out = set()
    for entity in SILVER_TYPES:
        r = s3.list_objects_v2(Bucket=settings.get()["bucket_silver"], Prefix=f"{entity}/ingest_date={d}/", MaxKeys=1)
        if r.get("KeyCount"):
            out.add(entity)
    return out


def refresh_mvs() -> None:
    admin().batch(["REFRESH MATERIALIZED VIEW vbc_mart.member_month",
                   "REFRESH MATERIALIZED VIEW vbc_mart.pmpm_cost_by_practice"])


def lab_result_to_varchar(rs: Redshift) -> None:
    """D05: the EHR integration starts sending result_value as text. Rebuild the table with the new type
    (keeps column order for COPY). Only late-binding views read it, so nothing blocks the change."""
    cols = SILVER_TYPES["lab_result"]
    from datagen.redshift_ddl import RS_TYPES
    defs = [f"{c} {'varchar(16)' if c == 'result_value' else RS_TYPES[t]}" for c, t in cols.items()]
    sel = ", ".join(f"{c}::varchar(16)" if c == "result_value" else c for c in cols)
    rs.batch([f"CREATE TABLE core.lab_result_new ({', '.join(defs)}, ingest_date date) DISTKEY(member_id) "
              "SORTKEY(ingest_date)",
              f"INSERT INTO core.lab_result_new SELECT {sel}, ingest_date FROM core.lab_result",
              "DROP TABLE core.lab_result",
              "ALTER TABLE core.lab_result_new RENAME TO lab_result"]
             + comments_sql("lab_result")
             + [f'GRANT SELECT ON core.lab_result TO "{u}"' for u in CONSUMERS] +
             [f"GRANT SELECT ON core.lab_result TO {HARVEST_DB_USER}"])
    log.info("D05 applied: core.lab_result.result_value is now varchar")
