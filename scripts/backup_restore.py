#!/usr/bin/env python3
"""Backup / restore of the pilot's state, so the demo can be parked (most stacks destroyed) and brought back exactly.

    python scripts/backup_restore.py backup          # snapshots + S3 + Glue catalog + build/ -> backup bucket
    python scripts/backup_restore.py status          # latest backup and whether its snapshots still exist
    python scripts/backup_restore.py restore-data    # after the stacks are redeployed: Redshift, S3, Glue, build/
    python scripts/backup_restore.py verify          # compare live counts with the latest backup's manifest
    python scripts/backup_restore.py purge-secrets   # force-delete eqh-dq/* secrets left pending deletion

State that is backed up (everything else is rebuilt by CDK or by scripts):
  Aurora metadata store   -> manual cluster snapshot (restored by CDK, see infra/stacks/metadata_store.py)
  Redshift Serverless     -> manual namespace snapshot (restored into the new namespace by restore-data)
  S3 data buckets         -> s3://<backup>/<id>/s3/<kind>/
  Glue eqh_raw/eqh_silver -> tables + partitions as JSON
  build/                  -> simulation state, eval results, generated data (this session's disk is temporary)
Snapshots and the backup bucket are encrypted with the pilot CMK, which stays deployed in EqhDqSecurity.
Only metadata, counts and object listings are written to the manifest; no row values are read or logged.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jobs.common import settings  # noqa: E402

log = logging.getLogger("backup")
DATA_BUCKETS = ("raw", "silver", "extracts", "glossary", "dq-results")
GLUE_DBS = ("eqh_raw", "eqh_silver")
CLUSTER = "eqh-dq-metadata"
NAMESPACE = WORKGROUP = "eqh-dq"
AURORA_TABLES = ("asset", "asset_column", "lineage_edge", "dq_metric", "dq_issue", "embedding", "glossary_term",
                 "review_action", "enrichment_task", "asset_entitlement", "sync_run", "schema_change")
RESTORE_STATE = ROOT / "config" / "restore_state.json"
TABLE_INPUT = {"Name", "Description", "Owner", "LastAccessTime", "LastAnalyzedTime", "Retention",
               "StorageDescriptor", "PartitionKeys", "ViewOriginalText", "ViewExpandedText", "TableType",
               "Parameters", "TargetTable"}
PARTITION_INPUT = {"Values", "LastAccessTime", "StorageDescriptor", "Parameters", "LastAnalyzedTime"}


def s() -> dict:
    return settings.get()


def client(name: str):
    return boto3.client(name, region_name=s()["region"])


def bucket(kind: str) -> str:
    return f"eqh-dq-{s()['account_id']}-{kind}"


def sh(*args: str) -> None:
    subprocess.run(args, check=True)


def put_json(key: str, obj) -> None:
    client("s3").put_object(Bucket=bucket("backup"), Key=key, Body=json.dumps(obj, indent=1, default=str).encode())


def get_json(key: str):
    return json.loads(client("s3").get_object(Bucket=bucket("backup"), Key=key)["Body"].read())


def latest() -> dict:
    return get_json(get_json("LATEST.json")["manifest"])


# ---------------------------------------------------------------- counts (metadata and aggregates only)
def s3_counts() -> dict:
    out, s3 = {}, client("s3")
    for kind in DATA_BUCKETS:
        n = size = 0
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket(kind)):
            for o in page.get("Contents", []):
                n, size = n + 1, size + o["Size"]
        out[kind] = {"objects": n, "bytes": size}
    return out


def glue_counts() -> dict:
    g, out = client("glue"), {}
    for db in GLUE_DBS:
        tables = [t["Name"] for p in g.get_paginator("get_tables").paginate(DatabaseName=db) for t in p["TableList"]]
        parts = sum(len(p["Partitions"]) for t in tables
                    for p in g.get_paginator("get_partitions").paginate(DatabaseName=db, TableName=t))
        out[db] = {"tables": len(tables), "partitions": parts}
    return out


def aurora_counts() -> dict:
    from jobs.common.db import MetaDB
    db = MetaDB(role="admin")
    have = {r["t"] for r in db.query("select table_name as t from information_schema.tables "
                                      "where table_schema = 'public'")}
    return {t: db.one(f"select count(*) from {t}") for t in AURORA_TABLES if t in have}  # names are constants


def redshift_counts() -> dict:
    from jobs.common.redshift import Redshift
    rs = Redshift(secret_arn=s()["redshift_admin_secret_arn"])
    rows = rs.query("""select trim("schema") as sch, trim("table") as tbl, tbl_rows::bigint as n from svv_table_info
                       where "schema" not in ('pg_catalog', 'information_schema', 'pg_internal')""")
    views = rs.query("""select count(*) as n from information_schema.views
                        where table_schema not in ('pg_catalog', 'information_schema')""")
    return {"tables": {f"{r['sch']}.{r['tbl']}": int(r["n"]) for r in rows}, "views": int(views[0]["n"])}


def counts() -> dict:
    return {"s3": s3_counts(), "glue": glue_counts(), "aurora": aurora_counts(), "redshift": redshift_counts()}


# ---------------------------------------------------------------- backup
def backup(args) -> None:
    bid = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    snap = f"eqh-dq-backup-{bid}"
    prefix = f"{bid}/"
    rds, rss = client("rds"), client("redshift-serverless")
    tags = [{"Key": "eqh-dq-backup", "Value": bid}]

    log.info("counting live state")
    c = counts()

    log.info("Aurora snapshot %s", snap)
    rds.create_db_cluster_snapshot(DBClusterIdentifier=CLUSTER, DBClusterSnapshotIdentifier=snap, Tags=tags)
    log.info("Redshift snapshot %s", snap)
    rss.create_snapshot(namespaceName=NAMESPACE, snapshotName=snap, retentionPeriod=-1,
                        tags=[{"key": "eqh-dq-backup", "value": bid}])

    for kind in DATA_BUCKETS:
        log.info("copy s3://%s -> backup", bucket(kind))
        sh("aws", "s3", "sync", f"s3://{bucket(kind)}", f"s3://{bucket('backup')}/{prefix}s3/{kind}", "--quiet")

    g = client("glue")
    for db in GLUE_DBS:
        tables = [t for p in g.get_paginator("get_tables").paginate(DatabaseName=db) for t in p["TableList"]]
        out = []
        for t in tables:
            parts = [p for pg in g.get_paginator("get_partitions").paginate(DatabaseName=db, TableName=t["Name"])
                     for p in pg["Partitions"]]
            out.append({"table": {k: v for k, v in t.items() if k in TABLE_INPUT},
                        "partitions": [{k: v for k, v in p.items() if k in PARTITION_INPUT} for p in parts]})
        put_json(f"{prefix}glue/{db}.json", out)
        log.info("glue %s: %d tables exported", db, len(out))

    build = ROOT / "build"
    if build.exists():
        log.info("copy build/ -> backup")
        sh("aws", "s3", "sync", str(build), f"s3://{bucket('backup')}/{prefix}build", "--quiet",
           "--exclude", "*.log")

    log.info("waiting for snapshots")
    rds.get_waiter("db_cluster_snapshot_available").wait(DBClusterSnapshotIdentifier=snap,
                                                          WaiterConfig={"Delay": 20, "MaxAttempts": 90})
    _wait(lambda: rss.get_snapshot(snapshotName=snap)["snapshot"]["status"], "AVAILABLE", "Redshift snapshot")

    manifest = {"id": bid, "created_at": datetime.now(timezone.utc).isoformat(), "aurora_snapshot": snap,
                "redshift_snapshot": snap, "prefix": prefix, "counts": c,
                "aurora_engine": rds.describe_db_clusters(DBClusterIdentifier=CLUSTER)["DBClusters"][0]["EngineVersion"]}
    put_json(f"{prefix}manifest.json", manifest)
    _check_backup(manifest)
    put_json("LATEST.json", {"manifest": f"{prefix}manifest.json", "id": bid})
    log.info("backup %s complete and verified", bid)
    print(json.dumps({"backup": bid, "aurora_snapshot": snap, "redshift_snapshot": snap}, indent=1))


def _wait(get, want: str, what: str, timeout: int = 3600) -> None:
    t0 = time.time()
    while True:
        st = get()
        if st == want:
            return
        if st in ("FAILED", "DELETED", "failed", "deleted") or time.time() - t0 > timeout:
            raise RuntimeError(f"{what}: {st}")
        time.sleep(20)


def _check_backup(m: dict) -> None:
    """The copied objects in the backup bucket match the live buckets; Glue export complete; snapshots available."""
    s3 = client("s3")
    for kind, want in m["counts"]["s3"].items():
        n = sum(len(p.get("Contents", [])) for p in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket("backup"), Prefix=f"{m['prefix']}s3/{kind}/"))
        if n != want["objects"]:
            raise RuntimeError(f"backup of {kind}: {n} objects, expected {want['objects']}")
    for db, want in m["counts"]["glue"].items():
        exp = get_json(f"{m['prefix']}glue/{db}.json")
        if len(exp) != want["tables"] or sum(len(t["partitions"]) for t in exp) != want["partitions"]:
            raise RuntimeError(f"glue export {db} incomplete")
    st = client("rds").describe_db_cluster_snapshots(DBClusterSnapshotIdentifier=m["aurora_snapshot"])
    assert st["DBClusterSnapshots"][0]["Status"] == "available"
    assert client("redshift-serverless").get_snapshot(snapshotName=m["redshift_snapshot"])["snapshot"]["status"] \
        == "AVAILABLE"


def status(args) -> None:
    m = latest()
    rds, rss = client("rds"), client("redshift-serverless")
    try:
        a = rds.describe_db_cluster_snapshots(DBClusterSnapshotIdentifier=m["aurora_snapshot"])["DBClusterSnapshots"][0]
        a = f"{a['Status']} ({a['AllocatedStorage']} GB)"
    except rds.exceptions.DBClusterSnapshotNotFoundFault:
        a = "MISSING"
    try:
        r = rss.get_snapshot(snapshotName=m["redshift_snapshot"])["snapshot"]
        r = f"{r['status']} ({round(r.get('totalBackupSizeInMegaBytes', 0) / 1024, 2)} GB)"
    except rss.exceptions.ResourceNotFoundException:
        r = "MISSING"
    print(json.dumps({"latest": m["id"], "created_at": m["created_at"], "aurora_snapshot": [m["aurora_snapshot"], a],
                      "redshift_snapshot": [m["redshift_snapshot"], r]}, indent=1))
    if "MISSING" in (a, r):
        sys.exit(1)


# ---------------------------------------------------------------- restore (after `cdk deploy --all`)
def restore_data(args) -> None:
    m = latest()
    rss = client("redshift-serverless")

    log.info("Redshift: restoring %s into namespace %s", m["redshift_snapshot"], NAMESPACE)
    rss.restore_from_snapshot(namespaceName=NAMESPACE, workgroupName=WORKGROUP, snapshotName=m["redshift_snapshot"])
    time.sleep(30)
    _wait(lambda: rss.get_namespace(namespaceName=NAMESPACE)["namespace"]["status"], "AVAILABLE", "namespace")
    _wait(lambda: rss.get_workgroup(workgroupName=WORKGROUP)["workgroup"]["status"], "AVAILABLE", "workgroup")
    # The snapshot carries the old admin password; align it with this deployment's secret (read in-process, never
    # printed), so the Data API keeps working with the secret ARN the jobs use.
    sec = json.loads(client("secretsmanager").get_secret_value(
        SecretId=s()["redshift_admin_secret_arn"])["SecretString"])
    rss.update_namespace(namespaceName=NAMESPACE, adminUsername=sec["username"], adminUserPassword=sec["password"])
    del sec
    _wait(lambda: rss.get_namespace(namespaceName=NAMESPACE)["namespace"]["status"], "AVAILABLE", "namespace")

    for kind in DATA_BUCKETS:
        log.info("copy backup -> s3://%s", bucket(kind))
        sh("aws", "s3", "sync", f"s3://{bucket('backup')}/{m['prefix']}s3/{kind}", f"s3://{bucket(kind)}", "--quiet")

    g = client("glue")
    for db in GLUE_DBS:
        for item in get_json(f"{m['prefix']}glue/{db}.json"):
            t = item["table"]
            try:
                g.create_table(DatabaseName=db, TableInput=t)
            except g.exceptions.AlreadyExistsException:
                g.update_table(DatabaseName=db, TableInput=t)
            parts = item["partitions"]
            for i in range(0, len(parts), 100):
                r = g.batch_create_partition(DatabaseName=db, TableName=t["Name"], PartitionInputList=parts[i:i + 100])
                errs = [e for e in r.get("Errors", []) if e["ErrorDetail"]["ErrorCode"] != "AlreadyExistsException"]
                if errs:
                    raise RuntimeError(f"glue partitions {db}.{t['Name']}: {errs[:2]}")
        log.info("glue %s restored", db)

    from datagen import glue_dq
    glue_dq.ensure_rulesets()

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    sh("aws", "s3", "sync", f"s3://{bucket('backup')}/{m['prefix']}build", str(build), "--quiet",
       "--exclude", "image_tag")
    log.info("data restored from backup %s", m["id"])


def verify(args) -> None:
    m = latest()
    live, want = counts(), m["counts"]
    diffs = []
    for area in ("s3", "glue", "aurora"):
        for k, v in want[area].items():
            if live[area].get(k) != v:
                diffs.append(f"{area}.{k}: backup {v} live {live[area].get(k)}")
    for k, v in want["redshift"]["tables"].items():
        if live["redshift"]["tables"].get(k) != v:
            diffs.append(f"redshift.{k}: backup {v} live {live['redshift']['tables'].get(k)}")
    if live["redshift"]["views"] != want["redshift"]["views"]:
        diffs.append(f"redshift views: backup {want['redshift']['views']} live {live['redshift']['views']}")
    summary = {"backup": m["id"], "s3_objects": sum(v["objects"] for v in live["s3"].values()),
               "glue_partitions": sum(v["partitions"] for v in live["glue"].values()),
               "aurora_rows": sum(live["aurora"].values()), "redshift_tables": len(live["redshift"]["tables"]),
               "redshift_rows": sum(live["redshift"]["tables"].values()), "redshift_views": live["redshift"]["views"],
               "differences": diffs}
    print(json.dumps(summary, indent=1))
    if diffs:
        sys.exit(1)


def purge_secrets(args) -> None:
    """CloudFormation deletes named secrets with a recovery window; a redeploy can't reuse the names until they are
    gone. Force-delete the pilot's own eqh-dq/* secrets that are already pending deletion."""
    sm = client("secretsmanager")
    for p in sm.get_paginator("list_secrets").paginate(IncludePlannedDeletion=True,
                                                       Filters=[{"Key": "name", "Values": ["eqh-dq/"]}]):
        for x in p["SecretList"]:
            if x.get("DeletedDate"):
                sm.restore_secret(SecretId=x["ARN"])
                sm.delete_secret(SecretId=x["ARN"], ForceDeleteWithoutRecovery=True)
                log.info("purged pending-deletion secret %s", x["Name"])


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("botocore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["backup", "status", "restore-data", "verify", "purge-secrets"])
    a = ap.parse_args()
    os.chdir(ROOT)
    {"backup": backup, "status": status, "restore-data": restore_data, "verify": verify,
     "purge-secrets": purge_secrets}[a.cmd](a)


if __name__ == "__main__":
    main()
