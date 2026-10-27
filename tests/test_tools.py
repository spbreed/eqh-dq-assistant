import json

from assistant.app import agent
from assistant.app import tools as T


def test_tool_specs_are_strict_and_complete():
    specs = T.tool_specs()
    assert {s["name"] for s in specs} == set(T.TOOLS)
    for s in specs:
        p = s["parameters"]
        assert p["additionalProperties"] is False and set(p["required"]) == set(p["properties"])
        json.dumps(s)


def test_write_intent_is_refused_without_model():
    for q in ("Delete the duplicate claims for me.", "Drop the legacy_pmpm_2023 table.",
              "Update the comment on core.member"):
        assert agent.WRITE_INTENT.search(q), q
    for q in ("Do we have duplicate claims? From which payer?", "Which payer feeds had schema changes this week?",
              "Why did Louisiana claims volume drop yesterday?"):
        assert not agent.WRITE_INTENT.search(q), q


def test_impact_ranking_order():
    assert T._impact_class("extract://payer_supplemental_quality_file") == "outbound_payer_submission"
    assert T._impact_class("redshift://eqh/careempower/open_care_gaps") == "careempower_feed"
    assert T._impact_class("redshift://eqh/vbc_mart/member_month") == "mart"


def test_review_queue_respects_entitlements(monkeypatch):
    from assistant.app import review

    class DB:
        def query(self, sql, params=None):
            if "from asset_entitlement" in sql:
                return [{"asset_key": "glue://eqh_raw/raw_careempower_ops", "column_name": "", "group_name": "restricted_bh"}]
            if "from sync_run" in sql:
                return []
            if "ai_description_status = 'draft'" in sql:
                return [{"asset_key": k, "asset_type": "table", "business_domain": None, "source_comment": None,
                         "ai_description": "x", "ai_meta": {}, "updated_at": None}
                        for k in ("glue://eqh_raw/raw_careempower_ops", "redshift://eqh/core/member")]
            return []

        def one(self, sql, params=None):
            return None

    monkeypatch.setattr(review, "MetaDB", lambda role: DB())
    keys = [r["asset_key"] for r in review.queue(["analyst", "steward"])]
    assert keys == ["redshift://eqh/core/member"]
    keys = [r["asset_key"] for r in review.queue(["steward", "restricted_bh"])]
    assert "glue://eqh_raw/raw_careempower_ops" in keys
