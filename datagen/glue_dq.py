"""Glue Data Quality rulesets (DQDL) for the silver layer (SPEC §B5.6) and an evaluation runner.

Rulesets are catalog configuration bound to the datagen-created Glue tables, so they are created here (idempotent)
rather than in CDK; the IAM role they run under is created by DataPlatformStack.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import boto3
from botocore.exceptions import ClientError

from datagen.domain import reference as R
from jobs.common import settings

log = logging.getLogger("glue_dq")
ROLE = "eqh-dq-glue-dq-role"
STATES = '["AZ","TX","LA","TN","VA"]'
ZCODES = "[" + ",".join(f'"{z}"' for z in sorted(R.VALID_Z_CODES)) + "]"
MEASURES = "[" + ",".join(f'"{m}"' for m in R.MEASURES) + "]"

RULESETS: dict[str, tuple[str, dict]] = {
    "member": ('Rules = [ IsComplete "member_id", IsUnique "member_id", ColumnValues "state" in ' + STATES +
               ', IsComplete "payer_code" ]', {}),
    "claim_header": ('Rules = [ IsComplete "claim_id", IsUnique "claim_id", IsComplete "member_id", '
                     'ColumnValues "state" in ' + STATES + ', '
                     'ReferentialIntegrity "member_id" "member.member_id" >= 0.99 ]', {"member": "member"}),
    "claim_line": ('Rules = [ IsComplete "claim_id", Uniqueness "claim_id,line_no" > 0.999, '
                   'Completeness "dx_code_1" > 0.9 ]', {}),
    "eligibility_span": ('Rules = [ IsComplete "member_id", IsComplete "start_date", '
                         'CustomSql "select count(*) from primary where end_date < start_date" = 0 ]', {}),
    "care_gap": ('Rules = [ IsUnique "care_gap_id", ColumnValues "measure_code" in ' + MEASURES + ', '
                 'ReferentialIntegrity "member_id" "eligibility_span.member_id" >= 0.999 ]',
                 {"eligibility_span": "eligibility_span"}),
    "sdoh_screening": ('Rules = [ IsComplete "screening_id", ColumnValues "z_code" in ' + ZCODES + ' with threshold >= 0.99 ]',
                       {}),
    "adt_event": ('Rules = [ IsComplete "adt_id", IsUnique "adt_id", ColumnValues "state" in ' + STATES + ' ]', {}),
}


def ensure_rulesets() -> None:
    glue = boto3.client("glue", region_name=settings.get()["region"])
    for table, (dqdl, _) in RULESETS.items():
        name = f"eqh_silver_{table}"
        args = {"Name": name, "Ruleset": dqdl, "Description": f"Silver DQ rules for {table}"}
        try:
            glue.get_data_quality_ruleset(Name=name)
            glue.update_data_quality_ruleset(**args)
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityNotFoundException":
                raise
            glue.create_data_quality_ruleset(**args, TargetTable={"DatabaseName": "eqh_silver", "TableName": table},
                                             Tags={"project": "eqh-dq-assistant", "env": "pilot", "data": "synthetic"})


def run_all(as_of: date, wait: bool = True) -> list[str]:
    ensure_rulesets()
    s = settings.get()
    glue = boto3.client("glue", region_name=s["region"])
    role = f"arn:aws:iam::{s['account_id']}:role/{ROLE}"
    runs = []
    for table, (_, extra) in RULESETS.items():
        args = {"DataSource": {"GlueTable": {"DatabaseName": "eqh_silver", "TableName": table}}, "Role": role,
                "RulesetNames": [f"eqh_silver_{table}"], "NumberOfWorkers": 2, "Timeout": 30}
        if extra:
            args["AdditionalDataSources"] = {alias: {"GlueTable": {"DatabaseName": "eqh_silver", "TableName": t}}
                                             for alias, t in extra.items()}
        runs.append(glue.start_data_quality_ruleset_evaluation_run(**args)["RunId"])
    log.info("started %d Glue DQ runs for %s", len(runs), as_of)
    if wait:
        pending = set(runs)
        while pending:
            time.sleep(20)
            for r in list(pending):
                st = glue.get_data_quality_ruleset_evaluation_run(RunId=r)["Status"]
                if st in ("SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT"):
                    pending.discard(r)
                    if st != "SUCCEEDED":
                        log.warning("Glue DQ run %s ended %s", r, st)
    return runs
