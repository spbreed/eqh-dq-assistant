"""PHI guard (SPEC §B2 rule 7): metadata store, prompts and logs hold metadata and aggregates only.

Synthetic row identifiers have recognisable shapes; none may appear outside the data platform itself.
"""
import json
import re
from datetime import date

import pytest

from jobs.profiler import profile

ROW_VALUE_PATTERNS = {
    "member_id": re.compile(r"\bM\d{7}\b"),
    "claim_id": re.compile(r"\bC\d{8}\b"),
    "lab_id": re.compile(r"\bL\d{8}\b"),
    "payer_member_id": re.compile(r"\b(?:AZ[123]|TX[12]|LA1|TN1|VA1)\d{9}\b"),
    "npi": re.compile(r"\b99\d{8}\b"),
    "rx_ndc": re.compile(r"\b7\d{4}-\d{4}-\d{2}\b"),
}
AGG = re.compile(r"\b(count|avg|sum|min|max|datediff)\s*\(", re.I)


def find_row_values(text: str) -> dict:
    return {k: p.findall(text)[:3] for k, p in ROW_VALUE_PATTERNS.items() if p.search(text)}


def test_patterns_catch_examples():
    assert find_row_values("member M0001234 claim C00012345 npi 9900001207 sub AZ1501938459")
    assert not find_row_values("redshift://eqh/core/claim_header null_rate 0.03 PAYER_TX2")


@pytest.mark.parametrize("full_load", [True, False])
def test_profiler_selects_only_aggregates(full_load):
    for key, col, metric, sql in profile.build_queries(date(2026, 10, 20), full_load):
        values = re.findall(r"AS segment,(.*?)\bAS value", sql, re.I | re.S)
        assert values, f"{metric}: no value column"
        for v in values:  # every value expression is an aggregate; only segment labels are non-aggregated
            assert AGG.search(v), f"{key} {metric}: non-aggregate value {v!r}"

def test_enrichment_prompt_has_no_row_values():
    from jobs.enrich import enrich
    assert "Never invent data values" in enrich.INSTRUCTIONS
    keys = {"asset_key", "platform", "type", "existing_comment", "domain_hint", "state_hint", "columns", "upstream",
            "downstream", "column_lineage", "glossary"}
    src = open(enrich.__file__).read()
    for k in keys:
        assert f'"{k}"' in src
    assert "select *" not in src.lower()


@pytest.mark.aws
def test_metadata_store_has_no_row_values():
    from jobs.common.db import MetaDB
    db = MetaDB(role="assistant")
    checks = {
        "asset": "select coalesce(source_comment,'') || ' ' || coalesce(ai_description,'') || ' ' || "
                 "coalesce(steward_description,'') || ' ' || ai_meta::text as t from asset",
        "asset_column": "select coalesce(source_comment,'') || ' ' || coalesce(ai_description,'') as t from asset_column",
        "embedding": "select content as t from embedding",
        "dq_issue": "select detail::text || ' ' || segment as t from dq_issue",
        "dq_metric": "select distinct segment as t from dq_metric",
        "lineage": "select dst_key || ' ' || attrs::text as t from lineage_edge",
        "glossary": "select definition as t from glossary_term",
    }
    for name, sql in checks.items():
        text = "\n".join(r["t"] or "" for r in db.query(sql))
        assert not find_row_values(text), f"{name} contains row-level values: {find_row_values(text)}"


@pytest.mark.aws
def test_logs_have_no_row_values():
    import boto3
    from jobs.common import settings
    logs = boto3.client("logs", region_name=settings.get()["region"])
    for group in ("/eqh-dq/pipeline", "/eqh-dq/assistant", "/eqh-dq/bedrock-invocations"):
        try:
            events = logs.filter_log_events(logGroupName=group, limit=2000)["events"]
        except logs.exceptions.ResourceNotFoundException:
            continue
        text = "\n".join(e["message"] for e in events)
        hits = find_row_values(text)
        assert not hits, f"{group}: {hits}"


@pytest.mark.aws
def test_tool_results_have_no_row_values():
    from assistant.app import tools as T
    ctx = T.Ctx(["analyst", "steward", "restricted_bh"])
    for name, args in [("get_asset", {"asset_key": "redshift://eqh/core/claim_header"}),
                       ("get_dq_issues", {}), ("get_lineage", {"asset_key": "redshift://eqh/core/lab_result",
                                                                 "direction": "downstream"}),
                       ("search_assets", {"query": "member eligibility"})]:
        out = json.dumps(T.call(ctx, name, args), default=str)
        assert not find_row_values(out), f"{name}: {find_row_values(out)}"
