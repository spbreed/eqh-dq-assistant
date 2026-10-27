"""
Daily metadata + vector sync for the EQH AI Data Quality Assistant.

Runs once a day (EventBridge Scheduler -> ECS Fargate task or Glue Python shell job).
Read-only against the data platform; writes only to the Aurora metadata store.

Algorithm
---------
 0. START      open sync_run, take a Postgres advisory lock (one run at a time)
 1. EXTRACT    pull snapshots from Glue Catalog, Redshift system views, datashares,
               outbound extract inventory, Glue Data Quality results
 2. NORMALIZE  map everything to canonical assets keyed by a stable asset_key URI
 3. FINGERPRINT struct_hash (columns/types/nullability) + doc_hash (text that gets embedded)
 4. DIFF       compare with Aurora -> new / changed / unchanged / missing
 5. UPSERT     assets + columns; log schema drift; protect steward-approved text
 6. LINEAGE    upsert edges seen today; expire edges unseen for EDGE_EXPIRY_DAYS
 7. DQ         append aggregate metrics; derive issues (stale, volume anomaly,
               null spike, rule failures, drift); auto-resolve issues that cleared
 8. ENRICH Q   enqueue new/changed assets without approved descriptions for the
               LLM drafting job (drafts go to steward review, never to Glue)
 9. EMBED      re-embed only chunks whose doc_hash or model_id changed
10. RETIRE     soft-delete assets missing for MISSED_RUNS_TO_DELETE runs; drop their vectors
11. FINISH     stats -> sync_run + CloudWatch metrics; ANALYZE

Idempotent: re-running for the same day produces the same end state.
PHI guard: only metadata and aggregate metrics are stored or embedded; never row values.

Requires: boto3, psycopg[binary]>=3.1, pgvector
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, pstdev

import boto3
import psycopg
from pgvector.psycopg import register_vector

log = logging.getLogger("daily_sync")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------------------------------------------------------- configuration
PG_DSN = os.environ["PG_DSN"]                               # from Secrets Manager in the task def
GLUE_DATABASES = [d for d in os.environ.get("GLUE_DATABASES", "").split(",") if d]
RS_DATABASE = os.environ["RS_DATABASE"]
RS_WORKGROUP = os.environ.get("RS_WORKGROUP")               # Redshift Serverless, or...
RS_CLUSTER_ID = os.environ.get("RS_CLUSTER_ID")             # ...provisioned cluster
RS_SECRET_ARN = os.environ["RS_SECRET_ARN"]                 # read-only metadata user
RS_SCHEMAS_EXCLUDE = ("pg_catalog", "information_schema", "pg_internal", "pg_automv")
EXTRACT_INVENTORY_S3 = os.environ.get("EXTRACT_INVENTORY_S3")  # s3://bucket/key.json
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1024"))
COLUMNS_PER_CHUNK = 40
MISSED_RUNS_TO_DELETE = 2          # tolerate one transient harvest failure
EDGE_EXPIRY_DAYS = 30              # usage edges come from a 1-day query window
STALE_HOURS_DEFAULT = 36           # daily feeds; override per asset via tags later
VOLUME_Z_THRESHOLD = 3.0
NULL_SPIKE_ABS = 0.10              # +10 percentage points over baseline
BASELINE_DAYS = 14
ADVISORY_LOCK_ID = 774411

glue = boto3.client("glue")
rsdata = boto3.client("redshift-data")
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")
cloudwatch = boto3.client("cloudwatch")


# ---------------------------------------------------------------- canonical model
@dataclass
class Column:
    name: str
    ordinal: int
    data_type: str
    is_nullable: bool | None
    comment: str | None = None


@dataclass
class Asset:
    asset_key: str
    platform: str
    asset_type: str
    database_name: str | None
    schema_name: str | None
    object_name: str
    comment: str | None = None
    source_updated_at: datetime | None = None
    columns: list[Column] = field(default_factory=list)

    def struct_hash(self) -> str:
        cols = [(c.name.lower(), c.data_type.lower(), c.is_nullable) for c in sorted(self.columns, key=lambda c: c.name)]
        return sha256(json.dumps([self.asset_type, cols], sort_keys=True))


@dataclass
class Edge:
    src: str
    dst: str
    edge_type: str
    attrs: dict = field(default_factory=dict)


@dataclass
class Metric:
    asset_key: str
    column_name: str
    metric: str
    value: float
    measured_at: datetime


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def rs_key(db: str, schema: str, name: str) -> str:
    return f"redshift://{db}/{schema}/{name}".lower()


def glue_key(db: str, name: str) -> str:
    return f"glue://{db}/{name}".lower()


# ---------------------------------------------------------------- 1. extract
def rs_query(sql: str) -> list[dict]:
    """Run SQL through the Redshift Data API and return rows as dicts."""
    args = dict(Database=RS_DATABASE, SecretArn=RS_SECRET_ARN, Sql=sql)
    args.update({"WorkgroupName": RS_WORKGROUP} if RS_WORKGROUP else {"ClusterIdentifier": RS_CLUSTER_ID})
    stmt_id = rsdata.execute_statement(**args)["Id"]
    delay = 0.5
    while True:
        desc = rsdata.describe_statement(Id=stmt_id)
        if desc["Status"] == "FINISHED":
            break
        if desc["Status"] in ("FAILED", "ABORTED"):
            raise RuntimeError(f"Redshift query failed: {desc.get('Error')}")
        time.sleep(delay)
        delay = min(delay * 2, 5)
    if not desc.get("HasResultSet"):
        return []
    rows, token = [], None
    while True:
        page = rsdata.get_statement_result(Id=stmt_id, **({"NextToken": token} if token else {}))
        names = [c["name"] for c in page["ColumnMetadata"]]
        for rec in page["Records"]:
            rows.append({n: (None if v.get("isNull") else next(iter(v.values()))) for n, v in zip(names, rec)})
        token = page.get("NextToken")
        if not token:
            return rows


def extract_glue() -> tuple[list[Asset], list[Metric]]:
    assets, metrics, now = [], [], datetime.now(timezone.utc)
    for db in GLUE_DATABASES:
        for page in glue.get_paginator("get_tables").paginate(DatabaseName=db):
            for t in page["TableList"]:
                sd = t.get("StorageDescriptor", {})
                cols = sd.get("Columns", []) + t.get("PartitionKeys", [])
                a = Asset(
                    asset_key=glue_key(db, t["Name"]), platform="glue",
                    asset_type="view" if t.get("TableType") == "VIRTUAL_VIEW" else "table",
                    database_name=db, schema_name=None, object_name=t["Name"],
                    comment=t.get("Description"), source_updated_at=t.get("UpdateTime"),
                    columns=[Column(c["Name"], i, c.get("Type", ""), None, c.get("Comment")) for i, c in enumerate(cols)],
                )
                assets.append(a)
                if a.source_updated_at:
                    hrs = (now - a.source_updated_at).total_seconds() / 3600
                    metrics.append(Metric(a.asset_key, "", "hours_since_update", hrs, now))
    return assets, metrics


def extract_redshift() -> tuple[list[Asset], list[Edge], list[Metric]]:
    excl = ",".join(f"'{s}'" for s in RS_SCHEMAS_EXCLUDE)
    now = datetime.now(timezone.utc)

    tables = rs_query(f"""
        select table_schema, table_name, table_type, remarks
        from svv_tables where table_catalog = current_database() and table_schema not in ({excl})""")
    columns = rs_query(f"""
        select table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, remarks
        from svv_columns where table_catalog = current_database() and table_schema not in ({excl})""")
    # Regular-view dependencies. Late-binding views (WITH NO SCHEMA BINDING) are not in pg_depend;
    # parse their DDL from pg_views in a later iteration if they are common in the business layer.
    view_deps = rs_query(f"""
        select distinct sn.nspname as src_schema, so.relname as src_name,
                        tn.nspname as dst_schema, tobj.relname as dst_name
        from pg_depend d
        join pg_rewrite r on d.objid = r.oid
        join pg_class tobj on r.ev_class = tobj.oid
        join pg_class so on d.refobjid = so.oid
        join pg_namespace sn on so.relnamespace = sn.oid
        join pg_namespace tn on tobj.relnamespace = tn.oid
        where tobj.oid <> so.oid and sn.nspname not in ({excl})""")
    share_objs = rs_query("""
        select share_name, object_type, object_name from svv_datashare_objects where share_type = 'OUTBOUND'""")
    share_consumers = rs_query("""
        select share_name, consumer_account, consumer_namespace from svv_datashare_consumers""")
    row_counts = rs_query(f"""
        select "schema" as table_schema, "table" as table_name, tbl_rows
        from svv_table_info where "schema" not in ({excl})""")
    # Who actually read each table yesterday (provisioned: STL; Serverless: swap for sys_query_detail).
    usage = rs_query("""
        select distinct trim(n.nspname) as table_schema, trim(c.relname) as table_name, trim(u.usename) as usename
        from stl_scan s
        join stl_query q on s.query = q.query
        join pg_class c on s.tbl = c.oid
        join pg_namespace n on c.relnamespace = n.oid
        join pg_user u on q.userid = u.usesysid
        where q.starttime > dateadd(day, -1, getdate()) and s.perm_table_name not like 'Internal Worktable%'""")

    by_table: dict[tuple, Asset] = {}
    for t in tables:
        key = rs_key(RS_DATABASE, t["table_schema"], t["table_name"])
        by_table[(t["table_schema"], t["table_name"])] = Asset(
            asset_key=key, platform="redshift",
            asset_type="view" if "VIEW" in (t["table_type"] or "") else "table",
            database_name=RS_DATABASE, schema_name=t["table_schema"], object_name=t["table_name"],
            comment=t["remarks"])
    for c in columns:
        a = by_table.get((c["table_schema"], c["table_name"]))
        if a:
            a.columns.append(Column(c["column_name"], int(c["ordinal_position"] or 0), c["data_type"] or "",
                                    (c["is_nullable"] or "").upper() == "YES", c["remarks"]))

    edges: list[Edge] = []
    for d in view_deps:
        edges.append(Edge(rs_key(RS_DATABASE, d["src_schema"], d["src_name"]),
                          rs_key(RS_DATABASE, d["dst_schema"], d["dst_name"]), "view_dependency"))
    consumers: dict[str, list[str]] = {}
    for sc in share_consumers:
        consumers.setdefault(sc["share_name"], []).append(sc["consumer_namespace"] or sc["consumer_account"])
    for so in share_objs:
        if so["object_type"] in ("table", "view", "materialized view") and "." in so["object_name"]:
            schema, name = so["object_name"].split(".", 1)
            for cons in consumers.get(so["share_name"], ["<no consumer>"]):
                edges.append(Edge(rs_key(RS_DATABASE, schema, name), f"datashare://{so['share_name']}/{cons}",
                                  "datashare", {"share": so["share_name"]}))
    for u in usage:
        edges.append(Edge(rs_key(RS_DATABASE, u["table_schema"], u["table_name"]),
                          f"user://{u['usename']}", "query_consumer"))

    metrics = [Metric(rs_key(RS_DATABASE, r["table_schema"], r["table_name"]), "", "row_count",
                      float(r["tbl_rows"] or 0), now) for r in row_counts]
    return list(by_table.values()), edges, metrics


def extract_outbound_extracts() -> tuple[list[Asset], list[Edge]]:
    """Inventory JSON: [{"name","target","schedule","sources":["redshift://db/schema/view", ...]}]"""
    if not EXTRACT_INVENTORY_S3:
        return [], []
    bucket, key = EXTRACT_INVENTORY_S3.removeprefix("s3://").split("/", 1)
    items = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    assets, edges = [], []
    for it in items:
        k = f"extract://{it['name']}".lower()
        assets.append(Asset(k, "extract", "extract", None, None, it["name"],
                            comment=f"Outbound to {it.get('target')} on {it.get('schedule')}"))
        edges += [Edge(src.lower(), k, "extract", {"target": it.get("target")}) for src in it.get("sources", [])]
    return assets, edges


def extract_glue_dq(since: datetime) -> list[Metric]:
    """Glue Data Quality rule outcomes since the last successful run (aggregate pass/fail only)."""
    metrics = []
    for page in glue.get_paginator("list_data_quality_results").paginate(Filter={"StartedAfter": since}):
        for r in page["Results"]:
            res = glue.get_data_quality_result(ResultId=r["ResultId"])
            tbl = res.get("DataSource", {}).get("GlueTable")
            if not tbl:
                continue
            key = glue_key(tbl["DatabaseName"], tbl["TableName"])
            for rule in res.get("RuleResults", []):
                metrics.append(Metric(key, "", f"rule:{rule['Name']}",
                                      1.0 if rule["Result"] == "PASS" else 0.0, res["CompletedOn"]))
    return metrics


# ---------------------------------------------------------------- 3. fingerprint
def embedding_text(a: Asset, steward: str | None, ai_draft: str | None) -> str:
    """Stable text only: no volatile metrics, so embeddings don't churn daily."""
    desc = steward or a.comment or (f"[AI draft] {ai_draft}" if ai_draft else "")
    loc = ".".join(p for p in (a.database_name, a.schema_name, a.object_name) if p)
    return f"{a.platform} {a.asset_type} {loc}\n{desc}".strip()


