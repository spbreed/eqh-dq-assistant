"""Daily metadata + DQ + vector sync (SPEC Phase 4b), adapted from reference/daily_sync.py.

Changes vs the reference:
  1. Redshift Serverless usage from SYS_QUERY_HISTORY (provisioned STL path kept behind RS_CLUSTER_ID).
  2. Late-binding/regular/materialized view lineage parsed with sqlglot: table- and column-level (attrs.columns).
  3. Spectrum edges glue://eqh_silver/x -> redshift://eqh/spectrum_silver/x; raw->silver edges from
     config/lineage_raw_to_silver.yaml; silver->core COPY edges.
  4. Profiler output ingested into dq_metric; new issue types ri_orphans, overlap, invalid_values.
  5. Metrics and issues segmented by payer_code / state.
  6. --as-of backfill; glossary harvest + embedding; last_read_at / read_count_30d; batched writes.
  7. business_domain / state tagging from config/domain_rules.yaml; entitlements from config/entitlements.yaml.
All access is through Data APIs; only metadata and aggregate metrics are stored or embedded (PHI guard).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean, pstdev

import boto3
import yaml

from jobs.common import settings
from jobs.common.db import MetaDB
from jobs.common.redshift import Redshift
from jobs.daily_sync.lineage import parse_view, referenced_tables

log = logging.getLogger("daily_sync")
ROOT = settings.ROOT
DB = "eqh"
RS_SCHEMAS = ("core", "careempower", "vbc_mart", "outbound")
COLUMNS_PER_CHUNK = 40
MISSED_RUNS_TO_DELETE = 2
EDGE_EXPIRY_DAYS = 30
VOLUME_Z = 3.0
NULL_SPIKE_ABS = 0.10
BASELINE_DAYS = 14
MIN_BASELINE = 5
INTERNAL_USERS = {"eqh_admin", "rdsdb", "IAMR:eqh-dq-harvest-task-role"}
# Entities delivered weekly/monthly or loaded once: daily volume is not meaningful for them.
NON_DAILY = {"pcp_assignment", "payer_gap_file", "member_risk_score", "practice", "provider", "practice_contract",
             "health_at_home_episode", "practice_incentive_payment", "shared_savings_settlement"}
MIN_VOLUME_CHANGE = 0.30
METRIC_ISSUE_TYPES = ("stale", "volume_anomaly", "null_spike", "duplicates", "rule_failed", "ri_orphans", "overlap",
                      "invalid_values")


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


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def rs_key(schema: str, name: str) -> str:
    return f"redshift://{DB}/{schema}/{name}".lower()


def glue_key(db: str, name: str) -> str:
    return f"glue://{db}/{name}".lower()


def norm_type(t: str) -> str:
    t = (t or "").lower()
    return {"character varying": "varchar", "double precision": "double", "integer": "int"}.get(t.split("(")[0], t)


# ---------------------------------------------------------------- 1. extract
class Harvester:
    def __init__(self, as_of: datetime, backfill: bool):
        s = settings.get()
        self.s = s
        self.as_of = as_of
        self.backfill = backfill
        self.glue = boto3.client("glue", region_name=s["region"])
        self.s3 = boto3.client("s3", region_name=s["region"])
        self.rs = Redshift()
        if not self.rs.secret_arn and not os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
            # local/cloud-session runs use the admin secret through the Data API; Fargate uses its IAM role
            self.rs.secret_arn = s["redshift_admin_secret_arn"]

    def glue_assets(self) -> list[Asset]:
        assets = []
        for db in ("eqh_raw", "eqh_silver"):
            for page in self.glue.get_paginator("get_tables").paginate(DatabaseName=db):
                for t in page["TableList"]:
                    sd = t.get("StorageDescriptor", {})
                    cols = sd.get("Columns", []) + t.get("PartitionKeys", [])
                    assets.append(Asset(
                        glue_key(db, t["Name"]), "glue", "view" if t.get("TableType") == "VIRTUAL_VIEW" else "table",
                        db, None, t["Name"], comment=t.get("Description"), source_updated_at=t.get("UpdateTime"),
                        columns=[Column(c["Name"], i, c.get("Type", ""), None, c.get("Comment"))
                                 for i, c in enumerate(cols)]))
        return assets

    def redshift(self) -> tuple[list[Asset], list[Edge], dict]:
        schemas = ",".join(f"'{s}'" for s in RS_SCHEMAS)
        tables = self.rs.query(f"""
            select table_schema, table_name, table_type, remarks from svv_tables
            where table_catalog = current_database() and table_schema in ({schemas})""")
        cols = self.rs.query(f"""
            select table_schema, table_name, column_name, ordinal_position, data_type, is_nullable, remarks
            from svv_columns where table_catalog = current_database() and table_schema in ({schemas})""")
        views = self.rs.query(f"""
            select schemaname, viewname, definition from pg_views where schemaname in ({schemas})""")
        mvs = {r["name"] for r in self.rs.query(
            f"select trim(schema_name) || '.' || trim(name) as name from svv_mv_info where trim(schema_name) in ({schemas})")}
        lbv_cols = self.rs.query("""
            select * from pg_get_late_binding_view_cols()
              cols(view_schema name, view_name name, col_name name, col_type varchar, col_num int)""")
        ext = self.rs.query("select schemaname, tablename from svv_external_tables where schemaname = 'spectrum_silver'")
        ext_cols = self.rs.query("""
            select schemaname, tablename, columnname, external_type, columnnum from svv_external_columns
            where schemaname = 'spectrum_silver'""")
        shares = self.rs.query("select share_name, object_type, object_name from svv_datashare_objects "
                               "where share_type = 'OUTBOUND'")

        by: dict[tuple, Asset] = {}
        for t in tables:
            sch, name = t["table_schema"], t["table_name"]
            typ = "materialized_view" if f"{sch}.{name}" in mvs else ("view" if "VIEW" in (t["table_type"] or "")
                                                                       else "table")
            by[(sch, name)] = Asset(rs_key(sch, name), "redshift", typ, DB, sch, name, comment=t["remarks"])
        for c in cols:
            a = by.get((c["table_schema"], c["table_name"]))
            if a:
                a.columns.append(Column(c["column_name"], int(c["ordinal_position"] or 0), c["data_type"] or "",
                                        (c["is_nullable"] or "").upper() == "YES", c["remarks"]))
        for c in lbv_cols:  # late-binding views have no rows in svv_columns
            a = by.get((c["view_schema"], c["view_name"]))
            if a and not any(x.name == c["col_name"] for x in a.columns):
                a.columns.append(Column(c["col_name"], int(c["col_num"]), c["col_type"], None))
        for e in ext:
            a = Asset(rs_key("spectrum_silver", e["tablename"]), "redshift", "external_table", DB, "spectrum_silver",
                      e["tablename"], comment=None)
            a.columns = [Column(c["columnname"], int(c["columnnum"]), c["external_type"], None)
                         for c in ext_cols if c["tablename"] == e["tablename"]]
            by[("spectrum_silver", e["tablename"])] = a

        edges: list[Edge] = []
        for v in views:
            dst = rs_key(v["schemaname"], v["viewname"])
            srcs, mapping = parse_view(v["definition"] or "", default_schema=v["schemaname"])
            per_src = defaultdict(list)
            for m in mapping:
                per_src[m["src"]].append({"src_col": m["src_col"], "dst_col": m["dst_col"]})
            late = "no schema binding" in (v["definition"] or "").lower()
            for src in srcs:
                sch, name = src.split(".", 1)
                cols_map = [dict(t) for t in {tuple(sorted(d.items())) for d in per_src.get(src, [])}]
                edges.append(Edge(rs_key(sch, name), dst, "view_dependency",
                                  {"late_binding": late, "columns": sorted(cols_map, key=lambda d: (d["src_col"], d["dst_col"]))}))
        # Spectrum: Glue silver table -> external table
        for e in ext:
            edges.append(Edge(glue_key("eqh_silver", e["tablename"]), rs_key("spectrum_silver", e["tablename"]),
                              "spectrum"))
        # Datashares: object -> share asset -> consumer
        consumers = yaml.safe_load((ROOT / "config" / "datashare_consumers.yaml").read_text())
        share_assets = {}
        for so in shares:
            if "." not in so["object_name"] or so["object_type"] in ("schema",):
                continue
            sch, name = so["object_name"].split(".", 1)
            sk = f"datashare://{DB}/{so['share_name']}"
            share_assets[sk] = so["share_name"]
            edges.append(Edge(rs_key(sch, name), sk, "datashare", {"share": so["share_name"]}))
        assets = list(by.values())
        for sk, name in share_assets.items():
            c = consumers.get(name, {})
            assets.append(Asset(sk, "datashare", "datashare", DB, None, name,
                                comment=f"Outbound datashare for {c.get('team', 'unknown consumer')}"))
            edges.append(Edge(sk, f"consumer://{c.get('consumer', 'unknown')}", "datashare_consumer",
                              {"team": c.get("team")}))
        return assets, edges, {"views_parsed": len(views)}

    def usage(self) -> tuple[list[Edge], dict[str, tuple[datetime, int]]]:
        """Readers per asset from SYS_QUERY_HISTORY (Serverless). Backfill: simulated day from query_label."""
        if os.environ.get("RS_CLUSTER_ID"):
            rows = self.rs.query("""
                select trim(u.usename) as username, q.starttime as start_time, '' as query_label, q.querytxt as query_text
                from stl_query q join pg_user u on q.userid = u.usesysid
                where q.starttime > dateadd(day, -30, getdate())""")
        else:
            rows = self.rs.query("""
                select trim(username) as username, start_time, trim(query_label) as query_label, query_text
                from sys_query_history
                where status = 'success' and query_type = 'SELECT' and start_time > dateadd(day, -7, getdate())
                  and query_text not ilike '%%pg_catalog%%' and query_text not ilike '%%svv_%%'""")
        window_start = self.as_of - timedelta(days=30)
        last: dict[str, datetime] = {}
        count: dict[str, int] = defaultdict(int)
        edges = []
        for r in rows:
            user = (r["username"] or "").strip()
            if user in INTERNAL_USERS:
                continue
            label = r.get("query_label") or ""
            if label.startswith("simday:"):
                when = datetime.combine(date.fromisoformat(label[7:]), time(12), tzinfo=timezone.utc)
            elif self.backfill:
                continue  # real-time queries don't belong to a simulated day
            else:
                when = datetime.fromisoformat(str(r["start_time"]).replace(" ", "T")).replace(tzinfo=timezone.utc)
            if when > self.as_of or when < window_start:
                continue
            for t in referenced_tables(r["query_text"] or ""):
                sch, name = t.split(".", 1)
                if sch not in RS_SCHEMAS:
                    continue
                k = rs_key(sch, name)
                edges.append(Edge(k, f"user://{user}", "query_consumer"))
                count[k] += 1
                last[k] = max(last.get(k, when), when)
        return edges, {k: (last[k], count[k]) for k in last}

    def extracts(self) -> tuple[list[Asset], list[Edge]]:
        items = json.loads(self.s3.get_object(Bucket=self.s["bucket_extracts"], Key="inventory.json")["Body"].read())
        assets, edges = [], []
        for it in items:
            k = f"extract://{it['name']}".lower()
            assets.append(Asset(k, "extract", "extract", None, None, it["name"],
                                comment=f"Outbound file to {it.get('target')} ({it.get('schedule')}); owner {it.get('owner')}"))
            edges += [Edge(src.lower(), k, "extract", {"target": it.get("target")}) for src in it.get("sources", [])]
            edges.append(Edge(k, f"target://{it.get('target')}", "extract_target", {"schedule": it.get("schedule")}))
        return assets, edges

    def config_edges(self, glue_keys: set[str], rs_keys: set[str]) -> list[Edge]:
        cfg = yaml.safe_load((ROOT / "config" / "lineage_raw_to_silver.yaml").read_text())
        edges = []
        for e in cfg["edges"]:
            src, dst = glue_key("eqh_raw", e["raw"]), glue_key("eqh_silver", e["silver"])
            if src in glue_keys and dst in glue_keys:
                edges.append(Edge(src, dst, "raw_to_silver",
                                  {k: e[k] for k in ("payer_code", "state") if k in e}))
        for k in glue_keys:
            if k.startswith("glue://eqh_silver/"):
                core = rs_key("core", k.rsplit("/", 1)[1])
                if core in rs_keys:
                    edges.append(Edge(k, core, "copy_load"))
        return edges

    def profile_metrics(self) -> list[dict]:
        key = f"profile/dt={self.as_of.date().isoformat()}/metrics.jsonl"
        try:
            body = self.s3.get_object(Bucket=self.s["bucket_dq"], Key=key)["Body"].read().decode()
        except self.s3.exceptions.NoSuchKey:
            log.warning("no profiler output at %s", key)
            return []
        return [json.loads(line) for line in body.splitlines() if line.strip()]

    def glue_dq(self) -> list[dict]:
        """Glue Data Quality rule outcomes completed on the as-of day (aggregate pass/fail only)."""
        out = []
        day_start = datetime.combine(self.as_of.date(), time(0), tzinfo=timezone.utc)
        try:
            token, results = None, []
            while True:
                page = self.glue.list_data_quality_results(
                    Filter={"StartedAfter": day_start - timedelta(days=1)}, **({"NextToken": token} if token else {}))
                results += page["Results"]
                token = page.get("NextToken")
                if not token:
                    break
            if True:
                for r in results:
                    res = self.glue.get_data_quality_result(ResultId=r["ResultId"])
                    tbl = res.get("DataSource", {}).get("GlueTable")
                    if not tbl:
                        continue
                    for rule in res.get("RuleResults", []):
                        out.append({"asset_key": glue_key(tbl["DatabaseName"], tbl["TableName"]), "column_name": "",
                                    "metric": "rule:" + re.sub(r"\W+", "_", rule["Name"]).strip("_").lower(),
                                    "segment": "glue_dq", "value": 1.0 if rule["Result"] == "PASS" else 0.0,
                                    "measured_at": self.as_of.isoformat(),
                                    "description": rule.get("Description", "")[:200]})
        except Exception:
            log.exception("glue dq harvest failed")
        return out

    def glossary(self) -> list[dict]:
        terms = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.s["bucket_glossary"], Prefix="terms/"):
            for o in page.get("Contents", []):
                md = self.s3.get_object(Bucket=self.s["bucket_glossary"], Key=o["Key"])["Body"].read().decode()
                title = md.splitlines()[0].lstrip("# ").strip()
                syn = re.search(r"\*\*Synonyms:\*\*\s*(.*)", md)
                rel = re.search(r"\*\*Related:\*\*\s*(.*)", md)
                body = re.sub(r"\*\*(Synonyms|Related):\*\*.*", "", "\n".join(md.splitlines()[1:])).strip()
                terms.append({"term": title, "definition": body, "source_key": o["Key"],
                              "synonyms": [x.strip() for x in (syn.group(1) if syn else "").split(",") if x.strip()],
                              "related": [x.strip() for x in (rel.group(1) if rel else "").split(",") if x.strip()]})
        return terms


# ---------------------------------------------------------------- tagging + text
def domain_tagger():
    rules = yaml.safe_load((ROOT / "config" / "domain_rules.yaml").read_text())

    def tag(a: Asset) -> tuple[str | None, str | None]:
        name = a.object_name.lower()
        dom = next((r["domain"] for r in rules["domains"] if any(re.search(p, name) for p in r["patterns"])), None)
        toks = re.split(r"[_\W]+", name)
        st = None
        for tok in toks:
            for prefix, s in rules["states"].items():
                if tok == prefix or (len(tok) == 3 and tok.startswith(prefix) and tok[2].isdigit()):
                    st = s
        return dom, st
    return tag


def embedding_text(a: Asset, steward: str | None, ai_draft: str | None, domain: str | None) -> str:
    desc = steward or a.comment or (f"[AI draft] {ai_draft}" if ai_draft else "")
    loc = ".".join(p for p in (a.database_name, a.schema_name, a.object_name) if p)
    return f"{a.platform} {a.asset_type} {loc} (domain: {domain or 'unknown'})\n{desc}".strip()


def column_chunks(a: Asset) -> list[str]:
    cols = sorted(a.columns, key=lambda c: c.ordinal)
    return ["\n".join(f"{c.name} ({c.data_type}){': ' + c.comment if c.comment else ''}"
                      for c in cols[i:i + COLUMNS_PER_CHUNK]) for i in range(0, len(cols), COLUMNS_PER_CHUNK)]


# ---------------------------------------------------------------- 4-5. diff + upsert
def upsert_assets(db: MetaDB, run_id: str, assets: list[Asset], frozen: list[str], at: datetime) -> dict:
    existing = {r["asset_key"]: r for r in db.query(
        "select asset_id, asset_key, struct_hash, doc_hash, steward_description, ai_description, "
        "ai_description_status, is_deleted, platform from asset")}
    tag = domain_tagger()
    stats = {"new": 0, "changed": 0, "unchanged": 0}
    rows, drift_assets, enqueue = [], [], []
    for a in assets:
        prev = existing.get(a.asset_key)
        steward = prev["steward_description"] if prev else None
        ai = prev["ai_description"] if prev else None
        dom, st = tag(a)
        s_hash = a.struct_hash()
        d_hash = sha256(embedding_text(a, steward, ai, dom) + "\n" + "\n".join(column_chunks(a)))
        if prev is None:
            stats["new"] += 1
        elif prev["struct_hash"] != s_hash or prev["is_deleted"]:
            stats["changed"] += 1
            drift_assets.append(a)
        else:
            stats["unchanged"] += 1
        if (prev is None or prev["struct_hash"] != s_hash) and not steward and \
                (prev is None or prev["ai_description_status"] != "approved"):
            enqueue.append({"k": a.asset_key, "h": d_hash, "r": "new_asset" if prev is None else "structure_changed"})
        rows.append({"k": a.asset_key, "p": a.platform, "t": a.asset_type, "db": a.database_name, "sc": a.schema_name,
                     "o": a.object_name, "c": a.comment, "sh": s_hash, "dh": d_hash,
                     "su": a.source_updated_at.isoformat() if a.source_updated_at else None, "run": run_id,
                     "at": at, "dom": dom, "st": st})
    with db.transaction():
        if drift_assets:
            log_column_drift(db, run_id, drift_assets, at)
        db.executemany("""
            insert into asset(asset_key, platform, asset_type, database_name, schema_name, object_name, source_comment,
                              struct_hash, doc_hash, source_updated_at, first_seen_run, last_seen_run, last_seen_at,
                              missed_runs, is_deleted, business_domain, state, created_in_source_at)
            values (:k,:p,:t,:db,:sc,:o,:c,:sh,:dh,:su::timestamptz,:run::uuid,:run::uuid,:at,0,false,:dom,:st,:at)
            on conflict (asset_key) do update set
                asset_type=excluded.asset_type, source_comment=excluded.source_comment,
                struct_hash=excluded.struct_hash, doc_hash=excluded.doc_hash,
                source_updated_at=excluded.source_updated_at, last_seen_run=excluded.last_seen_run,
                last_seen_at=excluded.last_seen_at, missed_runs=0, is_deleted=false,
                business_domain=excluded.business_domain, state=excluded.state,
                updated_at = case when asset.struct_hash <> excluded.struct_hash
                                    or asset.doc_hash <> excluded.doc_hash then excluded.last_seen_at
                                  else asset.updated_at end""", rows)
        new_keys = [a.asset_key for a in assets if a.asset_key not in existing]
        if new_keys:
            db.executemany("insert into schema_change(run_id, asset_key, change_type, detected_at) "
                           "values (:run::uuid, :k, 'asset_added', :at)",
                           [{"run": run_id, "k": k, "at": at} for k in new_keys])
        changed = {a.asset_key for a in assets if a.asset_key not in existing} | {a.asset_key for a in drift_assets}
        sync_columns(db, [a for a in assets if a.asset_key in changed or not existing])
        if enqueue:
            db.executemany("insert into enrichment_task(asset_key, doc_hash, reason) values (:k,:h,:r) "
                           "on conflict do nothing", enqueue)
            db.execute("update asset set ai_description_status='pending' where ai_description_status in "
                       "('none','rejected') and asset_key in (select jsonb_array_elements_text(:keys::jsonb))",
                       {"keys": [e["k"] for e in enqueue]})
        seen = [a.asset_key for a in assets]
        missing = [k for k, r in existing.items() if k not in set(seen) and not r["is_deleted"]
                   and r["platform"] not in frozen]
        if missing:
            db.execute("update asset set missed_runs = missed_runs + 1 where asset_key in "
                       "(select jsonb_array_elements_text(:keys::jsonb))", {"keys": missing})
        retired = [r["asset_key"] for r in db.query(
            "update asset set is_deleted = true, updated_at = :at where missed_runs >= :n and not is_deleted "
            "returning asset_key", {"n": MISSED_RUNS_TO_DELETE, "at": at})]
        if retired:
            db.executemany("insert into schema_change(run_id, asset_key, change_type, detected_at) "
                           "values (:run::uuid,:k,'asset_removed',:at)",
                           [{"run": run_id, "k": k, "at": at} for k in retired])
            db.execute("delete from embedding where asset_key in (select jsonb_array_elements_text(:keys::jsonb))",
                       {"keys": retired})
    stats["retired"] = len(retired)
    stats["enqueued"] = len(enqueue)
    return stats


def log_column_drift(db: MetaDB, run_id: str, assets: list[Asset], at: datetime) -> None:
    old_rows = db.query("""select a.asset_key, c.column_name, c.data_type, c.is_nullable
                           from asset_column c join asset a using (asset_id)
                           where a.asset_key in (select jsonb_array_elements_text(:keys::jsonb))""",
                        {"keys": [a.asset_key for a in assets]})
    old: dict[str, dict] = defaultdict(dict)
    for r in old_rows:
        old[r["asset_key"]][r["column_name"]] = r
    changes, issues = [], []
    for a in assets:
        o, n = old[a.asset_key], {c.name: c for c in a.columns}
        rows = []
        for name in n.keys() - o.keys():
            rows.append(("column_added", name, None, n[name].data_type))
        for name in o.keys() - n.keys():
            rows.append(("column_removed", name, o[name]["data_type"], None))
        for name in n.keys() & o.keys():
            if norm_type(o[name]["data_type"]) != norm_type(n[name].data_type):
                rows.append(("type_changed", name, o[name]["data_type"], n[name].data_type))
        if not rows:
            continue
        changes += [{"run": run_id, "k": a.asset_key, "t": t, "c": c, "o": ov, "n": nv, "at": at} for t, c, ov, nv in rows]
        sev = "high" if any(r[0] in ("column_removed", "type_changed") for r in rows) else "medium"
        col = rows[0][1] if len(rows) == 1 else ""
        issues.append({"k": a.asset_key, "c": col, "s": sev, "at": at,
                       "d": {"changes": [{"type": t, "column": c, "old": ov, "new": nv} for t, c, ov, nv in rows]}})
    if changes:
        db.executemany("""insert into schema_change(run_id, asset_key, change_type, column_name, old_value, new_value,
                          detected_at) values (:run::uuid,:k,:t,:c,:o,:n,:at)""", changes)
    for i in issues:
        db.execute("""insert into dq_issue(asset_key, column_name, issue_type, severity, detail, first_detected,
                                           last_detected, segment)
                      values (:k,:c,'schema_drift',:s,:d::jsonb,:at,:at,'')
                      on conflict (asset_key, column_name, issue_type, segment) where status='open'
                      do update set last_detected=excluded.last_detected, detail=excluded.detail,
                                    severity=excluded.severity""", i)


def sync_columns(db: MetaDB, assets: list[Asset]) -> None:
    if not assets:
        return
    rows = [{"k": a.asset_key, "n": c.name, "o": c.ordinal, "t": c.data_type, "nl": c.is_nullable, "c": c.comment}
            for a in assets for c in a.columns]
    db.execute("""delete from asset_column c using asset a where a.asset_id = c.asset_id
                  and a.asset_key in (select jsonb_array_elements_text(:keys::jsonb))
                  and c.steward_description is null and c.ai_description is null""",
               {"keys": [a.asset_key for a in assets]})
    db.executemany("""
        insert into asset_column(asset_id, column_name, ordinal, data_type, is_nullable, source_comment)
        select asset_id, :n, :o, :t, :nl, :c from asset where asset_key = :k
        on conflict (asset_id, column_name) do update set ordinal=excluded.ordinal, data_type=excluded.data_type,
            is_nullable=excluded.is_nullable, source_comment=excluded.source_comment""", rows)
    # columns that vanished but carried descriptions: drop them too (description kept in review_action history)
    keep = defaultdict(list)
    for a in assets:
        keep[a.asset_key] = [c.name for c in a.columns]
    db.executemany("""delete from asset_column c using asset a where a.asset_id = c.asset_id and a.asset_key = :k
                      and not (c.column_name in (select jsonb_array_elements_text(:cols::jsonb)))""",
                   [{"k": k, "cols": v} for k, v in keep.items()])


# ---------------------------------------------------------------- 6. lineage
def upsert_edges(db: MetaDB, run_id: str, edges: list[Edge], at: datetime) -> int:
    uniq = {(e.src, e.dst, e.edge_type): e for e in edges}
    db.executemany("""
        insert into lineage_edge(src_asset_key, dst_key, edge_type, attrs, first_seen_at, last_seen_run, last_seen_at,
                                 is_active)
        values (:s,:d,:t,:a::jsonb,:at,:run::uuid,:at,true)
        on conflict (src_asset_key, dst_key, edge_type) do update set
            attrs=excluded.attrs, last_seen_run=excluded.last_seen_run, last_seen_at=excluded.last_seen_at,
            is_active=true""",
        [{"s": e.src, "d": e.dst, "t": e.edge_type, "a": e.attrs, "run": run_id, "at": at} for e in uniq.values()])
    db.execute("""update lineage_edge set is_active=false where is_active and edge_type <> 'query_consumer'
                  and last_seen_run <> :run::uuid""", {"run": run_id})
    db.execute("""update lineage_edge set is_active=false where is_active and edge_type = 'query_consumer'
                  and last_seen_at < :at::timestamptz - (:d * interval '1 day')""", {"at": at, "d": EDGE_EXPIRY_DAYS})
    return len(uniq)


def update_usage(db: MetaDB, usage: dict[str, tuple[datetime, int]]) -> None:
    db.execute("update asset set read_count_30d = 0 where read_count_30d <> 0")
    if usage:
        db.executemany("""update asset set last_read_at = greatest(coalesce(last_read_at, :t), :t),
                          read_count_30d = :n where asset_key = :k""",
                       [{"k": k, "t": t, "n": n} for k, (t, n) in usage.items()])


# ---------------------------------------------------------------- 7. data quality
def record_metrics_and_issues(db: MetaDB, run_id: str, metrics: list[dict], at: datetime) -> dict:
    rows = [{"run": run_id, "k": m["asset_key"], "c": m.get("column_name", ""), "m": m["metric"],
             "s": m.get("segment", ""), "v": m["value"], "t": m["measured_at"], "at": at} for m in metrics]
    db.executemany("""insert into dq_metric(run_id, asset_key, column_name, metric, segment, value, measured_at,
                                           ingested_at)
                      values (:run::uuid,:k,:c,:m,:s,:v,:t::timestamptz,:at)
                      on conflict do nothing""", rows)
    hist_rows = db.query("""select asset_key, column_name, metric, segment, value from dq_metric
                            where measured_at >= :at::timestamptz - (:d * interval '1 day')
                              and measured_at < :at::timestamptz - interval '1 hour'
                              and metric in ('daily_rows','null_rate','dup_rate','ri_orphan_rate','overlap_rate',
                                             'invalid_value_rate')""",
                         {"at": at, "d": BASELINE_DAYS})
    hist: dict[tuple, list[float]] = defaultdict(list)
    for r in hist_rows:
        hist[(r["asset_key"], r["column_name"], r["metric"], r["segment"])].append(r["value"])
    sla = {(m["asset_key"], m.get("segment", "")): m["value"] for m in metrics if m["metric"] == "freshness_sla_hours"}

    found: list[dict] = []

    def issue(m, typ, sev, detail):
        found.append({"k": m["asset_key"], "c": m.get("column_name", ""), "s": m.get("segment", ""), "t": typ,
                      "sev": sev, "d": detail, "at": at})

    for m in metrics:
        v, name, seg = m["value"], m["metric"], m.get("segment", "")
        h = hist.get((m["asset_key"], m.get("column_name", ""), name, seg), [])
        mu = mean(h) if h else None
        if name == "hours_since_last_ingest":
            limit = sla.get((m["asset_key"], seg), 36.0)
            if v > limit:
                issue(m, "stale", "high" if v > 3 * limit else "medium",
                      {"hours_since_last_ingest": round(v, 1), "sla_hours": limit})
        elif name.startswith("rule:") and v == 0.0:
            issue(m, "rule_failed", "high" if "eligibility" in name else "medium",
                  {"rule": name[5:], "source": "glue_dq" if seg == "glue_dq" else "profiler"})
        elif name.startswith("rule_fail_rate:") and v > 0:
            continue  # carried in rule:<name>; the rate is kept as a trend metric
        elif name == "daily_rows" and len(h) >= MIN_BASELINE \
                and m["asset_key"].rsplit("/", 1)[-1] not in NON_DAILY:
            sd = max(pstdev(h), mu ** 0.5)  # Poisson floor: small baselines are noisy
            z = (v - mu) / sd if sd > 0 else 0.0
            change = (v - mu) / mu if mu else 0.0
            if mu >= 20 and abs(z) > VOLUME_Z and abs(change) >= MIN_VOLUME_CHANGE:
                issue(m, "volume_anomaly", "high" if v < mu else "medium",
                      {"today": v, "baseline_mean": round(mu, 1), "z": round(z, 2),
                       "pct_change": round(100 * (v - mu) / mu, 1) if mu else None})
        elif name == "null_rate" and len(h) >= MIN_BASELINE and v - mu > NULL_SPIKE_ABS:
            issue(m, "null_spike", "medium", {"today": round(v, 4), "baseline": round(mu, 4)})
        elif name == "dup_rate" and v > 0.005 and (mu is None or v > max(2 * mu, 0.005) or v >= 0.005):
            issue(m, "duplicates", "medium", {"dup_rate": round(v, 4), "baseline": round(mu or 0, 4)})
        elif name == "ri_orphan_rate" and v > 0.005:
            issue(m, "ri_orphans", "medium", {"orphan_rate": round(v, 4), "baseline": round(mu or 0, 4)})
        elif name == "overlap_rate" and v > 0.01:
            issue(m, "overlap", "medium", {"overlap_rate": round(v, 4), "baseline": round(mu or 0, 4)})
        elif name == "invalid_value_rate" and v > 0.01:
            issue(m, "invalid_values", "medium", {"invalid_rate": round(v, 4), "baseline": round(mu or 0, 4)})

    # Segment issues on the same asset/type are kept; the whole-table twin is dropped if a segment explains it
    seg_types = {(f["k"], f["c"], f["t"]) for f in found if f["s"]}
    found = [f for f in found if f["s"] or (f["k"], f["c"], f["t"]) not in seg_types
             or f["t"] in ("stale", "rule_failed")]
    db.executemany("""insert into dq_issue(asset_key, column_name, issue_type, severity, detail, first_detected,
                                           last_detected, segment)
                      values (:k,:c,:t,:sev,:d::jsonb,:at,:at,:s)
                      on conflict (asset_key, column_name, issue_type, segment) where status='open'
                      do update set last_detected=excluded.last_detected, severity=excluded.severity,
                                    detail=excluded.detail""", found)
    resolved = db.query("""update dq_issue set status='resolved', resolved_at=:at
                           where status='open' and issue_type in (select jsonb_array_elements_text(:types::jsonb))
                             and last_detected < :at::timestamptz - interval '20 hours' returning id""",
                        {"at": at, "types": list(METRIC_ISSUE_TYPES)})
    return {"metrics": len(metrics), "issues_detected": len(found), "issues_resolved": len(resolved)}


# ---------------------------------------------------------------- entitlements + glossary
def sync_entitlements(db: MetaDB) -> int:
    cfg = yaml.safe_load((ROOT / "config" / "entitlements.yaml").read_text())
    rows = []
    for group, spec in cfg.items():
        for k in spec.get("assets", []):
            rows.append({"k": k, "c": "", "g": group})
        pats = [re.compile(p) for p in spec.get("column_patterns", [])]
        for r in db.query("select a.asset_key, c.column_name from asset_column c join asset a using (asset_id) "
                          "where not a.is_deleted"):
            if any(p.search(r["column_name"]) for p in pats):
                rows.append({"k": r["asset_key"], "c": r["column_name"], "g": group})
    with db.transaction():
        db.execute("delete from asset_entitlement")
        db.executemany("insert into asset_entitlement(asset_key, column_name, group_name) values (:k,:c,:g) "
                       "on conflict do nothing", rows)
    return len(rows)


def sync_glossary(db: MetaDB, terms: list[dict], at: datetime) -> list[dict]:
    rows = []
    for t in terms:
        h = sha256(json.dumps(t, sort_keys=True))
        rows.append({"t": t["term"], "d": t["definition"], "s": t["synonyms"], "r": t["related"], "k": t["source_key"],
                     "h": h, "at": at})
    db.executemany("""insert into glossary_term(term, definition, synonyms, related, source_key, doc_hash, updated_at)
                      values (:t,:d,(select coalesce(array_agg(x), '{}') from jsonb_array_elements_text(:s::jsonb) x),
                              (select coalesce(array_agg(x), '{}') from jsonb_array_elements_text(:r::jsonb) x),
                              :k,:h,:at)
                      on conflict (term) do update set definition=excluded.definition, synonyms=excluded.synonyms,
                         related=excluded.related, doc_hash=excluded.doc_hash,
                         updated_at=case when glossary_term.doc_hash <> excluded.doc_hash then excluded.updated_at
                                         else glossary_term.updated_at end""", rows)
    return rows


def glossary_edges(db: MetaDB, terms: list[dict]) -> list[Edge]:
    """Link glossary terms to assets whose names/comments mention the term or a synonym (metadata only)."""
    assets = db.query("select asset_key, object_name, coalesce(source_comment,'') as c from asset where not is_deleted")
    edges = []
    for t in terms:
        words = [t["term"]] + t["synonyms"]
        pats = [re.compile(r"\b" + re.escape(w.lower().replace(" ", "_")) + r"\b") for w in words if len(w) > 2]
        pats += [re.compile(r"\b" + re.escape(w.lower()) + r"\b") for w in words if len(w) > 2]
        for a in assets:
            text = f"{a['object_name']} {a['c']}".lower()
            if any(p.search(text) for p in pats):
                edges.append(Edge(f"glossary://{t['term']}".lower(), a["asset_key"], "glossary"))
    return edges


# ---------------------------------------------------------------- 9. embeddings
def refresh_embeddings(db: MetaDB, assets: dict[str, Asset], glossary_rows: list[dict]) -> dict:
    from jobs.common import embed as E
    s = settings.get()
    model = s["embed_model"]
    todo = db.query("""
        select a.asset_key, a.doc_hash, a.steward_description, a.ai_description, a.business_domain
        from asset a where not a.is_deleted and not exists (
            select 1 from embedding e where e.asset_key = a.asset_key and e.chunk_type = 'asset'
              and e.model_id = :m and e.doc_hash = a.doc_hash)""", {"m": model})
    chunks = []
    for r in todo:
        a = assets.get(r["asset_key"])
        if a is None:
            continue
        chunks.append((r["asset_key"], "asset", 0, r["doc_hash"],
                       embedding_text(a, r["steward_description"], r["ai_description"], r["business_domain"])))
        chunks += [(r["asset_key"], "columns", i, r["doc_hash"], f"{a.object_name} columns:\n{t}")
                   for i, t in enumerate(column_chunks(a))]
    have = {r["asset_key"]: r["doc_hash"] for r in db.query(
        "select asset_key, doc_hash from embedding where chunk_type='glossary' and model_id=:m", {"m": model})}
    for g in glossary_rows:
        k = f"glossary://{g['t']}".lower()
        if have.get(k) != g["h"]:
            chunks.append((k, "glossary", 0, g["h"],
                           f"Glossary term: {g['t']}\nSynonyms: {', '.join(g['s'])}\n{g['d']}"))
    if not chunks:
        return {"reembedded": 0}
    try:
        vectors = E.embed_many([c[4] for c in chunks])
    except E.EmbeddingUnavailable as e:
        log.warning("embeddings skipped: %s", e)
        return {"reembedded": 0, "embed_skipped": len(chunks)}
    keys = sorted({c[0] for c in chunks})
    with db.transaction():
        db.execute("delete from embedding where model_id = :m and asset_key in "
                   "(select jsonb_array_elements_text(:keys::jsonb))", {"m": model, "keys": keys})
        db.executemany("""insert into embedding(asset_key, chunk_type, chunk_ix, model_id, doc_hash, content, embedding)
                          values (:k,:t,:i,:m,:h,:c,:v::vector)""",
                       [{"k": c[0], "t": c[1], "i": c[2], "m": model, "h": c[3], "c": c[4], "v": E.vec(v)}
                        for c, v in zip(chunks, vectors)], chunk=50)
    return {"reembedded": len(keys)}


# ---------------------------------------------------------------- orchestration
def put_metrics(db: MetaDB, stats: dict, at: datetime) -> None:
    cw = boto3.client("cloudwatch", region_name=settings.get()["region"])
    data = [{"MetricName": k, "Value": float(v), "Unit": "Count"} for k, v in stats.items()
            if isinstance(v, (int, float))]
    if data:
        cw.put_metric_data(Namespace="EQH/AIDataAssistant/DailySync", MetricData=data)
    issues = db.query("""select coalesce(a.business_domain, 'unknown') as domain,
                                coalesce(a.state, substring(i.segment from 'state=(..)'),
                                         substring(i.segment from 'PAYER_(..)'), 'ALL') as state, count(*) as n
                         from dq_issue i left join asset a using (asset_key) where i.status = 'open'
                         group by 1, 2""")
    by_dom, by_state = defaultdict(int), defaultdict(int)
    for r in issues:
        by_dom[r["domain"]] += r["n"]
        by_state[r["state"]] += r["n"]
    md = [{"MetricName": "OpenIssues", "Dimensions": [{"Name": "Domain", "Value": k}], "Value": v} for k, v in by_dom.items()]
    md += [{"MetricName": "OpenIssues", "Dimensions": [{"Name": "State", "Value": k}], "Value": v}
           for k, v in by_state.items()]
    for i in range(0, len(md), 20):
        cw.put_metric_data(Namespace="EQH/AIDataAssistant/Issues", MetricData=md[i:i + 20])


def run(as_of: date | None = None) -> dict:
    backfill = as_of is not None and as_of < datetime.now(timezone.utc).date()
    at = datetime.combine(as_of, time(13, 30), tzinfo=timezone.utc) if as_of else datetime.now(timezone.utc)
    db = MetaDB(role="harvest")
    run_id = str(uuid.uuid4())
    if db.one("select count(*) from sync_run where status='running' and started_at > now() - interval '2 hours'"):
        log.warning("another sync is running; exiting")
        return {}
    db.execute("insert into sync_run(run_id, as_of) values (:r::uuid, :at)", {"r": run_id, "at": at})
    h = Harvester(at, backfill)
    try:
        assets, edges, metrics, failed, extra = [], [], [], [], {}
        rs_assets: list[Asset] = []
        for name, fn in (("glue", h.glue_assets), ("redshift", h.redshift), ("extracts", h.extracts)):
            try:
                out = fn()
                if name == "glue":
                    assets += out
                elif name == "redshift":
                    rs_assets, e, extra = out
                    assets += rs_assets
                    edges += e
                else:
                    assets += out[0]
                    edges += out[1]
            except Exception:
                log.exception("source %s failed", name)
                failed.append(name)
        frozen = [{"glue": "glue", "redshift": "redshift", "extracts": "extract"}[f] for f in failed]
        glue_keys = {a.asset_key for a in assets if a.platform == "glue"}
        rs_keys = {a.asset_key for a in rs_assets}
        edges += h.config_edges(glue_keys, rs_keys)
        usage_edges, usage = h.usage()
        edges += usage_edges
        metrics = h.profile_metrics() + h.glue_dq()

        stats = {"assets_harvested": len(assets), "sources_failed": len(failed), **extra}
        stats.update(upsert_assets(db, run_id, assets, frozen, at))
        terms = h.glossary()
        g_rows = sync_glossary(db, terms, at)
        edges += glossary_edges(db, terms)
        stats["edges"] = upsert_edges(db, run_id, edges, at)
        update_usage(db, usage)
        stats.update(record_metrics_and_issues(db, run_id, metrics, at))
        stats["entitlements"] = sync_entitlements(db)
        stats["glossary_terms"] = len(g_rows)
        stats.update(refresh_embeddings(db, {a.asset_key: a for a in assets}, g_rows))
        db.execute("analyze asset; ")
        db.execute("update sync_run set status=:s, finished_at=now(), stats=:st::jsonb where run_id=:r::uuid",
                   {"s": "failed" if failed else "succeeded", "st": stats, "r": run_id})
        try:
            put_metrics(db, stats, at)
        except Exception:
            log.exception("cloudwatch metrics failed")
        log.info("run %s (as of %s) done: %s", run_id, at.date(), stats)
        return stats
    except Exception as exc:
        db.execute("update sync_run set status='failed', finished_at=now(), error=:e where run_id=:r::uuid",
                   {"e": str(exc)[:2000], "r": run_id})
        raise


def redetect() -> None:
    """Re-run metric-based issue detection over stored metrics, day by day (after tuning thresholds).
    Schema-drift issues come from structural diffs and are kept."""
    db = MetaDB(role="harvest")
    runs = db.query("""select run_id::text, as_of from sync_run where status='succeeded' and as_of is not null
                       order by as_of""")
    db.execute("delete from dq_issue where issue_type <> 'schema_drift'")
    seen = set()
    for r in runs:
        at = datetime.fromisoformat(str(r["as_of"])[:19]).replace(tzinfo=timezone.utc)
        if at.date() in seen:
            continue
        seen.add(at.date())
        ms = db.query("""select asset_key, column_name, metric, segment, value, measured_at::text as measured_at
                         from dq_metric where measured_at::date = :d""", {"d": at.date()})
        stats = record_metrics_and_issues(db, r["run_id"], ms, at)
        log.info("redetect %s: %s", at.date(), stats)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None, help="simulated date (YYYY-MM-DD) for backfills")
    ap.add_argument("--redetect", action="store_true", help="replay issue detection over stored metrics")
    a = ap.parse_args()
    if a.redetect:
        redetect()
        return
    run(date.fromisoformat(a.as_of) if a.as_of else None)


if __name__ == "__main__":
    main()
