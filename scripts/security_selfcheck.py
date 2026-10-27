#!/usr/bin/env python3
"""Security self-check (SPEC Phase 7). Exit 1 on any FAIL.

  no public S3 · encryption on · no wildcard IAM · Aurora and Redshift private · CloudTrail + Bedrock invocation
  logging on · budget alarm active · no IAM-user access keys older than 30 days.
--leftovers: list resources still tagged project=eqh-dq-assistant (after make destroy).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jobs.common import settings  # noqa: E402

S = settings.get()
REGION, ACCT = S["region"], S["account_id"]
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
    results.append(("PASS" if ok else ("WARN" if warn else "FAIL"), name, detail))


def s3_checks() -> None:
    s3 = boto3.client("s3", region_name=REGION)
    for b in [x["Name"] for x in s3.list_buckets()["Buckets"] if x["Name"].startswith("eqh-dq-") or
              x["Name"].startswith("eqhdqsecurity")]:
        try:
            pab = s3.get_public_access_block(Bucket=b)["PublicAccessBlockConfiguration"]
            check(f"s3 {b} public access blocked", all(pab.values()), json.dumps(pab))
        except Exception as e:  # noqa: BLE001
            check(f"s3 {b} public access blocked", False, str(e)[:80])
        try:
            rules = s3.get_bucket_encryption(Bucket=b)["ServerSideEncryptionConfiguration"]["Rules"]
            algo = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
            check(f"s3 {b} encrypted", True, algo)
        except Exception as e:  # noqa: BLE001
            check(f"s3 {b} encrypted", False, str(e)[:80])


def _statements(doc) -> list[dict]:
    if isinstance(doc, str):
        doc = json.loads(unquote(doc))
    st = doc.get("Statement", [])
    return st if isinstance(st, list) else [st]


def iam_checks() -> None:
    iam = boto3.client("iam")
    roles = [r for p in iam.get_paginator("list_roles").paginate() for r in p["Roles"]
             if r["RoleName"].startswith(("eqh-dq", "EqhDq"))]
    bad = []
    for r in roles:
        docs = [iam.get_role_policy(RoleName=r["RoleName"], PolicyName=n)["PolicyDocument"]
                for n in iam.list_role_policies(RoleName=r["RoleName"])["PolicyNames"]]
        for ap in iam.list_attached_role_policies(RoleName=r["RoleName"])["AttachedPolicies"]:
            if ap["PolicyArn"].startswith("arn:aws:iam::aws:"):
                continue
            pol = iam.get_policy(PolicyArn=ap["PolicyArn"])["Policy"]
            docs.append(iam.get_policy_version(PolicyArn=ap["PolicyArn"],
                                               VersionId=pol["DefaultVersionId"])["PolicyVersion"]["Document"])
        for d in docs:
            for st in _statements(d):
                if st.get("Effect") != "Allow":
                    continue
                acts = st.get("Action", [])
                acts = [acts] if isinstance(acts, str) else acts
                res = st.get("Resource", [])
                res = [res] if isinstance(res, str) else res
                if "*" in acts or any(a.endswith(":*") for a in acts) and "*" in res:
                    bad.append(f"{r['RoleName']}: {acts[:3]} on {res[:2]}")
    check("iam no wildcard actions on pilot roles", not bad, "; ".join(bad[:5]) or f"{len(roles)} roles checked")
    old = []
    now = datetime.now(timezone.utc)
    for u in [u for p in iam.get_paginator("list_users").paginate() for u in p["Users"]]:
        for k in iam.list_access_keys(UserName=u["UserName"])["AccessKeyMetadata"]:
            age = (now - k["CreateDate"]).days
            if k["Status"] == "Active" and age > 30:
                old.append(f"{u['UserName']} ({age}d)")
    check("no IAM-user access keys older than 30 days", not old, ", ".join(old) or "none")


def data_checks() -> None:
    rds = boto3.client("rds", region_name=REGION, endpoint_url=f"https://rds.{REGION}.amazonaws.com")
    for c in rds.describe_db_clusters(DBClusterIdentifier="eqh-dq-metadata")["DBClusters"]:
        check("aurora storage encrypted", c["StorageEncrypted"], c.get("KmsKeyId", "")[-12:])
        insts = rds.describe_db_instances(Filters=[{"Name": "db-cluster-id", "Values": [c["DBClusterIdentifier"]]}])
        check("aurora instances private", not any(i["PubliclyAccessible"] for i in insts["DBInstances"]))
    rs = boto3.client("redshift-serverless", region_name=REGION)
    wg = rs.get_workgroup(workgroupName="eqh-dq")["workgroup"]
    check("redshift workgroup private", not wg["publiclyAccessible"])
    ns = rs.get_namespace(namespaceName="eqh-dq")["namespace"]
    check("redshift namespace KMS-encrypted", ns.get("kmsKeyId", "AWS_OWNED") != "AWS_OWNED_KMS_KEY", ns.get("kmsKeyId", "")[-12:])
    limits = rs.list_usage_limits(resourceArn=wg["workgroupArn"]).get("usageLimits", [])
    check("redshift RPU usage limit set", bool(limits), json.dumps([(u["amount"], u["breachAction"]) for u in limits]))


def logging_checks() -> None:
    ct = boto3.client("cloudtrail", region_name=REGION)
    st = ct.get_trail_status(Name="eqh-dq-assistant")
    check("cloudtrail logging", st["IsLogging"])
    br = boto3.client("bedrock", region_name=REGION).get_model_invocation_logging_configuration()
    cfg = br.get("loggingConfig") or {}
    check("bedrock model invocation logging", bool(cfg.get("cloudWatchConfig") or cfg.get("s3Config")),
          (cfg.get("cloudWatchConfig") or {}).get("logGroupName", ""))
    b = boto3.client("budgets", region_name=REGION)
    try:
        bud = b.describe_budget(AccountId=ACCT, BudgetName="eqh-dq-assistant-monthly")["Budget"]
        notes = b.describe_notifications_for_budget(AccountId=ACCT, BudgetName="eqh-dq-assistant-monthly")
        acts = b.describe_budget_actions_for_budget(AccountId=ACCT, BudgetName="eqh-dq-assistant-monthly")
        check("budget + alerts + deny action", len(notes["Notifications"]) >= 3 and bool(acts["Actions"]),
              f"${bud['BudgetLimit']['Amount']} {len(notes['Notifications'])} alerts, action "
              f"{acts['Actions'][0]['Status'] if acts['Actions'] else 'none'}")
    except Exception as e:  # noqa: BLE001
        check("budget + alerts + deny action", False, str(e)[:100])


def leftovers() -> int:
    tag = boto3.client("resourcegroupstaggingapi", region_name=REGION)
    left = []
    for p in tag.get_paginator("get_resources").paginate(TagFilters=[{"Key": "project",
                                                                      "Values": ["eqh-dq-assistant"]}]):
        for r in p["ResourceTagMappingList"]:
            tags = {t["Key"]: t["Value"] for t in r["Tags"]}
            if tags.get("aws:cloudformation:stack-name") == "CDKToolkit":
                continue  # CDK bootstrap, shared tooling; remove separately if the account is closed
            left.append(r["ResourceARN"])
    print("\n".join(left) if left else "no resources tagged project=eqh-dq-assistant remain")
    return 1 if left else 0


def main() -> int:
    if "--leftovers" in sys.argv:
        return leftovers()
    for fn in (s3_checks, iam_checks, data_checks, logging_checks):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            check(fn.__name__, False, f"error: {str(e)[:120]}")
    for status, name, detail in results:
        print(f"{status:5} {name}" + (f"  — {detail}" if detail else ""))
    return 1 if any(r[0] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
