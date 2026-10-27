"""Profiler (SPEC Phase 4a): aggregate DQ metrics only — never row values.

Writes JSON lines to s3://<dq-results>/profile/dt=<as_of>/metrics.jsonl. Each metric:
{asset_key, column_name, metric, segment, value, measured_at}. segment is '' (whole asset) or
'payer_code=PAYER_TX2' / 'state=LA'. daily_sync ingests these into dq_metric.

Metrics: row_count, daily_rows, null_rate, dup_rate, ri_orphan_rate, overlap_rate, invalid_value_rate,
hours_since_last_ingest (+ freshness_sla_hours), and rule:<name> pass/fail with rule_fail_rate:<name>.
"""
from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone

import boto3

from datagen.domain import reference as R
from jobs.common import settings
from jobs.common.redshift import Redshift

log = logging.getLogger("profiler")
DB = "eqh"
MEASURE_HOUR_UTC = 13  # 06:00 America/Phoenix

# table -> (segment columns, null-rate columns, key columns for dup_rate)
CORE = {
    "member": (["payer_code", "state"], ["zip", "dob", "payer_member_id"], ["member_id"]),
    "eligibility_span": (["payer_code", "state"], ["start_date"], ["span_id"]),
    "pcp_assignment": (["payer_code", "state"], ["pcp_npi", "practice_id"], []),
    "claim_header": (["payer_code", "state"], ["member_id", "practice_id", "billing_npi"], ["claim_id"]),
    "claim_line": (["payer_code"], ["dx_code_1", "cpt_code"], ["claim_id", "line_no"]),
    "rx_claim": (["payer_code"], ["ndc"], ["rx_claim_id"]),
    "lab_result": (["state"], ["result_value", "loinc_code"], ["lab_id"]),
    "adt_event": (["state"], ["event_ts"], ["adt_id"]),
    "payer_gap_file": (["payer_code"], ["measure_code"], ["payer_gap_id"]),
    "care_gap": (["payer_code"], ["practice_id", "measure_code"], ["care_gap_id"]),
    "member_risk_score": ([], ["risk_tier"], []),
    "chw_encounter": ([], ["outcome"], ["encounter_id"]),
    "sdoh_screening": ([], ["z_code"], ["screening_id"]),
    "health_at_home_episode": (["state"], [], ["episode_id"]),
}
RI = [("claim_header", "member_id", "member", "member_id", ["payer_code"]),
      ("rx_claim", "member_id", "member", "member_id", ["payer_code"]),
      ("care_gap", "member_id", "member", "member_id", []),
      ("lab_result", "member_id", "member", "member_id", [])]
VALUE_SETS = {("sdoh_screening", "z_code"): sorted(R.VALID_Z_CODES), ("care_gap", "measure_code"): R.MEASURES,
              ("member", "state"): R.STATES}


def key(schema: str, name: str) -> str:
    return f"redshift://{DB}/{schema}/{name}"


def _seg_union(table: str, segs: list[str], select: str, where: str) -> str:
    """One query returning (segment, value...) for the whole table and each segment column."""
    parts = [f"SELECT '' AS segment, {select} FROM core.{table} WHERE {where}"]
    for s in segs:
        parts.append(f"SELECT '{s}=' || {s} AS segment, {select} FROM core.{table} WHERE {where} GROUP BY {s}")
    return "\nUNION ALL\n".join(parts)


