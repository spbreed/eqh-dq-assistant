"""Inject the planted defects from datagen/seeded_defects.yaml into the generated frames (data-level defects).

Structural defects (D04 column removed, D05 type change) are applied by the raw-feed writer / simulator on their
day; documentation and lineage defects (D09–D12) live in sql/redshift DDL.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from datagen.domain import reference as R


def manifest() -> dict[str, dict]:
    return {d["id"]: d for d in R.load_yaml("datagen/seeded_defects.yaml")["defects"]}


def inject(frames: dict[str, pd.DataFrame], seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed + 1)
    m = manifest()
    f = frames

    # D01: PAYER_TX2 dx_code_1 null rate 3% -> 30% from day 18
    d = m["D01"]
    cl = f["claim_line"]
    sel = (cl["payer_code"] == "PAYER_TX2") & (cl["ingest_day"] >= d["inject_on_day"])
    extra = sel & (rng.random(len(cl)) < (d["params"]["defect_null_rate"] - 0.03) / 0.97)
    cl.loc[extra, "dx_code_1"] = None

    # D02: PAYER_AZ2 resends a file on day 19 -> ~4% of AZ2 claim headers duplicated
    d = m["D02"]
    ch = f["claim_header"]
    az2 = ch[(ch["payer_code"] == "PAYER_AZ2") & (ch["ingest_day"] < d["inject_on_day"])]
    dup = az2.sample(frac=d["params"]["dup_fraction"], random_state=int(rng.integers(1e9))).copy()
    dup["ingest_day"] = d["inject_on_day"]
    dup["received_date"] = R.day_date(d["inject_on_day"])

    # D06: from day 17, ~2% of newly received claims reference members not in core.member (retro-terms)
    d = m["D06"]
    new = ch["ingest_day"] >= d["inject_on_day"]
    orphan = new & (rng.random(len(ch)) < d["params"]["orphan_fraction"])
    ch.loc[orphan, "member_id"] = [f"M9{rng.integers(10**6, 10**7)}" for _ in range(int(orphan.sum()))]

    # D07: PAYER_LA1 claims on day 21 drop ~70%
    d = m["D07"]
    la = (ch["payer_code"] == "PAYER_LA1") & (ch["ingest_day"] == d["inject_on_day"])
    drop = la & (rng.random(len(ch)) > d["params"]["volume_factor"])
    dropped_ids = set(ch.loc[drop, "claim_id"])
    ch = ch[~drop]
    f["claim_line"] = cl[~cl["claim_id"].isin(dropped_ids)]
    f["claim_header"] = pd.concat([ch, dup], ignore_index=True)

    # D03: Tennessee HIE ADT stops after day 15
    d = m["D03"]
    adt = f["adt_event"]
    f["adt_event"] = adt[~((adt["state"] == "TN") & (adt["ingest_day"] > d["params"]["last_good_day"]))]

    # D08: day-10 redetermination batch creates overlapping spans for ~2% of members
    d = m["D08"]
    el = f["eligibility_span"]
    open_spans = el[el["end_date"].isna() & (el["ingest_day"] < d["inject_on_day"])]
    ov = open_spans.sample(frac=d["params"]["overlap_fraction"], random_state=int(rng.integers(1e9))).copy()
    ov["start_date"] = ov["start_date"].map(lambda s: s + timedelta(days=int(rng.integers(10, 40))))
    ov["term_reason"] = None
    ov["ingest_day"] = d["inject_on_day"]
    ov["span_id"] = [f"ES9{i:06d}" for i in range(len(ov))]

    # D13: day-16 retro-terminations: ~3% of members with open care gaps lose eligibility (gaps stay open)
    d = m["D13"]
    cg = f["care_gap"]
    with_gaps = cg.loc[(cg["status"] == "open") & (cg["ingest_day"] < d["inject_on_day"]), "member_id"].unique()
    k = int(len(with_gaps) * d["params"]["retro_term_fraction"])
    termed = set(rng.choice(with_gaps, k, replace=False))
    term = el[el["member_id"].isin(termed) & el["end_date"].isna()].copy()
    term["end_date"] = R.day_date(d["inject_on_day"] - 1)
    term["term_reason"] = "retro_termination"
    term["ingest_day"] = d["inject_on_day"]  # same span_id: loaded with MERGE (upsert)
    f["eligibility_span"] = pd.concat([el, ov, term], ignore_index=True)

    # D14: from day 18, ~5% of new SDoH screenings carry invalid Z-codes
    d = m["D14"]
    sd = f["sdoh_screening"]
    bad = (sd["ingest_day"] >= d["inject_on_day"]) & (rng.random(len(sd)) < d["params"]["invalid_fraction"])
    sd.loc[bad, "z_code"] = rng.choice(R.INVALID_Z_CODES, int(bad.sum()))
    sd.loc[bad, "need_category"] = None

    # D05 (data side): from day 20 lab results arrive as text, some censored like '>14.0'
    d = m["D05"]
    lab = f["lab_result"].copy()
    lab["result_value"] = lab["result_value"].astype(object)
    late = lab["ingest_day"] >= d["inject_on_day"]
    txt = lab.loc[late, "result_value"].map(lambda v: f"{v:.1f}")
    cens = late & (lab["loinc_code"] == "4548-4") & (rng.random(len(lab)) < 0.12)
    lab.loc[late, "result_value"] = txt
    lab.loc[cens, "result_value"] = ">14.0"
    f["lab_result"] = lab
    return f
