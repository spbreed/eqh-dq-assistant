"""21-day history simulation (SPEC §B5.5).

    python -m datagen.simulate build            # generate + inject defects + write all day files locally
    python -m datagen.simulate seed             # day 0: upload, catalog, Redshift DDL + COPY, marts, glossary
    python -m datagen.simulate days 1 21        # replay days 1..21 (each runs the full daily chain)
    python -m datagen.simulate day 22 --inject D07   # live demo day

Per day, in order: load (S3 + Glue partitions) -> COPY -> refresh MVs -> usage simulator -> Glue DQ (last day)
-> profiler -> daily_sync --as-of <simulated date>.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3
import yaml

from datagen import catalog, defects, load, usage_simulator, writer
from datagen.domain import reference as R
from datagen.domain.entities import Gen
from jobs.common import settings

log = logging.getLogger("simulate")
STATE = R.ROOT / "build" / "sim_state.json"


def build(seed: int | None = None) -> dict[str, str]:
    seed = seed or R.sim_cfg()["seed"]
    frames = defects.inject(Gen(seed).all(), seed)
    if writer.BUILD.exists():
        shutil.rmtree(writer.BUILD)
    schemas = {}
    for day in range(0, R.sim_cfg()["days"] + 1):
        writer.write_silver(frames, day)
        schemas[day] = writer.write_raw(frames, day)
    (R.ROOT / "build").mkdir(exist_ok=True)
    (R.ROOT / "build" / "raw_schemas.json").write_text(json.dumps(schemas))
    sums = writer.frame_checksums(frames)
    (R.ROOT / "build" / "checksums.json").write_text(json.dumps(sums, indent=1))
    log.info("built %d days; checksums %s", len(schemas), sums)
    return sums


def _upload_day(day: int) -> list[str]:
    s3 = boto3.client("s3", region_name=settings.get()["region"])
    d = f"ingest_date={R.day_date(day).isoformat()}"
    files = [p for p in writer.BUILD.rglob("*") if p.is_file() and d in p.parts]
    s = settings.get()

    def put(p: Path):
        rel = p.relative_to(writer.BUILD)
        layer, key = rel.parts[0], "/".join(rel.parts[1:])
        s3.upload_file(str(p), s[f"bucket_{layer}"], key)

    with ThreadPoolExecutor(16) as ex:
        list(ex.map(put, files))
    return sorted({p.relative_to(writer.BUILD).parts[1] for p in files if p.relative_to(writer.BUILD).parts[0] == "silver"})


def publish_static() -> None:
    """Glossary markdown + outbound extract inventory (inputs harvested by daily_sync)."""
    s, s3 = settings.get(), boto3.client("s3", region_name=settings.get()["region"])
    for t in yaml.safe_load((R.ROOT / "datagen" / "glossary.yaml").read_text())["terms"]:
        slug = str(t["term"]).lower().replace(" ", "_").replace(",", "").replace("/", "_")
        md = (f"# {t['term']}\n\n**Synonyms:** {', '.join(map(str, t.get('synonyms', [])))}\n\n{t['definition']}\n\n"
              f"**Related:** {', '.join(map(str, t.get('related', [])))}\n")
        s3.put_object(Bucket=s["bucket_glossary"], Key=f"terms/{slug}.md", Body=md.encode(),
                      ContentType="text/markdown")
    inventory = [
        {"name": "payer_supplemental_quality_file", "target": "PAYER_AZ1 SFTP", "schedule": "monthly, 5th 02:00",
         "sources": ["redshift://eqh/outbound/payer_supplemental_quality_file"], "owner": "quality-ops"},
        {"name": "practice_gap_list", "target": "practice portal", "schedule": "daily 05:00",
         "sources": ["redshift://eqh/outbound/practice_gap_list"], "owner": "practice-ops"},
        {"name": "practice_incentive_statement", "target": "practice portal", "schedule": "monthly, 10th",
         "sources": ["redshift://eqh/outbound/practice_incentive_statement"], "owner": "finance"},
        {"name": "careempower_panel_feed", "target": "CareEmpower", "schedule": "daily 05:30",
         "sources": ["redshift://eqh/outbound/careempower_panel_feed"], "owner": "careempower-eng"},
        {"name": "payer_hah_report", "target": "PAYER_TN1 SFTP", "schedule": "quarterly",
         "sources": ["redshift://eqh/outbound/payer_hah_report"], "owner": "care-model"},
    ]
    s3.put_object(Bucket=s["bucket_extracts"], Key="inventory.json", Body=json.dumps(inventory, indent=1).encode())


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {"days_done": []}


def _save(st: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st))


def load_day(day: int) -> None:
    schemas = json.loads((R.ROOT / "build" / "raw_schemas.json").read_text())[str(day)]
    silver_entities = _upload_day(day)
    catalog.register_day(schemas, silver_entities, day)
    if day == 0:
        load.bootstrap()
    load.copy_day(day)
    if day == 0:
        load.create_marts()
        publish_static()
    load.refresh_mvs()


def daily_chain(day: int) -> None:
    """Everything after the load for one simulated day."""
    from jobs.daily_sync import sync
    from jobs.profiler import profile
    as_of = R.day_date(day)
    st = _state()
    if day == 0 and not st.get("usage_history"):
        usage_simulator.run_history(30)
        st["usage_history"] = True
        _save(st)
    usage_simulator.run_day(day)
    if os.environ.get("RUN_GLUE_DQ") == "1" or day == R.sim_cfg()["days"]:
        from datagen import glue_dq
        glue_dq.run_all(as_of)
    profile.run(as_of)
    sync.run(as_of=as_of)


def run_day(day: int, chain: bool = True) -> None:
    st = _state()
    log.info("==== simulated day %d (%s)", day, R.day_date(day))
    load_day(day)
    if chain:
        daily_chain(day)
    st["days_done"] = sorted(set(st["days_done"]) | {day})
    _save(st)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "seed", "days", "day", "chain"])
    ap.add_argument("start", nargs="?", type=int)
    ap.add_argument("end", nargs="?", type=int)
    ap.add_argument("--inject", default="")
    ap.add_argument("--no-chain", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "seed":
        run_day(0, chain=not a.no_chain)
    elif a.cmd == "days":
        for d in range(a.start, (a.end or a.start) + 1):
            run_day(d, chain=not a.no_chain)
    elif a.cmd == "chain":
        daily_chain(a.start)
    elif a.cmd == "day":
        from datagen import live_day
        live_day.run(a.start, a.inject.split(",") if a.inject else [])


if __name__ == "__main__":
    main()
