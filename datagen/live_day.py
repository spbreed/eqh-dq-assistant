"""Replay one extra simulated day live for the demo: `make simulate-day N INJECT=D07[,D01,...]`.

Day N's feeds are derived from the day-20 increment (same members, new record ids, dates shifted), so ongoing
conditions (e.g. TN ADT outage) persist; the requested defects are injected on top. Then the normal daily chain runs:
upload -> Glue partitions -> COPY -> MV refresh -> usage -> profiler -> daily_sync.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from datagen import defects, simulate, writer
from datagen.domain import reference as R
from datagen.domain.entities import Gen

log = logging.getLogger("live_day")
TEMPLATE_DAY = 20
ID_COLS = {"claim_header": "claim_id", "rx_claim": "rx_claim_id", "lab_result": "lab_id", "adt_event": "adt_id",
           "care_gap": "care_gap_id", "chw_encounter": "encounter_id", "sdoh_screening": "screening_id"}
DATE_COLS = ("service_date", "received_date", "fill_date", "result_date", "opened_date", "encounter_date",
             "screening_date")
SUPPORTED = {"D01", "D02", "D03", "D06", "D07", "D14"}


def derive(frames: dict[str, pd.DataFrame], day: int, inject: list[str], seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed + day)
    shift = timedelta(days=day - TEMPLATE_DAY)
    out = {k: v.iloc[0:0].copy() for k, v in frames.items()}
    claim_map = {}
    for ent, idc in ID_COLS.items():
        d = frames[ent][frames[ent]["ingest_day"] == TEMPLATE_DAY].copy()
        prefix = idc[0].upper() if ent != "rx_claim" else "RX"
        new_ids = [f"{prefix}{day}{i:06d}" for i in range(len(d))]
        if ent == "claim_header":
            d = d.drop_duplicates("claim_id")
            new_ids = new_ids[:len(d)]
            claim_map = dict(zip(d["claim_id"], new_ids))
        d[idc] = new_ids
        for c in DATE_COLS:
            if c in d:
                d[c] = pd.to_datetime(d[c]).map(lambda x: (x + shift).date())
        if "event_ts" in d:
            d["event_ts"] = pd.to_datetime(d["event_ts"]) + shift
        d["ingest_day"] = day
        out[ent] = d
    cl = frames["claim_line"]
    cl = cl[cl["claim_id"].isin(claim_map)].copy()
    cl["claim_id"] = cl["claim_id"].map(claim_map)
    cl["service_date"] = pd.to_datetime(cl["service_date"]).map(lambda x: (x + shift).date())
    cl["ingest_day"] = day
    out["claim_line"] = cl

    ch = out["claim_header"]
    if "D07" in inject:
        drop = (ch["payer_code"] == "PAYER_LA1") & (rng.random(len(ch)) > 0.30)
        out["claim_line"] = out["claim_line"][~out["claim_line"]["claim_id"].isin(set(ch.loc[drop, "claim_id"]))]
        ch = ch[~drop]
    if "D02" in inject:
        az2 = frames["claim_header"][frames["claim_header"]["payer_code"] == "PAYER_AZ2"]
        ch = pd.concat([ch, az2.sample(frac=0.02, random_state=day).assign(ingest_day=day)], ignore_index=True)
    out["claim_header"] = ch
    if "D01" in inject:
        l = out["claim_line"]
        l.loc[(l["payer_code"] == "PAYER_TX2") & (rng.random(len(l)) < 0.3), "dx_code_1"] = None
    if "D03" in inject:
        out["adt_event"] = out["adt_event"][out["adt_event"]["state"] != "TN"]
    if "D14" in inject:
        sd = out["sdoh_screening"]
        bad = rng.random(len(sd)) < 0.05
        sd.loc[bad, "z_code"] = rng.choice(R.INVALID_Z_CODES, int(bad.sum()))
    return out


def run(day: int, inject: list[str]) -> None:
    unknown = set(inject) - SUPPORTED
    if unknown:
        raise SystemExit(f"unsupported live injections {unknown}; supported: {sorted(SUPPORTED)}")
    seed = R.sim_cfg()["seed"]
    frames = defects.inject(Gen(seed).all(), seed)
    live = derive(frames, day, inject, seed)
    for ent, df in frames.items():  # keep reference data available to the raw writer (member lookups)
        if ent not in live or live[ent].empty:
            live[ent] = df.iloc[0:0]
    lookups = {**live, "member": frames["member"].assign(ingest_day=-1),
               "pcp_assignment": frames["pcp_assignment"].assign(ingest_day=-1)}
    writer.write_silver(live, day)
    schemas = json.loads((R.ROOT / "build" / "raw_schemas.json").read_text())
    schemas[str(day)] = writer.write_raw(lookups, day)
    (R.ROOT / "build" / "raw_schemas.json").write_text(json.dumps(schemas))
    log.info("day %d (%s) derived from day %d with %s", day, R.day_date(day), TEMPLATE_DAY, inject or "no injections")
    simulate.run_day(day)