def build_queries(as_of: date, full_load: bool) -> list[tuple[str, str, str, str]]:
    """Return [(asset_key, column, metric, sql)] where sql yields columns (segment, value)."""
    d = f"'{as_of.isoformat()}'::date"
    q: list[tuple[str, str, str, str]] = []
    for t, (segs, nulls, keys) in CORE.items():
        k = key("core", t)
        q.append((k, "", "row_count", _seg_union(t, segs, "count(*)::float AS value", f"ingest_date <= {d}")))
        if not full_load:
            q.append((k, "", "daily_rows", _seg_union(t, segs, "count(*)::float AS value", f"ingest_date = {d}")))
        for c in nulls:
            sel = f"avg(CASE WHEN {c} IS NULL THEN 1.0 ELSE 0.0 END) AS value"
            where = f"ingest_date {'<=' if full_load else '='} {d}"
            q.append((k, c, "null_rate", _seg_union(t, segs, sel, where)))
        if keys:
            kexpr = " || '|' || ".join(f"{c}::varchar" for c in keys)
            sel = f"1.0 - count(DISTINCT {kexpr})::float / nullif(count(*), 0) AS value"
            q.append((k, keys[0], "dup_rate", _seg_union(t, segs, sel, f"ingest_date <= {d}")))
    for child, col, parent, pcol, segs in RI:
        sel = "avg(CASE WHEN p.pk IS NULL THEN 1.0 ELSE 0.0 END) AS value"
        src = (f"core.{child} c LEFT JOIN (SELECT DISTINCT {pcol} AS pk FROM core.{parent} "
               f"WHERE ingest_date <= {d}) p ON p.pk = c.{col}")
        where = f"c.ingest_date {'<=' if full_load else '='} {d}"
        parts = [f"SELECT '' AS segment, {sel} FROM {src} WHERE {where}"]
        parts += [f"SELECT '{s}=' || c.{s} AS segment, {sel} FROM {src} WHERE {where} GROUP BY c.{s}"
                  for s in segs]
        q.append((key("core", child), col, "ri_orphan_rate", "\nUNION ALL\n".join(parts)))
    q.append((key("core", "eligibility_span"), "", "overlap_rate", f"""
        SELECT '' AS segment, count(DISTINCT a.member_id)::float /
               nullif((SELECT count(DISTINCT member_id) FROM core.eligibility_span WHERE ingest_date <= {d}), 0) AS value
        FROM core.eligibility_span a JOIN core.eligibility_span b
          ON a.member_id = b.member_id AND a.span_id < b.span_id
         AND a.start_date <= coalesce(b.end_date, '2099-12-31') AND b.start_date <= coalesce(a.end_date, '2099-12-31')
        WHERE a.ingest_date <= {d} AND b.ingest_date <= {d}"""))
    for (t, c), values in VALUE_SETS.items():
        vs = ",".join(f"'{v}'" for v in values)
        sel = f"avg(CASE WHEN {c} IS NOT NULL AND {c} NOT IN ({vs}) THEN 1.0 ELSE 0.0 END) AS value"
        where = f"ingest_date {'<=' if full_load else '='} {d}"
        q.append((key("core", t), c, "invalid_value_rate", f"SELECT '' AS segment, {sel} FROM core.{t} WHERE {where}"))
    # core freshness per feed segment (ADT by state, claims by payer)
    for t, seg in (("adt_event", "state"), ("claim_header", "payer_code"), ("lab_result", "")):
        if seg:
            q.append((key("core", t), "", "last_ingest_date", f"""
                SELECT '{seg}=' || {seg} AS segment, datediff(day, max(ingest_date), {d})::float AS value
                FROM core.{t} WHERE ingest_date <= {d} GROUP BY {seg}"""))
        q.append((key("core", t), "", "last_ingest_date",
                  f"SELECT '' AS segment, datediff(day, max(ingest_date), {d})::float AS value "
                  f"FROM core.{t} WHERE ingest_date <= {d}"))
    # rules (SQL equivalents of the DQDL rulesets; Glue DQ itself runs in the live pipeline)
    q.append((key("careempower", "open_care_gaps"), "member_id", "rule_fail_rate:open_gaps_active_eligibility", f"""
        SELECT '' AS segment, avg(CASE WHEN e.member_id IS NULL THEN 1.0 ELSE 0.0 END) AS value
        FROM careempower.open_care_gaps g
        LEFT JOIN (SELECT DISTINCT member_id FROM core.eligibility_span
                   WHERE start_date <= {d} AND coalesce(end_date, '2099-12-31') >= {d}) e ON e.member_id = g.member_id"""))
    q.append((key("core", "sdoh_screening"), "z_code", "rule_fail_rate:z_code_value_set",
              f"SELECT '' AS segment, avg(CASE WHEN z_code NOT IN "
              f"({','.join(repr(v) for v in sorted(R.VALID_Z_CODES))}) THEN 1.0 ELSE 0.0 END) AS value "
              f"FROM core.sdoh_screening WHERE ingest_date {'<=' if full_load else '='} {d}"))
    return q