def column_chunks(a: Asset) -> list[str]:
    cols = sorted(a.columns, key=lambda c: c.ordinal)
    return ["\n".join(f"{c.name} ({c.data_type}){': ' + c.comment if c.comment else ''}"
                      for c in cols[i:i + COLUMNS_PER_CHUNK]) for i in range(0, len(cols), COLUMNS_PER_CHUNK)]


# ---------------------------------------------------------------- 4-5. diff + upsert
def upsert_assets(cur, run_id: str, assets: list[Asset], frozen_platforms: list[str]) -> dict:
    cur.execute("select asset_id, asset_key, struct_hash, doc_hash, steward_description, ai_description, "
                "ai_description_status, is_deleted, platform from asset")
    existing = {r[1]: r for r in cur.fetchall()}
    stats = {"new": 0, "changed": 0, "unchanged": 0}
    seen = set()

    for a in assets:
        seen.add(a.asset_key)
        prev = existing.get(a.asset_key)
        steward = prev[4] if prev else None
        ai_draft = prev[5] if prev else None
        s_hash = a.struct_hash()
        d_hash = sha256(embedding_text(a, steward, ai_draft) + "\n" + "\n".join(column_chunks(a)))

        if prev is None:
            stats["new"] += 1
            cur.execute("insert into schema_change(run_id, asset_key, change_type) values (%s,%s,'asset_added')",
                        (run_id, a.asset_key))
        elif prev[2] != s_hash or prev[7]:
            stats["changed"] += 1
            log_column_drift(cur, run_id, prev[0], a)
        else:
            stats["unchanged"] += 1

        cur.execute("""
            insert into asset(asset_key, platform, asset_type, database_name, schema_name, object_name,
                              source_comment, struct_hash, doc_hash, source_updated_at,
                              first_seen_run, last_seen_run, last_seen_at, missed_runs, is_deleted)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),0,false)
            on conflict (asset_key) do update set
                asset_type=excluded.asset_type, source_comment=excluded.source_comment,
                struct_hash=excluded.struct_hash, doc_hash=excluded.doc_hash,
                source_updated_at=excluded.source_updated_at, last_seen_run=excluded.last_seen_run,
                last_seen_at=now(), missed_runs=0, is_deleted=false,
                updated_at = case when asset.struct_hash <> excluded.struct_hash
                                    or asset.doc_hash <> excluded.doc_hash then now() else asset.updated_at end
            returning asset_id""",
            (a.asset_key, a.platform, a.asset_type, a.database_name, a.schema_name, a.object_name,
             a.comment, s_hash, d_hash, a.source_updated_at, run_id, run_id))
        asset_id = cur.fetchone()[0]

        if prev is None or prev[2] != s_hash or prev[7]:
            sync_columns(cur, asset_id, a)
            # 8. enrichment queue: only if no human-approved description exists
            if not steward and (prev is None or prev[6] != "approved"):
                cur.execute("""insert into enrichment_task(asset_key, doc_hash, reason) values (%s,%s,%s)
                               on conflict do nothing""",
                            (a.asset_key, d_hash, "new_asset" if prev is None else "structure_changed"))
                cur.execute("update asset set ai_description_status='pending' where asset_id=%s "
                            "and ai_description_status in ('none','rejected')", (asset_id,))

    # 10. retire assets missing from today's harvest (only platforms that harvested successfully)
    missing = [k for k, r in existing.items() if k not in seen and not r[7] and r[8] not in frozen_platforms]
    cur.execute("update asset set missed_runs = missed_runs + 1 where asset_key = any(%s)", (missing,))
    cur.execute("""update asset set is_deleted = true, updated_at = now()
                   where missed_runs >= %s and not is_deleted returning asset_key""", (MISSED_RUNS_TO_DELETE,))
    retired = [r[0] for r in cur.fetchall()]
    for k in retired:
        cur.execute("insert into schema_change(run_id, asset_key, change_type) values (%s,%s,'asset_removed')",
                    (run_id, k))
    cur.execute("delete from embedding where asset_key = any(%s)", (retired,))
    stats["retired"] = len(retired)
    return stats


