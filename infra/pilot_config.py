"""Loads config/pilot.yaml (non-secret) for the CDK app and the jobs."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load() -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "pilot.yaml").read_text())
    cfg["region"] = os.environ.get("AWS_REGION", cfg["region"])
    cfg["owner"] = os.environ.get("EQH_PILOT_OWNER", cfg["owner"])
    return cfg


def bucket_name(cfg: dict, kind: str) -> str:
    """Deterministic bucket names so CloudTrail selectors and jobs don't need cross-stack lookups."""
    return f"eqh-dq-{cfg['account_id']}-{kind}"


# Workload role names are fixed so the budget action and later stacks can reference them by name.
HARVEST_ROLE = "eqh-dq-harvest-task-role"
ASSISTANT_ROLE = "eqh-dq-assistant-task-role"
REDSHIFT_ROLE = "eqh-dq-redshift-role"
EVAL_ROLE = "eqh-dq-eval-task-role"
