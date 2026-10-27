"""Enrichment (SPEC Phase 4c): AI documentation drafts with GPT-5.6 Luna for steward review.

Inputs are metadata only — names, types, comments, lineage neighbours, glossary hits; never row values.
Output follows a strict JSON schema {description, column_descriptions, tags, business_domain, doc_issues,
confidence}. Drafts land in asset.ai_description (status 'draft') and asset_column.ai_description. The job never
touches Glue/Redshift comments or steward_description.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from jobs.common import llm
from jobs.common.db import MetaDB

log = logging.getLogger("enrich")
BATCH_THRESHOLD = 100
DOMAINS = ["eligibility", "claims", "quality", "care-model", "finance", "HIE", "network", "unknown"]

SCHEMA = {
    "title": "asset_documentation",
    "type": "object",
    "additionalProperties": False,
    "required": ["description", "column_descriptions", "tags", "business_domain", "doc_issues", "confidence"],
    "properties": {
        "description": {"type": "string", "description": "2-4 sentence plain-language description for analysts"},
        "column_descriptions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["column", "description"],
            "properties": {"column": {"type": "string"}, "description": {"type": "string"}}}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "business_domain": {"type": "string", "enum": DOMAINS},
        "doc_issues": {"type": "array", "items": {"type": "string"},
                       "description": "Problems with the existing documentation, e.g. a comment that mentions a "
                                      "column that does not exist, terse or misleading text"},
        "confidence": {"type": "number"},
    },
}

INSTRUCTIONS = """You document data assets for a Medicaid value-based-care data platform (synthetic pilot).
You receive ONLY metadata: object name, type, existing comments, column names/types/comments, lineage
neighbours and glossary terms. Never invent data values. Write a concise description for business analysts,
a short description for every column (expand cryptic abbreviations using lineage and glossary evidence, and say
"likely" when inferring), 2-6 tags, the business domain, and doc_issues: compare the existing comments with the
actual column list (doc_lint holds deterministic findings: always include them) and flag any comment that references columns that do not exist, contradicts a column's type,
or is too terse to be useful. confidence is 0-1. Return JSON only."""


# column-like identifiers only (enumerated values such as well_child are not flagged)
IDENT = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:id|date|code|flag|npi|amt|amount|month|key|ts)\b")


def doc_lint(comment: str | None, columns: list[str], other_comments: list[str | None]) -> list[str]:
    """Deterministic documentation checks (metadata only): identifiers mentioned in comments that are not columns."""
    names = {c.lower() for c in columns}
    issues = []
    for text, where in [(comment, "table comment")] + [(c, "a column comment") for c in other_comments]:
        for ident in sorted(set(IDENT.findall((text or "").lower()))):
            if ident not in names and not ident.startswith(("payer_", "raw_", "vbc_", "core_")):
                issues.append(f"{where} references '{ident}', which is not a column of this asset (outdated documentation)")
    return issues


def build_context(db: MetaDB, asset_key: str) -> dict | None:
    a = db.query("""select asset_key, platform, asset_type, schema_name, object_name, source_comment, business_domain,
                           state from asset where asset_key = :k and not is_deleted""", {"k": asset_key})
    if not a:
        return None
    a = a[0]
    cols = db.query("""select c.column_name, c.data_type, c.source_comment from asset_column c join asset x
                       using (asset_id) where x.asset_key = :k order by c.ordinal""", {"k": asset_key})
    up = db.query("""select src_asset_key as k, edge_type, attrs from lineage_edge where dst_key = :k and is_active
                     and edge_type <> 'glossary' limit 25""", {"k": asset_key})
    down = db.query("""select dst_key as k, edge_type from lineage_edge where src_asset_key = :k and is_active
                       and edge_type not in ('query_consumer','glossary') limit 25""", {"k": asset_key})
    glossary = db.query("""select g.term, left(g.definition, 300) as definition from lineage_edge e
                           join glossary_term g on lower('glossary://' || g.term) = e.src_asset_key
                           where e.dst_key = :k and e.edge_type = 'glossary' limit 6""", {"k": asset_key})
    col_map = []
    for u in up:
        attrs = u["attrs"] if isinstance(u["attrs"], dict) else json.loads(u["attrs"] or "{}")
        for m in attrs.get("columns", [])[:40]:
            col_map.append(f"{m['dst_col']} <- {u['k']}.{m['src_col']}")
    return {
        "asset_key": a["asset_key"], "platform": a["platform"], "type": a["asset_type"],
        "existing_comment": a["source_comment"], "domain_hint": a["business_domain"], "state_hint": a["state"],
        "columns": [{"name": c["column_name"], "type": c["data_type"], "comment": c["source_comment"]} for c in cols],
        "upstream": [f"{u['k']} ({u['edge_type']})" for u in up],
        "downstream": [f"{d['k']} ({d['edge_type']})" for d in down],
        "column_lineage": col_map,
        "glossary": glossary,
        "doc_lint": doc_lint(a["source_comment"], [c["column_name"] for c in cols],
                             [c["source_comment"] for c in cols]),
    }


def draft(ctx: dict, attempts: int = 3) -> dict:
    err: Exception | None = None
    for _ in range(attempts):
        try:
            r = llm.respond("enrich", json.dumps(ctx, default=str), instructions=INSTRUCTIONS, json_schema=SCHEMA,
                            max_output_tokens=4000, reasoning_effort="low")
            return llm.json_of(r, SCHEMA)
        except (ValueError, json.JSONDecodeError) as e:  # malformed JSON: ask again
            err = e
    raise RuntimeError(f"no valid draft after {attempts} attempts: {err}")


def save(db: MetaDB, asset_key: str, doc_hash: str, out: dict, lint: list[str] | None = None) -> None:
    out["doc_issues"] = list(dict.fromkeys(list(lint or []) + list(out.get("doc_issues") or [])))
    meta = {"tags": out["tags"], "doc_issues": out["doc_issues"], "confidence": out["confidence"],
            "ai_business_domain": out["business_domain"], "model": llm.model("enrich")}
    with db.transaction():
        db.execute("""update asset set ai_description = :d, ai_description_status = 'draft',
                      ai_meta = :m::jsonb, tags = (select coalesce(array_agg(x), '{}')
                                                   from jsonb_array_elements_text(:t::jsonb) x)
                      where asset_key = :k and steward_description is null""",
                   {"d": out["description"], "m": meta, "t": out["tags"], "k": asset_key})
        rows = [{"k": asset_key, "c": c["column"], "d": c["description"]} for c in out["column_descriptions"]]
        if rows:
            db.executemany("""update asset_column set ai_description = :d where column_name = :c and asset_id =
                              (select asset_id from asset where asset_key = :k)""", rows)
        db.execute("update enrichment_task set status='drafted', updated_at=now() where asset_key=:k and doc_hash=:h",
                   {"k": asset_key, "h": doc_hash})


def run(limit: int | None = None, workers: int = 6) -> dict:
    db = MetaDB(role="harvest")
    tasks = db.query("""select distinct on (t.asset_key) t.asset_key, t.doc_hash from enrichment_task t
                        join asset a using (asset_key)
                        where t.status in ('pending','failed') and not a.is_deleted and a.steward_description is null
                        order by t.asset_key, t.created_at desc""")
    if limit:
        tasks = tasks[:limit]
    mode = "online" if len(tasks) <= BATCH_THRESHOLD else "online-concurrent"
    # Backlogs > BATCH_THRESHOLD would use Bedrock batch inference; see docs/DECISIONS.md for why the pilot
    # runs them as bounded concurrent Responses calls instead.
    log.info("enrichment backlog %d (%s)", len(tasks), mode)
    stats = {"drafted": 0, "failed": 0, "skipped": 0}

    def one(t):
        try:
            ctx = build_context(db, t["asset_key"])
            if ctx is None:
                return "skipped"
            save(db, t["asset_key"], t["doc_hash"], draft(ctx), ctx["doc_lint"])
            return "drafted"
        except Exception as e:  # noqa: BLE001
            log.warning("enrich %s failed: %s", t["asset_key"], str(e)[:200])
            db.execute("update enrichment_task set status='failed', error=:e, updated_at=now() "
                       "where asset_key=:k and doc_hash=:h", {"e": str(e)[:500], "k": t["asset_key"], "h": t["doc_hash"]})
            return "failed"

    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(one, tasks):
            stats[r] += 1
    # stale tasks for superseded doc hashes
    db.execute("""update enrichment_task t set status='skipped' where status='pending' and exists
                  (select 1 from enrichment_task n where n.asset_key=t.asset_key and n.status='drafted'
                   and n.created_at > t.created_at)""")
    log.info("enrichment done: %s", stats)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    run(ap.parse_args().limit)


if __name__ == "__main__":
    main()