def log_column_drift(cur, run_id: str, asset_id: int, a: Asset) -> None:
    cur.execute("select column_name, data_type, is_nullable from asset_column where asset_id=%s", (asset_id,))
    old = {r[0]: r for r in cur.fetchall()}
    new = {c.name: c for c in a.columns}
    rows = []
    for name in new.keys() - old.keys():
        rows.append((run_id, a.asset_key, "column_added", name, None, new[name].data_type))
    for name in old.keys() - new.keys():
        rows.append((run_id, a.asset_key, "column_removed", name, old[name][1], None))
    for name in new.keys() & old.keys():
        if (old[name][1] or "").lower() != new[name].data_type.lower():
            rows.append((run_id, a.asset_key, "type_changed", name, old[name][1], new[name].data_type))
        if old[name][2] is not None and new[name].is_nullable is not None and old[name][2] != new[name].is_nullable:
            rows.append((run_id, a.asset_key, "nullability_changed", name, str(old[name][2]), str(new[name].is_nullable)))
    if rows:
        cur.executemany("""insert into schema_change(run_id, asset_key, change_type, column_name, old_value, new_value)
                           values (%s,%s,%s,%s,%s,%s)""", rows)
        cur.execute("""insert into dq_issue(asset_key, issue_type, severity, detail) values (%s,'schema_drift',%s,%s)
                       on conflict (asset_key, column_name, issue_type) where status='open'
                       do update set last_detected=now(), detail=excluded.detail""",
                    (a.asset_key, "high" if any(r[2] in ("column_removed", "type_changed") for r in rows) else "medium",
                     json.dumps({"changes": [{"type": r[2], "column": r[3]} for r in rows]})))


