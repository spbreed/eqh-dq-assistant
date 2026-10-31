from assistant.app import agent, suggest


class FakeDB:
    def query(self, sql, params=None):
        if "from asset_column" not in sql and "from asset" in sql:
            return [{"asset_key": k, "platform": k.split(":")[0], "asset_type": "table", "business_domain": "claims"}
                    for k in ("redshift://eqh/core/claim_header", "redshift://eqh/core/sdoh_screening",
                              "glue://eqh_raw/raw_la1_clm_extract")]
        if "from asset_column" in sql:
            return [{"asset_key": "redshift://eqh/core/claim_header", "column_name": "dx_code_1"},
                    {"asset_key": "redshift://eqh/core/claim_header", "column_name": "secret_col"},
                    {"asset_key": "redshift://eqh/core/sdoh_screening", "column_name": "z_code"}]
        if "from glossary_term" in sql:
            return [{"term": "PMPM"}]
        raise AssertionError(sql)


class FakeCtx:
    def __init__(self, groups):
        self.groups, self.db = set(groups), FakeDB()
        self.hidden = set() if "restricted_bh" in groups else {"redshift://eqh/core/sdoh_screening"}
        self.hidden_cols = {} if "restricted_bh" in groups else {"redshift://eqh/core/claim_header": {"secret_col"}}

    def visible(self, key):
        return key not in self.hidden


def test_short_names():
    assert suggest.short_name("redshift://eqh/core/claim_header") == "core.claim_header"
    assert suggest.short_name("glue://eqh_raw/raw_la1_clm_extract") == "eqh_raw.raw_la1_clm_extract"
    assert suggest.short_name("extract://payer_supplemental_quality_file") == "payer_supplemental_quality_file"


def test_catalog_respects_entitlements():
    suggest._cache.clear()
    c = suggest.catalog(FakeCtx(["analyst"]))
    names = {a["name"] for a in c["assets"]}
    assert "core.claim_header" in names and "core.sdoh_screening" not in names
    cols = {col for col, _ in c["columns"]}
    assert cols == {"dx_code_1"}  # hidden column and columns of hidden assets are not exposed
    assert set(c["schemas"]) == {"core", "eqh_raw"} and "PAYER_LA1" in c["payers"]
    suggest._cache.clear()
    c = suggest.catalog(FakeCtx(["analyst", "restricted_bh"]))
    assert "core.sdoh_screening" in {a["name"] for a in c["assets"]}


def test_starters_gate_restricted_domain():
    assert "restricted" not in {d["id"] for d in suggest.starters(["analyst"])}
    assert "restricted" in {d["id"] for d in suggest.starters(["analyst", "restricted_bh"])}
    for d in suggest.STARTERS:
        for p in d["prompts"]:
            assert not agent.WRITE_INTENT.search(p), p


def test_followups_from_tools_and_citations():
    res = {"tool_calls": [{"name": "get_dq_issues"}],
           "citations": ["glue://eqh_raw/raw_la1_clm_extract", "redshift://eqh/core/claim_header"]}
    f = suggest.followups("Why did Louisiana claims volume drop yesterday?", res)
    assert 1 <= len(f) <= 4
    assert any("core.claim_header" in s for s in f)  # curated Redshift asset preferred over the raw feed
    assert all(not agent.WRITE_INTENT.search(s) for s in f)


def test_followups_after_refusal_and_no_tools():
    f = suggest.followups("Delete the duplicate claims for me.", {"refused": True, "tool_calls": [], "citations": []})
    assert f and all(not agent.WRITE_INTENT.search(s) for s in f)
    assert suggest.followups("hello", {"tool_calls": [], "citations": []})
    q = "Which open issues are high severity?"
    assert q not in suggest.followups(q, {"tool_calls": [{"name": "get_dq_issues"}], "citations": []})
