"""Write per-day silver (Parquet) and raw (per-payer CSV with feed quirks) files, and Glue table definitions."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from datagen.domain import reference as R

BUILD = R.ROOT / "build" / "data"

# silver entity -> Glue/Redshift column types (order = Parquet/COPY order; ingest_date appended last)
SILVER_TYPES: dict[str, dict[str, str]] = {
    "member": {"member_id": "string", "payer_member_id": "string", "payer_code": "string", "state": "string",
               "dob": "date", "sex": "string", "zip": "string", "language": "string", "lob": "string",
               "program": "string", "enrollment_date": "date"},
    "eligibility_span": {"span_id": "string", "member_id": "string", "payer_code": "string", "state": "string",
                         "lob": "string", "program": "string", "start_date": "date", "end_date": "date",
                         "term_reason": "string"},
    "pcp_assignment": {"member_id": "string", "payer_code": "string", "state": "string", "pcp_npi": "string",
                       "practice_id": "string", "effective_month": "date", "assignment_source": "string"},
    "practice": {"practice_id": "string", "practice_name": "string", "practice_type": "string", "state": "string",
                 "tin": "string", "accelerated_reimbursement_flag": "boolean", "onboarded_date": "date"},
    "provider": {"npi": "string", "provider_label": "string", "specialty": "string", "practice_id": "string",
                 "state": "string", "is_pcp": "boolean"},
    "practice_contract": {"contract_id": "string", "practice_id": "string", "payer_code": "string",
                          "contract_type": "string", "effective_start": "date", "effective_end": "date",
                          "practice_share_pct": "double"},
    "claim_header": {"claim_id": "string", "member_id": "string", "payer_code": "string", "state": "string",
                     "claim_type": "string", "service_category": "string", "service_date": "date",
                     "received_date": "date", "billing_npi": "string", "practice_id": "string",
                     "total_allowed": "double", "total_paid": "double"},
    "claim_line": {"claim_id": "string", "line_no": "int", "payer_code": "string", "cpt_code": "string",
                   "dx_code_1": "string", "dx_code_2": "string", "units": "int", "paid_amount": "double",
                   "service_date": "date"},
    "rx_claim": {"rx_claim_id": "string", "member_id": "string", "payer_code": "string", "ndc": "string",
                 "drug_class": "string", "fill_date": "date", "days_supply": "int", "paid_amount": "double"},
    "lab_result": {"lab_id": "string", "member_id": "string", "state": "string", "loinc_code": "string",
                   "test_name": "string", "result_value": "double", "unit": "string", "result_date": "date",
                   "source": "string"},
    "adt_event": {"adt_id": "string", "member_id": "string", "state": "string", "hie_feed": "string",
                  "event_type": "string", "facility_type": "string", "event_ts": "timestamp"},
    "payer_gap_file": {"payer_gap_id": "string", "member_id": "string", "payer_code": "string",
                       "measure_code": "string", "gap_status": "string", "report_month": "date"},
    "care_gap": {"care_gap_id": "string", "member_id": "string", "practice_id": "string", "payer_code": "string",
                 "measure_code": "string", "status": "string", "opened_date": "date", "closed_date": "date",
                 "source": "string"},
    "member_risk_score": {"member_id": "string", "score_month": "date", "risk_tier": "int", "risk_score": "double",
                          "predicted_unplanned_admit_flag": "boolean", "model_version": "string"},
    "chw_encounter": {"encounter_id": "string", "member_id": "string", "chw_id": "string",
                      "encounter_date": "date", "encounter_type": "string", "outcome": "string"},
    "sdoh_screening": {"screening_id": "string", "member_id": "string", "screening_date": "date",
                       "z_code": "string", "need_category": "string", "referral_made": "boolean",
                       "screening_tool": "string"},
    "health_at_home_episode": {"episode_id": "string", "member_id": "string", "state": "string",
                               "start_date": "date", "end_date": "date", "status": "string",
                               "risk_tier_at_referral": "int", "ed_visits_pre_90d": "int",
                               "ed_visits_post_90d": "int"},
    "practice_incentive_payment": {"payment_id": "string", "practice_id": "string", "payer_code": "string",
                                   "payment_month": "date", "measure_bundle": "string", "amount": "double"},
    "shared_savings_settlement": {"settlement_id": "string", "practice_id": "string", "payer_code": "string",
                                  "performance_year": "int", "benchmark_pmpm": "double", "actual_pmpm": "double",
                                  "member_months": "int", "gross_savings": "double", "quality_gate_met": "boolean",
                                  "practice_share_amount": "double"},
}
LAB_TYPE_CHANGE_DAY = 20  # D05: result_value arrives as text from this day

ARROW = {"string": pa.string(), "date": pa.date32(), "double": pa.float64(), "int": pa.int64(),
         "boolean": pa.bool_(), "timestamp": pa.timestamp("us")}


def silver_types(entity: str, day: int) -> dict[str, str]:
    t = dict(SILVER_TYPES[entity])
    if entity == "lab_result" and day >= LAB_TYPE_CHANGE_DAY:
        t["result_value"] = "string"
    return t


def write_silver(frames: dict[str, pd.DataFrame], day: int, root: Path = BUILD) -> list[Path]:
    out = []
    ingest_date = R.day_date(day)
    for entity in SILVER_TYPES:
        df = frames[entity]
        part = df[df["ingest_day"] == day]
        if part.empty:
            continue
        types = silver_types(entity, day)
        cols = {}
        for c, t in types.items():
            v = part[c]
            if t == "date":
                v = pd.to_datetime(v).dt.date
            elif t == "timestamp":
                v = pd.to_datetime(v)
            elif t == "int":
                v = v.astype("int64")
            elif t == "string":
                v = v.astype(object).where(v.notna(), None).map(lambda x: None if x is None else str(x))
            cols[c] = pa.array(v.tolist() if t != "timestamp" else v, type=ARROW[t], from_pandas=True)
        # In-file copy of the partition date. Named load_date (not ingest_date) so Spark/Glue don't see a duplicate
        # of the partition column; Redshift COPY maps Parquet columns by position into core.<entity>.ingest_date.
        cols["load_date"] = pa.array([ingest_date] * len(part), type=pa.date32())
        path = root / "silver" / entity / f"ingest_date={ingest_date}" / "part-0000.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table(cols), path, compression="snappy")
        out.append(path)
    return out


# ------------------------------------------------------------------ raw feeds (quirky per payer)
ABBREV = {"member": "MBR", "claim": "CLM", "date": "DT", "code": "CD", "number": "NBR", "payer": "PYR",
          "service": "SVC", "amount": "AMT", "paid": "PD", "provider": "PROV", "assignment": "ASGN",
          "status": "STAT", "measure": "MEAS", "category": "CAT", "allowed": "ALWD", "practice": "PRAC",
          "subscriber": "SBSCR", "coverage": "COV", "effective": "EFF"}


def style(name: str, naming: str) -> str:
    parts = name.split("_")
    if naming == "snake":
        return name
    if naming == "upper_abbrev":
        return "_".join(ABBREV.get(p, p.upper()) for p in parts)
    if naming == "camel":
        return parts[0] + "".join(p.title() for p in parts[1:])
    if naming == "legacy":
        return "fld_" + "".join(ABBREV.get(p, p[:4]).lower() for p in parts)
    raise ValueError(naming)


def glue_name(header: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", header.lower())


def _fmt_dates(df: pd.DataFrame, fmt: str) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if c.endswith("_date") or c.endswith("_dob") or c.endswith("_start") or c.endswith("_end") or c in ("dob", "effective_month",
                                                                                       "report_month"):
            s = pd.to_datetime(df[c], errors="coerce")
            df[c] = s.dt.strftime(fmt).where(s.notna(), "")
    return df


def raw_feed_frames(frames: dict[str, pd.DataFrame], day: int) -> dict[str, tuple[pd.DataFrame, dict]]:
    """Return {raw_table: (frame with canonical column names, quirks)} for one ingest day."""
    payers = R.load_yaml("datagen/payers.yaml")
    f = {k: v[v["ingest_day"] == day] for k, v in frames.items()}
    out: dict[str, tuple[pd.DataFrame, dict]] = {}
    mem_all = frames["member"].set_index("member_id")
    pcp = frames["pcp_assignment"].drop_duplicates("member_id", keep="last").set_index("member_id")["pcp_npi"]
    for code, p in payers["payers"].items():
        q = p["quirks"]
        fd = p["feeds"]
        el = f["eligibility_span"][f["eligibility_span"]["payer_code"] == code]
        if not el.empty:
            m = mem_all.reindex(el["member_id"])
            e = pd.DataFrame({
                "subscriber_id": m["payer_member_id"].to_numpy(), "member_dob": m["dob"].to_numpy(),
                "member_sex": m["sex"].to_numpy(), "member_zip": m["zip"].to_numpy(), "lob": el["lob"].to_numpy(),
                "coverage_start_date": el["start_date"].to_numpy(), "coverage_end_date": el["end_date"].to_numpy(),
                "maintenance_type_code": np.where(el["end_date"].isna(), "021", "024"),
                "pcp_assignment_npi": pcp.reindex(el["member_id"]).to_numpy()})
            if code == "PAYER_AZ1" and day >= 20:  # D04: column dropped by the payer
                e = e.drop(columns=["pcp_assignment_npi"])
            out[fd["eligibility"]["table"]] = (e, q)
        ch = f["claim_header"][f["claim_header"]["payer_code"] == code]
        if not ch.empty:
            ln = frames["claim_line"]
            ln = ln[(ln["ingest_day"] == day) & (ln["payer_code"] == code)]
            flat = ln.merge(ch.drop(columns=["payer_code", "ingest_day", "service_date"]).drop_duplicates("claim_id"),
                            on="claim_id", how="inner")
            flat["subscriber_id"] = mem_all["payer_member_id"].reindex(flat["member_id"]).to_numpy()
            flat = flat[["claim_id", "line_no", "subscriber_id", "claim_type", "service_date", "received_date",
                         "billing_npi", "cpt_code", "dx_code_1", "dx_code_2", "units", "paid_amount", "total_paid"]]
            out[fd["claims"]["table"]] = (flat, q)
        ro = f["pcp_assignment"][f["pcp_assignment"]["payer_code"] == code]
        if not ro.empty:
            out[fd["roster"]["table"]] = (ro[["member_id", "pcp_npi", "effective_month"]].rename(
                columns={"member_id": "member_number"}), q)
        gp = f["payer_gap_file"][f["payer_gap_file"]["payer_code"] == code]
        if not gp.empty:
            out[fd["gaps"]["table"]] = (gp[["payer_gap_id", "member_id", "measure_code", "gap_status", "report_month"]], q)
        rx = f["rx_claim"][f["rx_claim"]["payer_code"] == code]
        if not rx.empty:
            out[fd["pharmacy"]["table"]] = (rx.drop(columns=["payer_code", "ingest_day"]), q)
    hie_q = {"naming": "upper_abbrev", "date_format": "%Y%m%d%H%M", "delimiter": "|"}
    for st, scfg in payers["states"].items():
        a = f["adt_event"][f["adt_event"]["state"] == st]
        if not a.empty:
            out[scfg["hie_feed"]] = (a.drop(columns=["ingest_day", "hie_feed"]).rename(
                columns={"event_ts": "event_date"}), hie_q)
    lab = f["lab_result"]
    if not lab.empty:
        out["raw_ehr_ccda_labs"] = (lab.drop(columns=["ingest_day"]),
                                    {"naming": "camel", "date_format": "%Y-%m-%dT00:00:00", "delimiter": ","})
    ops = pd.concat([
        f["chw_encounter"].assign(record_type="CHW").rename(columns={"encounter_id": "record_id",
                                                                     "encounter_date": "event_date"}),
        f["sdoh_screening"].assign(record_type="SDOH").rename(columns={"screening_id": "record_id",
                                                                       "screening_date": "event_date"}),
    ], ignore_index=True)
    if not ops.empty:
        ops = ops[["record_type", "record_id", "member_id", "event_date", "chw_id", "encounter_type", "outcome",
                   "z_code", "need_category"]]
        out["raw_careempower_ops"] = (ops, {"naming": "snake", "date_format": "%Y-%m-%d", "delimiter": ","})
    return out


def write_raw(frames: dict[str, pd.DataFrame], day: int, root: Path = BUILD) -> dict[str, dict]:
    """Write raw CSVs; return {table: {"columns": [...glue names], "delimiter": d}} for the catalog."""
    ingest_date = R.day_date(day)
    schemas = {}
    for table, (df, q) in raw_feed_frames(frames, day).items():
        df = _fmt_dates(df, q["date_format"])
        headers = [style(c, q["naming"]) for c in df.columns]
        path = root / "raw" / table / f"ingest_date={ingest_date}" / f"{table}_{ingest_date:%Y%m%d}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, sep=q["delimiter"], header=headers, index=False, na_rep="", lineterminator="\n")
        schemas[table] = {"columns": [glue_name(h) for h in headers], "delimiter": q["delimiter"]}
    return schemas


def frame_checksums(frames: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Order-sensitive content checksums, used to prove the generator is deterministic."""
    out = {}
    for k in sorted(frames):
        h = pd.util.hash_pandas_object(frames[k].astype(str), index=False).to_numpy()
        out[k] = hashlib.sha256(h.tobytes()).hexdigest()[:16]
    return out