def sync_columns(cur, asset_id: int, a: Asset) -> None:
    """Upsert columns; keep steward/AI column descriptions for columns that still exist."""
    cur.executemany("""
        insert into asset_column(asset_id, column_name, ordinal, data_type, is_nullable, source_comment)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (asset_id, column_name) do update set ordinal=excluded.ordinal, data_type=excluded.data_type,
            is_nullable=excluded.is_nullable, source_comment=excluded.source_comment""",
        [(asset_id, c.name, c.ordinal, c.data_type, c.is_nullable, c.comment) for c in a.columns])
    cur.execute("delete from asset_column where asset_id=%s and not (column_name = any(%s))",
                (asset_id, [c.name for c in a.columns]))


# ---------------------------------------------------------------- 6. lineage
def upsert_edges(cur, run_id: str, edges: list[Edge]) -> int:
    uniq = {(e.src, e.dst, e.edge_type): e for e in edges}
    cur.executemany("""
        insert into lineage_edge(src_asset_key, dst_key, edge_type, attrs, last_seen_run, last_seen_at, is_active)
        values (%s,%s,%s,%s,%s,now(),true)
        on conflict (src_asset_key, dst_key, edge_type) do update set
            attrs=excluded.attrs, last_seen_run=excluded.last_seen_run, last_seen_at=now(), is_active=true""",
        [(e.src, e.dst, e.edge_type, json.dumps(e.attrs), run_id) for e in uniq.values()])
    # Structural edges (views, shares, extracts) are complete snapshots: inactive as soon as they vanish.
    cur.execute("""update lineage_edge set is_active=false where is_active and edge_type <> 'query_consumer'
                   and last_seen_run <> %s""", (run_id,))
    # Usage edges are sampled daily: keep them for a rolling window.
    cur.execute("""update lineage_edge set is_active=false where is_active and edge_type = 'query_consumer'
                   and last_seen_at < now() - make_interval(days => %s)""", (EDGE_EXPIRY_DAYS,))
    return len(uniq)


