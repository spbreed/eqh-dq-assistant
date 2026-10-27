"""Runtime settings: config/pilot.yaml + env vars, falling back to CloudFormation stack outputs.

In Fargate every value arrives as an env var set by CDK. Locally (laptop / cloud session) the ARNs are looked
up once from the deployed stacks' outputs. No secret values are ever read here — only ARNs and names.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import boto3
import yaml

ROOT = Path(__file__).resolve().parents[2]

ENV_KEYS = {
    "aurora_cluster_arn": ("AURORA_CLUSTER_ARN", "EqhDqMetadataStore", "ClusterArn"),
    "aurora_admin_secret_arn": ("AURORA_ADMIN_SECRET_ARN", "EqhDqMetadataStore", "SecretArn"),
    "aurora_harvest_secret_arn": ("AURORA_SECRET_ARN", "EqhDqMetadataStore", "SecretArnHarvest"),
    "aurora_assistant_secret_arn": ("AURORA_ASSISTANT_SECRET_ARN", "EqhDqMetadataStore", "SecretArnAssistant"),
    "redshift_admin_secret_arn": ("RS_ADMIN_SECRET_ARN", "EqhDqDataPlatform", "RedshiftAdminSecretArn"),
}


@functools.lru_cache(maxsize=1)
def config() -> dict:
    return yaml.safe_load((ROOT / "config" / "pilot.yaml").read_text())


@functools.lru_cache(maxsize=8)
def _stack_outputs(stack: str) -> dict:
    cf = boto3.client("cloudformation", region_name=os.environ.get("AWS_REGION", config()["region"]))
    try:
        outs = cf.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    except Exception:
        return {}
    return {o["OutputKey"]: o["OutputValue"] for o in outs}


class _Settings(dict):
    def __missing__(self, key):
        if key in ENV_KEYS:
            env, stack, out = ENV_KEYS[key]
            val = os.environ.get(env) or _stack_outputs(stack).get(out)
            if not val:
                raise KeyError(f"{key}: set ${env} or deploy {stack}")
            self[key] = val
            return val
        raise KeyError(key)


@functools.lru_cache(maxsize=1)
def get() -> _Settings:
    c = config()
    acct = c["account_id"]
    s = _Settings(
        region=os.environ.get("AWS_REGION", c["region"]),
        account_id=acct,
        redshift_database=c["redshift"]["database"],
        redshift_workgroup="eqh-dq",
        aurora_database="eqh_meta",
        bucket_raw=f"eqh-dq-{acct}-raw", bucket_silver=f"eqh-dq-{acct}-silver",
        bucket_extracts=f"eqh-dq-{acct}-extracts", bucket_glossary=f"eqh-dq-{acct}-glossary",
        bucket_dq=f"eqh-dq-{acct}-dq-results",
        redshift_role_arn=f"arn:aws:iam::{acct}:role/eqh-dq-redshift-role",
        models=c["models"],
        embed_model=os.environ.get("EMBED_MODEL_ID", c["models"]["embed"]),
        embed_dim=int(os.environ.get("EMBED_DIM", c["models"]["embed_dim"])),
    )
    return s
