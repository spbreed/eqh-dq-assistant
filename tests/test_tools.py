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