# ---------------------------------------------------------------- 7. data quality
def record_metrics_and_issues(cur, run_id: str, metrics: list[Metric]) -> dict:
    cur.executemany("""insert into dq_metric(run_id, asset_key, column_name, metric, value, measured_at)
                       values (%s,%s,%s,%s,%s,%s) on conflict do nothing""",
                    [(run_id, m.asset_key, m.column_name, m.metric, m.value, m.measured_at) for m in metrics])
    found: list[tuple] = []  # (asset_key, column, issue_type, severity, detail)

    for m in metrics:
        if m.metric == "hours_since_update" and m.value > STALE_HOURS_DEFAULT:
            sev = "high" if m.value > 3 * STALE_HOURS_DEFAULT else "medium"
            found.append((m.asset_key, "", "stale", sev, {"hours_since_update": round(m.value, 1)}))
        elif m.metric.startswith("rule:") and m.value == 0.0:
            found.append((m.asset_key, "", "rule_failed", "medium", {"rule": m.metric[5:]}))
        elif m.metric in ("row_count", "null_rate", "dup_rate"):
            cur.execute("""select value from dq_metric where asset_key=%s and column_name=%s and metric=%s
                           and measured_at >= now() - make_interval(days => %s) and measured_at < %s""",
                        (m.asset_key, m.column_name, m.metric, BASELINE_DAYS, m.measured_at))
            hist = [r[0] for r in cur.fetchall() if r[0] is not None]
            if len(hist) < 5:
                continue  # not enough baseline yet
            mu, sd = mean(hist), pstdev(hist)
            if m.metric == "row_count" and sd > 0 and abs(m.value - mu) / sd > VOLUME_Z_THRESHOLD:
                found.append((m.asset_key, "", "volume_anomaly", "high" if m.value < mu else "medium",
                              {"today": m.value, "baseline_mean": round(mu), "z": round((m.value - mu) / sd, 2)}))
            elif m.metric == "null_rate" and m.value - mu > NULL_SPIKE_ABS:
                found.append((m.asset_key, m.column_name, "null_spike", "medium",
                              {"today": m.value, "baseline": round(mu, 4)}))
            elif m.metric == "dup_rate" and m.value > 0 and m.value > mu * 2:
                found.append((m.asset_key, m.column_name, "duplicates", "medium",
                              {"today": m.value, "baseline": round(mu, 4)}))

    for k, col, typ, sev, detail in found:
        cur.execute("""insert into dq_issue(asset_key, column_name, issue_type, severity, detail)
                       values (%s,%s,%s,%s,%s)
                       on conflict (asset_key, column_name, issue_type) where status='open'
                       do update set last_detected=now(), severity=excluded.severity, detail=excluded.detail""",
                    (k, col, typ, sev, json.dumps(detail)))
    # Auto-resolve metric-driven issues not re-detected today (drift is resolved by a steward).
    cur.execute("""update dq_issue set status='resolved' where status='open'
                   and issue_type in ('stale','volume_anomaly','null_spike','duplicates','rule_failed')
                   and last_detected < now() - interval '20 hours'""")
    return {"metrics": len(metrics), "issues_detected": len(found)}


