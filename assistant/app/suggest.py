"""Prompt suggestions for the chat UI: starter prompts per domain, autocomplete catalogue, follow-up prompts.

Everything here is metadata only (asset, schema and column names, glossary terms) and respects entitlements:
restricted assets and columns never reach the browser for users outside their group.
Follow-ups are derived deterministically from the tools the agent called and the assets it cited, so they cost no
extra model call and never suggest a change to data.
"""
from __future__ import annotations

import re
import threading
import time

from assistant.app import tools as T

# Starter prompts by domain. Each was answered correctly in the latest eval run (build/eval_latest.json).
STARTERS: list[dict] = [
    {"id": "find", "label": "Find data", "icon": "🔎", "prompts": [
        "Where do I find ED visits per 1,000 by practice for Arizona Medicaid?",
        "Which dataset should I use for PMPM cost by practice?",
        "Which dataset should I use for CareEmpower open care gaps?",
        "Where does Health at Home enrollment and outcome data live, and who uses it?"]},
    {"id": "explain", "label": "Explain", "icon": "💡", "prompts": [
        "Explain `vbc_mart.practice_shared_savings_calc` in plain language.",
        "What is vbc_mart.member_month and what is it built from?",
        "What does PMPM mean here?",
        "What does redetermination mean here?"]},
    {"id": "lineage", "label": "Lineage & impact", "icon": "🧬", "prompts": [
        "If the HbA1c result value changes type, which payer submissions and CareEmpower views are affected?",
        "What would break if core.eligibility_span changed?",
        "What feeds core.claim_header upstream?",
        "Which outbound extracts go to PAYER_AZ1?"]},
    {"id": "dq", "label": "Data quality", "icon": "🩺", "prompts": [
        "What DQ issues opened in the last 7 days? Prioritise by impact on payer submissions.",
        "Why did Louisiana claims volume drop yesterday?",
        "Is the Tennessee HIE ADT feed current? What depends on it?",
        "Do we have duplicate claims? From which payer?"]},
    {"id": "docs", "label": "Documentation", "icon": "📝", "prompts": [
        "Which gold-layer assets are undocumented or have outdated documentation?",
        "Is the core.member documentation accurate?",
        "Which marts have no table comments?",
        "Which assets haven't been read in 30 days?"]},
    {"id": "restricted", "label": "Behavioural health", "icon": "🔒", "groups": ["restricted_bh"], "prompts": [
        "Describe the SDoH screening data and its Z-code quality.",
        "What columns are in core.sdoh_screening?"]},
]


def starters(groups: list[str]) -> list[dict]:
    g = set(groups or [])
    return [{k: v for k, v in s.items() if k != "groups"} for s in STARTERS
            if not s.get("groups") or g & set(s["groups"])]


# ------------------------------------------------------------------ autocomplete catalogue
def short_name(key: str) -> str:
    """redshift://eqh/core/claim_header -> core.claim_header; glue://eqh_raw/x -> eqh_raw.x; extract://x -> x."""
    m = re.match(r"redshift://[^/]+/([^/]+)/(.+)$", key)
    if m:
        return f"{m[1]}.{m[2]}"
    m = re.match(r"glue://([^/]+)/(.+)$", key)
    if m:
        return f"{m[1]}.{m[2]}"
    return key.split("://", 1)[-1]


_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()
TTL_S = 600


def catalog(ctx: T.Ctx) -> dict:
    """Names the user is entitled to see, for type-ahead: schemas, tables/views, columns, glossary terms, payers."""
    ck = tuple(sorted(ctx.groups))
    with _lock:
        hit = _cache.get(ck)
        if hit and time.time() - hit[0] < TTL_S:
            return hit[1]
    rows = ctx.db.query("""select asset_key, platform, asset_type, business_domain from asset
                           where not is_deleted order by asset_key""")
    assets = [{"name": short_name(r["asset_key"]), "key": r["asset_key"], "type": r["asset_type"],
               "domain": r["business_domain"] or ""} for r in rows if ctx.visible(r["asset_key"])]
    visible = {a["key"] for a in assets}
    schemas = sorted({a["name"].split(".")[0] for a in assets if "." in a["name"]})
    hidden_cols = ctx.hidden_cols
    cols = ctx.db.query("""select a.asset_key, c.column_name from asset_column c join asset a using (asset_id)
                           where not a.is_deleted order by a.asset_key, c.ordinal""")
    columns = [[c["column_name"], short_name(c["asset_key"])] for c in cols
               if c["asset_key"] in visible and c["column_name"] not in hidden_cols.get(c["asset_key"], set())]
    terms = [r["term"] for r in ctx.db.query("select term from glossary_term order by term")]
    out = {"assets": assets, "schemas": schemas, "columns": columns, "terms": terms,
           "payers": [f"PAYER_{p}" for p in sorted(T.PAYERS)]}
    with _lock:
        _cache[ck] = (time.time(), out)
    return out


# ------------------------------------------------------------------ follow-ups
DQ_TOOLS = {"get_dq_issues", "get_dq_trend", "get_schema_changes"}
LINEAGE_TOOLS = {"get_lineage", "impact_of_change"}
DOC_TOOLS = {"list_undocumented_assets", "list_unused_assets"}


def _primary_assets(res: dict) -> list[str]:
    """Cited assets, curated Redshift objects first (they are what users act on)."""
    order = {"redshift": 0, "extract": 1, "datashare": 2, "glue": 3}
    cites = res.get("citations") or []
    return sorted(cites, key=lambda k: (order.get(k.split("://")[0], 9), cites.index(k)))


def followups(question: str, res: dict, groups: list[str] | None = None, limit: int = 4) -> list[str]:
    tools = {c["name"] for c in res.get("tool_calls") or []}
    assets = [short_name(k) for k in _primary_assets(res)]
    q = question.lower()
    out: list[str] = []

    if res.get("refused"):
        out += ["Which data quality issues are open right now, ranked by impact?",
                "What is downstream of core.claim_header?",
                "Which gold-layer assets are undocumented or have outdated documentation?"]
    else:
        a = assets[0] if assets else None
        if tools & DQ_TOOLS:
            if "impact" not in q and "priorit" not in q:
                out.append("Prioritise these issues by impact on payer submissions.")
            if a:
                out.append(f"Show the daily trend for {a}.")
                out.append(f"What is downstream of {a}, and who is affected?")
            out.append("Which open issues are high severity?")
        if tools & LINEAGE_TOOLS:
            if a:
                out.append(f"What DQ issues affect {a}?")
                out.append(f"Explain {a} in plain language.")
            if "payer" not in q:
                out.append("Which payer submissions are affected?")
        if tools & DOC_TOOLS:
            out += ["Is the core.member documentation accurate?", "Which marts have no table comments?"]
            if a:
                out.append(f"Who uses {a}?")
        if "search_glossary" in tools:
            out.append("Which datasets use this term?")
        if tools & {"search_assets", "get_asset"} or not out:
            if a:
                out += [f"What feeds {a} upstream?", f"What would break if {a} changed?",
                        f"Are there open DQ issues on {a}?"]
            else:
                out += ["What DQ issues opened in the last 7 days?", "Which assets haven't been read in 30 days?"]

    seen, final = {question.strip().lower()}, []
    for s in out:
        if s.lower() not in seen and not _write_like(s):
            seen.add(s.lower())
            final.append(s)
    return final[:limit]


def _write_like(s: str) -> bool:
    from assistant.app.agent import WRITE_INTENT
    return bool(WRITE_INTENT.search(s))