RULE_THRESHOLDS = {"open_gaps_active_eligibility": 0.001, "z_code_value_set": 0.01}


def raw_freshness(as_of: date) -> list[dict]:
    """hours since the latest raw partition <= as_of, per raw feed (Glue partitions; metadata only)."""
    glue = boto3.client("glue", region_name=settings.get()["region"])
    payers = R.load_yaml("datagen/payers.yaml")
    sla = {}
    for p in payers["payers"].values():
        for f in p["feeds"].values():
            sla[f["table"]] = f["cadence_hours"] * 1.5
    for s in payers["states"].values():
        sla[s["hie_feed"]] = 36
    sla["raw_ehr_ccda_labs"] = sla["raw_careempower_ops"] = 36
    out = []
    measured = datetime.combine(as_of, time(MEASURE_HOUR_UTC), tzinfo=timezone.utc)
    for table, hours_sla in sla.items():
        latest = None
        for page in glue.get_paginator("get_partitions").paginate(DatabaseName="eqh_raw", TableName=table):
            for p in page["Partitions"]:
                v = date.fromisoformat(p["Values"][0])
                if v <= as_of and (latest is None or v > latest):
                    latest = v
        if latest is None:
            continue
        # files land ~02:00 UTC on their ingest date
        hours = (measured - datetime.combine(latest, time(2), tzinfo=timezone.utc)).total_seconds() / 3600
        k = f"glue://eqh_raw/{table}"
        out += [{"asset_key": k, "column_name": "", "metric": "hours_since_last_ingest", "segment": "",
                 "value": round(hours, 1)},
                {"asset_key": k, "column_name": "", "metric": "freshness_sla_hours", "segment": "", "value": hours_sla}]
    return out


def run(as_of: date, upload: bool = True) -> list[dict]:
    full_load = as_of == R.day0()
    rs = Redshift()  # IAM identity (Fargate) or RS_SECRET_ARN; falls back to admin secret locally
    if not rs.secret_arn and not _in_aws():
        rs.secret_arn = settings.get()["redshift_admin_secret_arn"]
    queries = build_queries(as_of, full_load)
    measured_at = datetime.combine(as_of, time(MEASURE_HOUR_UTC), tzinfo=timezone.utc).isoformat()

    def one(item):
        k, col, metric, sql = item
        rows = rs.query(sql)
        out = []
        for r in rows:
            if r["value"] is None:
                continue
            m = metric
            if metric == "last_ingest_date":  # days -> hours since last ingest (files land ~02:00 UTC)
                out.append({"asset_key": k, "column_name": col, "metric": "hours_since_last_ingest",
                            "segment": r["segment"], "value": float(r["value"]) * 24 + 11})
                out.append({"asset_key": k, "column_name": col, "metric": "freshness_sla_hours",
                            "segment": r["segment"], "value": 36.0})
                continue
            out.append({"asset_key": k, "column_name": col, "metric": m, "segment": r["segment"] or "",
                        "value": round(float(r["value"]), 6)})
            if metric.startswith("rule_fail_rate:"):
                name = metric.split(":", 1)[1]
                out.append({"asset_key": k, "column_name": col, "metric": f"rule:{name}", "segment": "",
                            "value": 0.0 if float(r["value"]) > RULE_THRESHOLDS[name] else 1.0})
        return out

    with ThreadPoolExecutor(8) as ex:
        metrics = [m for chunk in ex.map(one, queries) for m in chunk]
    metrics += raw_freshness(as_of)
    for m in metrics:
        m["measured_at"] = measured_at
    if upload:
        s3 = boto3.client("s3", region_name=settings.get()["region"])
        s3.put_object(Bucket=settings.get()["bucket_dq"], Key=f"profile/dt={as_of.isoformat()}/metrics.jsonl",
                      Body="\n".join(json.dumps(m) for m in metrics).encode())
    log.info("profiled %s: %d metrics from %d queries", as_of, len(metrics), len(queries))
    return metrics


def _in_aws() -> bool:
    import os
    return bool(os.environ.get("ECS_CONTAINER_METADATA_URI_V4"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=None)
    a = ap.parse_args()
    run(date.fromisoformat(a.as_of) if a.as_of else datetime.now(timezone.utc).date())


if __name__ == "__main__":
    main()