# ---------------------------------------------------------------- 9. embeddings
def embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text[:30000], "dimensions": EMBED_DIM, "normalize": True})
    for attempt in range(5):
        try:
            resp = bedrock.invoke_model(modelId=EMBED_MODEL_ID, body=body)
            return json.loads(resp["body"].read())["embedding"]
        except bedrock.exceptions.ThrottlingException:
            time.sleep(2 ** attempt)
    raise RuntimeError("embedding throttled after retries")


def refresh_embeddings(cur, assets: dict[str, Asset]) -> int:
    """Re-embed only assets whose doc_hash differs from what's stored for this model."""
    cur.execute("""
        select a.asset_key, a.doc_hash, a.steward_description, a.ai_description
        from asset a
        where not a.is_deleted and not exists (
            select 1 from embedding e where e.asset_key = a.asset_key and e.chunk_type = 'asset'
              and e.model_id = %s and e.doc_hash = a.doc_hash)""", (EMBED_MODEL_ID,))
    todo = cur.fetchall()
    for key, d_hash, steward, ai_draft in todo:
        a = assets.get(key)
        if a is None:
            continue
        chunks = [("asset", 0, embedding_text(a, steward, ai_draft))]
        chunks += [("columns", i, f"{a.object_name} columns:\n{t}") for i, t in enumerate(column_chunks(a))]
        cur.execute("delete from embedding where asset_key=%s and model_id=%s", (key, EMBED_MODEL_ID))
        cur.executemany("""insert into embedding(asset_key, chunk_type, chunk_ix, model_id, doc_hash, content, embedding)
                           values (%s,%s,%s,%s,%s,%s,%s)""",
                        [(key, ct, ix, EMBED_MODEL_ID, d_hash, txt, embed(txt)) for ct, ix, txt in chunks])
    return len(todo)


# ---------------------------------------------------------------- orchestration
def put_metrics(stats: dict) -> None:
    data = [{"MetricName": k, "Value": float(v), "Unit": "Count"}
            for k, v in stats.items() if isinstance(v, (int, float))]
    if data:
        cloudwatch.put_metric_data(Namespace="EQH/AIDataAssistant/DailySync", MetricData=data)


def main() -> None:
    run_id = str(uuid.uuid4())
    with psycopg.connect(PG_DSN, autocommit=False) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("select pg_try_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
            if not cur.fetchone()[0]:
                log.warning("another sync is running; exiting")
                return
            cur.execute("insert into sync_run(run_id) values (%s)", (run_id,))
            cur.execute("select coalesce(max(started_at), now() - interval '2 days') from sync_run "
                        "where status='succeeded'")
            since = cur.fetchone()[0]
            conn.commit()
            try:
                # 1-2. extract + normalize (sources fail independently; a failed source must not retire its assets)
                assets, edges, metrics, failed = [], [], [], []
                for name, fn in (("glue", extract_glue), ("redshift", extract_redshift),
                                 ("extracts", extract_outbound_extracts), ("glue_dq", lambda: extract_glue_dq(since))):
                    try:
                        out = fn()
                        if name == "glue":
                            assets += out[0]; metrics += out[1]
                        elif name == "redshift":
                            assets += out[0]; edges += out[1]; metrics += out[2]
                        elif name == "extracts":
                            assets += out[0]; edges += out[1]
                        else:
                            metrics += out
                    except Exception:
                        log.exception("source %s failed", name)
                        failed.append(name)
                # A platform we couldn't read is "frozen": its assets are neither counted missing nor retired.
                source_platform = {"glue": "glue", "redshift": "redshift", "extracts": "extract"}
                frozen = [source_platform[f] for f in failed if f in source_platform]

                stats = {"assets_harvested": len(assets), "sources_failed": len(failed)}
                with conn.transaction():
                    stats.update(upsert_assets(cur, run_id, assets, frozen))
                    stats["edges"] = upsert_edges(cur, run_id, edges)
                    stats.update(record_metrics_and_issues(cur, run_id, metrics))
                stats["reembedded"] = refresh_embeddings(cur, {a.asset_key: a for a in assets})
                conn.commit()

                cur.execute("analyze asset; analyze embedding; analyze dq_metric")
                cur.execute("update sync_run set status=%s, finished_at=now(), stats=%s where run_id=%s",
                            ("failed" if failed else "succeeded", json.dumps(stats), run_id))
                conn.commit()
                put_metrics(stats)
                log.info("run %s done: %s", run_id, stats)
            except Exception as exc:
                conn.rollback()
                cur.execute("update sync_run set status='failed', finished_at=now(), error=%s where run_id=%s",
                            (str(exc)[:2000], run_id))
                conn.commit()
                raise
            finally:
                cur.execute("select pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
                conn.commit()


if __name__ == "__main__":
    main()
