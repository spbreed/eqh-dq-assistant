"""Read-only assistant tools (SPEC Phase 5). Parameterised SQL against the metadata store only.

Every tool applies entitlements: assets (or columns) listed in asset_entitlement are visible only to members of
the named Cognito group. Results never contain row-level data — the store holds metadata and aggregates only.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timedelta

from jobs.common import embed as E
from jobs.common.db import MetaDB

MAX_DEPTH = 3
IMPACT_ORDER = ["outbound_payer_submission", "careempower_feed", "practice_delivery", "finance_datashare",
                "actuarial_datashare", "mart", "consumer", "other"]


class Ctx:
    def __init__(self, groups: list[str], db: MetaDB | None = None):
        self.groups = set(groups or [])
        self.db = db or MetaDB(role="assistant")
        self._hidden: set[str] | None = None
        self._hidden_cols: dict[str, set[str]] | None = None
        self.as_of = self._as_of()

    def _as_of(self) -> datetime:
        v = self.db.one("select max(coalesce(as_of, started_at)) from sync_run where status='succeeded'")
        return datetime.fromisoformat(str(v)[:19]) if v else datetime.utcnow()

    def _load_entitlements(self) -> None:
        rows = self.db.query("select asset_key, column_name, group_name from asset_entitlement")
        allowed: dict[tuple, set] = {}
        for r in rows:
            allowed.setdefault((r["asset_key"], r["column_name"]), set()).add(r["group_name"])
        self._hidden = {k for (k, c), g in allowed.items() if c == "" and not (g & self.groups)}
        self._hidden_cols = {}
        for (k, c), g in allowed.items():
            if c and not (g & self.groups):
                self._hidden_cols.setdefault(k, set()).add(c)

    @property
    def hidden(self) -> set[str]:
        if self._hidden is None:
            self._load_entitlements()
        return self._hidden

    @property
    def hidden_cols(self) -> dict[str, set[str]]:
        if self._hidden_cols is None:
            self._load_entitlements()
        return self._hidden_cols

    def visible(self, key: str) -> bool:
        return key not in self.hidden


DOMAINS = {"eligibility", "claims", "quality", "care-model", "finance", "HIE", "network"}
ISSUE_TYPES = {"stale": "stale", "fresh": "stale", "late": "stale", "volume": "volume_anomaly", "drop": "volume_anomaly",
               "null": "null_spike", "missing": "null_spike", "dup": "duplicates", "orphan": "ri_orphans",
               "referential": "ri_orphans", "ri": "ri_orphans", "overlap": "overlap", "invalid": "invalid_values",
               "domain": "invalid_values", "rule": "rule_failed", "drift": "schema_drift", "schema": "schema_drift",
               "type": "schema_drift"}
PAYERS = {"AZ1", "AZ2", "AZ3", "TX1", "TX2", "LA1", "TN1", "VA1"}
STATES = {"AZ", "TX", "LA", "TN", "VA"}


def resolve_key(ctx: "Ctx", key: str | None) -> str | None:
    """Accept full asset keys or short names ('core.claim_header', 'eqh_raw.raw_hie_tn_adt', 'claim_header')."""
    if not key:
        return key
    k = key.strip().strip("`").lower()
    if "://" in k:
        return k
    parts = [p for p in k.replace("/", ".").split(".") if p and p != "eqh"]
    name, schema = parts[-1], (parts[-2] if len(parts) > 1 else None)
    rows = ctx.db.query("select asset_key, platform, schema_name, database_name from asset where object_name = :n "
                        "and not is_deleted", {"n": name})
    if schema:
        rows = [r for r in rows if schema in ((r["schema_name"] or ""), (r["database_name"] or ""))] or rows
    order = lambda r: (0 if r["platform"] == "redshift" and r["schema_name"] != "spectrum_silver" else
                       1 if r["platform"] in ("extract", "datashare") else 2 if r["platform"] == "glue" else 3)
    rows.sort(key=order)
    return rows[0]["asset_key"] if rows else k


def norm_issue_type(t: str | None) -> str | None:
    if not t:
        return None
    t = t.lower().strip()
    if t in set(ISSUE_TYPES.values()):
        return t
    return next((v for k, v in ISSUE_TYPES.items() if k in t), None)


def norm_segment(seg: str | None) -> str | None:
    if not seg:
        return seg
    s = seg.strip().upper().replace(" ", "")
    if "=" in s:
        k, v = s.split("=", 1)
        k = k.lower()
        if k in ("payer", "payer_code"):
            v = v if v.startswith("PAYER_") else f"PAYER_{v}"
            return f"payer_code={v}"
        return f"state={v}" if k == "state" else seg
    if s.startswith("PAYER_") or s in PAYERS:
        return f"payer_code={s if s.startswith('PAYER_') else 'PAYER_' + s}"
    if s in STATES:
        return f"state={s}"
    return seg


def norm_domain(d: str | None) -> str | None:
    if not d:
        return None
    m = {x.lower(): x for x in DOMAINS}
    return m.get(d.lower().replace("_", "-"))


def _impact_class(key: str) -> str:
    k = key.lower()
    if k.startswith("extract://") and ("payer" in k or "supplemental" in k):
        return "outbound_payer_submission"
    if "/outbound/payer_" in k:
        return "outbound_payer_submission"
    if "careempower" in k:
        return "careempower_feed"
    if k.startswith("extract://") or "/outbound/" in k:
        return "practice_delivery"
    if "finance" in k or "shared_savings" in k or "incentive" in k:
        return "finance_datashare" if k.startswith("datashare://") or "datashare" in k else "mart"
    if k.startswith("datashare://") or k.startswith("consumer://"):
        return "actuarial_datashare"
    if "/vbc_mart/" in k:
        return "mart"
    if k.startswith("user://") or k.startswith("target://"):
        return "consumer"
    return "other"


def _describe(r: dict) -> tuple[str | None, str]:
    if r.get("steward_description"):
        return r["steward_description"], "steward-approved"
    if r.get("source_comment"):
        return r["source_comment"], "source comment"
    if r.get("ai_description"):
        return r["ai_description"], "AI draft – not yet approved"
    return None, "undocumented"


# ---------------------------------------------------------------- tools
def search_assets(ctx: Ctx, query: str, domain: str | None = None, state: str | None = None,
                  platform: str | None = None, k: int = 8) -> dict:
    k = max(1, min(int(k or 8), 20))
    filters, params = ["not a.is_deleted"], {"q": query, "k": k * 4}
    if norm_domain(domain):
        filters.append("a.business_domain = :domain")
        params["domain"] = norm_domain(domain)
    if state:
        filters.append("(a.state = :state or a.state is null)")
        params["state"] = state.upper()
    if platform:
        filters.append("a.platform = :platform")
        params["platform"] = platform
    where = " and ".join(filters)
    scores: dict[str, float] = {}
    query = (query or "").strip() or "data asset"
    domain = norm_domain(domain)
    try:
        params["v"] = E.vec(E.embed(query))
        for r in ctx.db.query(f"""
                select e.asset_key, max(1 - (e.embedding <=> :v::vector)) as s
                from embedding e join asset a on a.asset_key = e.asset_key
                where e.chunk_type in ('asset','columns') and {where}
                group by e.asset_key order by s desc limit :k""", params):
            scores[r["asset_key"]] = float(r["s"])
    except E.EmbeddingUnavailable:
        pass
    params.pop("v", None)
    for r in ctx.db.query(f"""
            select a.asset_key, greatest(similarity(a.object_name, :q),
                   max(ts_rank(to_tsvector('english', e.content), plainto_tsquery('english', :q)))) as s
            from asset a left join embedding e on e.asset_key = a.asset_key
            where {where} group by a.asset_key, a.object_name order by s desc nulls last limit :k""", params):
        if r["s"]:
            scores[r["asset_key"]] = scores.get(r["asset_key"], 0) + 0.5 * float(r["s"])
    # curated Redshift objects first: marts/views/core over Spectrum externals and raw feeds
    def weight(key: str) -> float:
        if "/spectrum_silver/" in key:
            return 0.75
        if key.startswith("glue://eqh_raw/"):
            return 0.7
        if key.startswith("glue://"):
            return 0.8
        return 1.15 if key.startswith("redshift://") else 1.0
    scores = {key: v * weight(key) for key, v in scores.items()}
    ranked = [key for key, _ in sorted(scores.items(), key=lambda x: -x[1]) if ctx.visible(key)][:k]
    hidden = len([key for key in scores if not ctx.visible(key)])
    notice = (f"{hidden} matching asset(s) are hidden because they require the restricted_bh group. Tell the user "
              "that some results are restricted.") if hidden else None
    if not ranked:
        return {"results": [], "hidden_by_entitlement": hidden, "notice": notice}
    rows = {r["asset_key"]: r for r in ctx.db.query("""
        select asset_key, platform, asset_type, business_domain, state, steward_description, source_comment,
               ai_description from asset where asset_key in (select jsonb_array_elements_text(:keys::jsonb))""",
                                                     {"keys": ranked})}
    out = []
    for key in ranked:
        r = rows[key]
        desc, src = _describe(r)
        out.append({"asset_key": key, "type": r["asset_type"], "domain": r["business_domain"], "state": r["state"],
                    "description": (desc or "")[:300], "description_source": src, "score": round(scores[key], 3)})
    return {"results": out, "hidden_by_entitlement": hidden, "notice": notice}


NOT_ENTITLED = {"error": "not_entitled",
                "message": "This asset is restricted (requires the restricted_bh group); its metadata is hidden."}


def get_asset(ctx: Ctx, asset_key: str) -> dict:
    asset_key = resolve_key(ctx, asset_key)
    if not ctx.visible(asset_key):
        return dict(NOT_ENTITLED)
    rows = ctx.db.query("""select asset_key, platform, asset_type, schema_name, object_name, business_domain, state,
                                  steward_description, source_comment, ai_description, ai_description_status, tags,
                                  ai_meta, last_seen_at, last_read_at, read_count_30d, owner, is_deleted
                           from asset where asset_key = :k""", {"k": asset_key})
    if not rows:
        return {"error": "unknown_asset", "asset_key": asset_key}
    a = rows[0]
    desc, src = _describe(a)
    hidden_cols = ctx.hidden_cols.get(asset_key, set())
    cols = []
    for c in ctx.db.query("""select c.column_name, c.data_type, c.source_comment, c.steward_description, c.ai_description
                             from asset_column c join asset a using (asset_id) where a.asset_key = :k
                             order by c.ordinal""", {"k": asset_key}):
        if c["column_name"] in hidden_cols:
            continue
        cd, cs = _describe(c)
        cols.append({"name": c["column_name"], "type": c["data_type"], "description": cd, "description_source": cs})
    fresh = ctx.db.query("""select segment, value, measured_at from dq_metric where asset_key = :k
                            and metric = 'hours_since_last_ingest' and measured_at = (select max(measured_at)
                            from dq_metric where asset_key = :k and metric = 'hours_since_last_ingest')""",
                         {"k": asset_key})
    issues = ctx.db.query("""select issue_type, severity, column_name, segment, first_detected from dq_issue
                             where asset_key = :k and status = 'open'""", {"k": asset_key})
    meta = a["ai_meta"] if isinstance(a["ai_meta"], dict) else json.loads(a["ai_meta"] or "{}")
    owners = [r["dst_key"] for r in ctx.db.query(
        "select distinct dst_key from lineage_edge where src_asset_key = :k and edge_type in ('query_consumer') "
        "and is_active limit 10", {"k": asset_key})]
    last_read = a["last_read_at"]
    return {
        "asset_key": asset_key, "platform": a["platform"], "type": a["asset_type"], "domain": a["business_domain"],
        "state": a["state"], "description": desc, "description_source": src,
        "ai_draft": a["ai_description"] if src != "AI draft – not yet approved" else None,
        "ai_doc_issues": meta.get("doc_issues", []), "tags": a["tags"], "columns": cols,
        "hidden_columns": len(hidden_cols), "freshness": fresh, "open_issues": issues,
        "last_read_at": last_read, "reads_30d": a["read_count_30d"],
        "days_since_last_read": (ctx.as_of - datetime.fromisoformat(str(last_read)[:19])).days if last_read else None,
        "owner": a["owner"], "readers": owners, "deleted": a["is_deleted"],
    }


def _edges(ctx: Ctx, key: str, direction: str) -> list[dict]:
    if direction == "upstream":
        return ctx.db.query("""select src_asset_key as other, edge_type, attrs from lineage_edge
                               where dst_key = :k and is_active and edge_type <> 'glossary'""", {"k": key})
    return ctx.db.query("""select dst_key as other, edge_type, attrs from lineage_edge
                           where src_asset_key = :k and is_active and edge_type <> 'glossary'""", {"k": key})


def _cols(attrs) -> list[dict]:
    a = attrs if isinstance(attrs, dict) else json.loads(attrs or "{}")
    return a.get("columns", [])


def get_lineage(ctx: Ctx, asset_key: str, direction: str = "both", depth: int = 2, column: str | None = None) -> dict:
    asset_key = resolve_key(ctx, asset_key)
    direction = direction if direction in ("upstream", "downstream", "both") else "both"
    if not ctx.visible(asset_key):
        return dict(NOT_ENTITLED)
    depth = max(1, min(int(depth or 2), MAX_DEPTH))
    dirs = ["upstream", "downstream"] if direction == "both" else [direction]
    out = {"asset_key": asset_key, "column": column, "depth": depth}
    for d in dirs:
        nodes, edges = [], []
        seen = {(asset_key, (column or "").lower())}
        q = deque([(asset_key, (column or "").lower(), 0)])
        while q:
            key, col, lvl = q.popleft()
            if lvl >= depth:
                continue
            for e in _edges(ctx, key, d):
                other = e["other"]
                if not ctx.visible(other):
                    continue
                next_cols = [""]
                if col:  # follow column-level lineage where we have it
                    cm = _cols(e["attrs"])
                    if e["edge_type"] == "view_dependency" and cm:
                        next_cols = [m["dst_col"] for m in cm if m["src_col"] == col] if d == "downstream" else \
                                    [m["src_col"] for m in cm if m["dst_col"] == col]
                        if not next_cols:
                            continue
                    elif e["edge_type"] in ("copy_load", "spectrum", "raw_to_silver"):
                        next_cols = [col]
                for nc in next_cols:
                    edges.append({"from": key if d == "downstream" else other, "to": other if d == "downstream" else key,
                                  "type": e["edge_type"], "column": nc or None,
                                  "late_binding": bool((e["attrs"] if isinstance(e["attrs"], dict)
                                                        else json.loads(e["attrs"] or "{}")).get("late_binding"))})
                    if (other, nc) not in seen:
                        seen.add((other, nc))
                        nodes.append({"key": other, "column": nc or None, "level": lvl + 1})
                        if not other.startswith(("user://", "target://", "consumer://")):
                            q.append((other, nc, lvl + 1))
        out[d] = {"nodes": nodes, "edges": edges}
    return out


def impact_of_change(ctx: Ctx, asset_key: str, column: str | None = None) -> dict:
    asset_key = resolve_key(ctx, asset_key)
    lin = get_lineage(ctx, asset_key, "downstream", MAX_DEPTH, column)
    if "error" in lin:
        return lin
    # extend beyond depth 3 cheaply for delivery endpoints
    affected: dict[str, dict] = {}
    frontier = [(n["key"], n["column"]) for n in lin["downstream"]["nodes"]]
    for n in lin["downstream"]["nodes"]:
        affected[n["key"]] = {"asset_key": n["key"], "via_column": n["column"], "hops": n["level"]}
    for key, col in frontier:
        if key.startswith(("user://", "target://", "consumer://")):
            continue
        more = get_lineage(ctx, key, "downstream", MAX_DEPTH, col)
        for n in more.get("downstream", {}).get("nodes", []):
            affected.setdefault(n["key"], {"asset_key": n["key"], "via_column": n["column"],
                                           "hops": n["level"] + affected[key]["hops"]})
    groups: dict[str, list] = {c: [] for c in IMPACT_ORDER}
    for a in affected.values():
        groups[_impact_class(a["asset_key"])].append(a)
    late = [e for e in lin["downstream"]["edges"] if e["late_binding"]]
    return {"asset_key": asset_key, "column": column, "as_of": ctx.as_of.date().isoformat(),
            "impact_ranked": [{"category": c, "assets": sorted(groups[c], key=lambda x: x["hops"])}
                              for c in IMPACT_ORDER if groups[c]],
            "late_binding_hops": late, "total_affected": len(affected)}


def _priority(ctx: Ctx, key: str, cache: dict) -> tuple[int, str]:
    if key not in cache:
        imp = impact_of_change(ctx, key)
        cats = [g["category"] for g in imp.get("impact_ranked", [])]
        best = min((IMPACT_ORDER.index(c) for c in cats), default=len(IMPACT_ORDER))
        cache[key] = (best, IMPACT_ORDER[best] if best < len(IMPACT_ORDER) else "none")
    return cache[key]


def get_dq_issues(ctx: Ctx, asset_key: str | None = None, domain: str | None = None, state: str | None = None,
                  payer: str | None = None, status: str | None = "open", since: str | None = None,
                  issue_type: str | None = None) -> dict:
    f, p = ["true"], {}
    issue_type = norm_issue_type(issue_type)
    domain = norm_domain(domain)
    if asset_key:
        f.append("i.asset_key = :k")
        p["k"] = resolve_key(ctx, asset_key)
    if domain:
        f.append("a.business_domain = :d")
        p["d"] = domain
    if state:
        f.append("(a.state = :st or i.segment = 'state=' || :st or i.segment like 'payer_code=PAYER_' || :st || '%%')")
        p["st"] = state.upper()
    if payer:
        f.append("(i.segment = 'payer_code=' || :py or i.asset_key like '%%' || lower(substr(:py, 7)) || '%%')")
        py = payer.upper().replace(" ", "")
        p["py"] = py if py.startswith("PAYER_") else f"PAYER_{py}"
    if status and status != "all":
        f.append("i.status = :s")
        p["s"] = status
    if issue_type:
        f.append("i.issue_type = :t")
        p["t"] = issue_type
    if since:
        f.append("i.first_detected >= :since::timestamptz")
        p["since"] = _since(ctx, since)
    rows = ctx.db.query(f"""select i.id, i.asset_key, i.column_name, i.segment, i.issue_type, i.severity, i.detail,
                                   i.first_detected, i.last_detected, i.status, a.business_domain, a.state
                            from dq_issue i left join asset a on a.asset_key = i.asset_key
                            where {' and '.join(f)} order by i.first_detected desc limit 100""", p)
    cache: dict = {}
    out = []
    for r in rows:
        if not ctx.visible(r["asset_key"]):
            continue
        rank, cat = _priority(ctx, r["asset_key"], cache)
        sev = {"high": 0, "medium": 1, "low": 2}[r["severity"]]
        out.append({**{k: r[k] for k in ("asset_key", "column_name", "segment", "issue_type", "severity",
                                         "first_detected", "last_detected", "status", "business_domain", "state")},
                    "detail": r["detail"] if isinstance(r["detail"], dict) else json.loads(r["detail"] or "{}"),
                    "top_downstream_impact": cat, "_rank": (rank, sev)})
    out.sort(key=lambda x: x["_rank"])
    for o in out:
        o.pop("_rank")
    hidden = sum(1 for r in rows if not ctx.visible(r["asset_key"]))
    extra = {}
    if hidden:
        extra["notice"] = (f"{hidden} issue(s) are on restricted_bh assets and are hidden. Tell the user that some "
                           "results are restricted.")
    if not out and (asset_key or domain or state or payer or issue_type or since):
        # filters matched nothing: show what IS open so the model doesn't conclude "no issues" from a bad filter
        others = ctx.db.query("""select asset_key, issue_type, segment, severity from dq_issue where status='open'
                                 order by first_detected desc limit 40""")
        extra["no_match_for_filters"] = True
        extra["other_open_issues"] = [o for o in others if ctx.visible(o["asset_key"])][:25]
    return {"as_of": ctx.as_of.date().isoformat(), "issues": out, **extra,
            "ranking": "outbound payer submissions > CareEmpower feeds > practice deliveries > finance datashares "
                       "> actuarial datashares > internal marts; then severity"}


def _since(ctx: Ctx, since: str) -> str:
    s = since.strip().lower()
    if s.endswith("d") and s[:-1].isdigit():
        return (ctx.as_of - timedelta(days=int(s[:-1]))).isoformat()
    if s.isdigit():
        return (ctx.as_of - timedelta(days=int(s))).isoformat()
    return s


def get_dq_trend(ctx: Ctx, asset_key: str, metric: str, column: str | None = None, segment: str | None = None,
                 days: int = 21) -> dict:
    asset_key = resolve_key(ctx, asset_key)
    segment = norm_segment(segment)
    if not ctx.visible(asset_key):
        return dict(NOT_ENTITLED)
    rows = ctx.db.query("""select measured_at::date as day, value from dq_metric
                           where asset_key = :k and metric = :m and column_name = :c and segment = :s
                             and measured_at >= :start::timestamptz order by measured_at""",
                        {"k": asset_key, "m": metric, "c": column or "", "s": segment or "",
                         "start": (ctx.as_of - timedelta(days=int(days or 21))).isoformat()})
    if metric == "row_count" and rows:  # volume questions: the per-day series is what users mean
        daily = ctx.db.query("""select measured_at::date as day, value from dq_metric
                                where asset_key = :k and metric = 'daily_rows' and column_name = '' and segment = :s
                                  and measured_at >= :start::timestamptz order by measured_at""",
                             {"k": asset_key, "s": segment or "",
                              "start": (ctx.as_of - timedelta(days=int(days or 21))).isoformat()})
        if daily:
            return {"asset_key": asset_key, "metric": "daily_rows", "column": column, "segment": segment or "(all)",
                    "note": "row_count is the cumulative table size; daily_rows (rows received per day) is shown "
                            "because it is what volume questions need.",
                    "series": [{"day": str(r["day"]), "value": r["value"]} for r in daily],
                    "cumulative_row_count_last": rows[-1]["value"]}
    avail = ctx.db.query("""select distinct metric, column_name, segment from dq_metric where asset_key = :k
                            and (metric = :m or :m = '') order by 1,2,3 limit 60""",
                         {"k": asset_key, "m": metric}) if not rows else []
    return {"asset_key": asset_key, "metric": metric, "column": column, "segment": segment or "(all)",
            "series": [{"day": str(r["day"]), "value": r["value"]} for r in rows],
            "available_series": avail}


def get_schema_changes(ctx: Ctx, asset_key: str | None = None, since: str | None = None) -> dict:
    f, p = ["change_type <> 'asset_added'"], {}
    if asset_key:
        f.append("asset_key = :k")
        p["k"] = resolve_key(ctx, asset_key)
    if since:
        f.append("detected_at >= :since::timestamptz")
        p["since"] = _since(ctx, since)
    rows = ctx.db.query(f"""select asset_key, change_type, column_name, old_value, new_value, detected_at
                            from schema_change where {' and '.join(f)} order by detected_at desc limit 100""", p)
    return {"as_of": ctx.as_of.date().isoformat(), "changes": [r for r in rows if ctx.visible(r["asset_key"])]}


def list_undocumented_assets(ctx: Ctx, domain: str | None = None, include_outdated: bool = True) -> dict:
    p = {}
    f = ["not a.is_deleted", "a.platform = 'redshift'", "a.schema_name in ('vbc_mart','outbound','careempower','core')"]
    if norm_domain(domain):
        f.append("a.business_domain = :d")
        p["d"] = norm_domain(domain)
    elif domain and domain.lower().replace("-", "_") in ("vbc_mart", "outbound", "careempower", "core"):
        f.append("a.schema_name = :sch")  # callers sometimes pass a schema as "domain"
        p["sch"] = domain.lower().replace("-", "_")
    rows = ctx.db.query(f"""
        select a.asset_key, a.business_domain, a.ai_description_status, a.source_comment is null as no_comment,
               a.steward_description is null as no_steward, a.ai_meta -> 'doc_issues' as doc_issues,
               (select count(*) from asset_column c where c.asset_id = a.asset_id) as n_cols,
               (select count(*) from asset_column c where c.asset_id = a.asset_id and c.source_comment is not null)
                   as n_cols_commented
        from asset a where {' and '.join(f)}""", p)
    undocumented, outdated = [], []
    for r in rows:
        if not ctx.visible(r["asset_key"]):
            continue
        issues = r["doc_issues"] if isinstance(r["doc_issues"], list) else json.loads(r["doc_issues"] or "[]")
        if r["no_comment"] and r["no_steward"]:
            undocumented.append({"asset_key": r["asset_key"], "domain": r["business_domain"], "table_comment": None,
                                 "columns_commented": f"{r['n_cols_commented']}/{r['n_cols']}",
                                 "ai_draft_status": r["ai_description_status"]})
        if include_outdated and issues:
            outdated.append({"asset_key": r["asset_key"], "doc_issues": issues})
    gold = [u for u in undocumented if "/core/" not in u["asset_key"]]
    pending = ctx.db.query("""select asset_key, business_domain from asset where ai_description_status = 'draft'
                              and not is_deleted order by asset_key""")
    return {"undocumented_gold_layer": gold, "undocumented_core": [u for u in undocumented if u not in gold],
            "outdated_documentation": outdated,
            "awaiting_steward_review": {"count": len(pending),
                                        "assets": [r["asset_key"] for r in pending if ctx.visible(r["asset_key"])][:40]},
            "note": "AI drafts are 'AI draft – not yet approved' until a steward approves them in the review queue."}


def list_unused_assets(ctx: Ctx, days: int = 30, include_external: bool = False) -> dict:
    cutoff = ctx.as_of - timedelta(days=int(days or 30))
    rows = ctx.db.query("""select asset_key, asset_type, last_read_at, read_count_30d from asset
                           where not is_deleted and platform = 'redshift'""")
    reads = {r["asset_key"]: r for r in rows}
    unused = []
    for r in rows:
        if r["asset_type"] == "external_table" and not include_external:
            continue
        lin = get_lineage(ctx, r["asset_key"], "downstream", MAX_DEPTH)
        keys = [r["asset_key"]] + [n["key"] for n in lin.get("downstream", {}).get("nodes", [])]
        deliveries = [k for k in keys if k.startswith(("extract://", "datashare://"))]
        last = [reads[k]["last_read_at"] for k in keys if k in reads and reads[k]["last_read_at"]]
        latest = max((datetime.fromisoformat(str(x)[:19]) for x in last), default=None)
        if deliveries or (latest and latest >= cutoff):
            continue
        unused.append({"asset_key": r["asset_key"], "type": r["asset_type"],
                       "last_read_at": str(latest) if latest else None,
                       "note": "never read since usage tracking began" if not latest else
                               f"last read {(ctx.as_of - latest).days} days ago"})
    marts = [u for u in unused if "/core/" not in u["asset_key"]]
    core = [u for u in unused if "/core/" in u["asset_key"]]
    return {"as_of": ctx.as_of.date().isoformat(), "days": days, "unused_marts_and_views": marts,
            "unused_core_reference_tables": core,
            "method": "no direct reads and no reads of any downstream view; delivery-backed assets excluded. "
                      "Lead with unused marts/views (candidates for retirement); core reference tables are listed "
                      "separately because they are loaded for completeness."}


def search_glossary(ctx: Ctx, term: str) -> dict:
    rows = ctx.db.query("""select term, definition, synonyms, related,
                                  greatest(similarity(term, :t), (select max(similarity(s, :t)) from unnest(synonyms) s))
                                  as s
                           from glossary_term order by s desc nulls last limit 5""", {"t": term})
    hits = [r for r in rows if r["s"] and r["s"] > 0.15]
    if not hits:
        try:
            v = E.vec(E.embed(term))
            hits = ctx.db.query("""select g.term, g.definition, g.synonyms, g.related from embedding e
                                   join glossary_term g on lower('glossary://' || g.term) = e.asset_key
                                   where e.chunk_type = 'glossary' order by e.embedding <=> :v::vector limit 3""",
                                {"v": v})
        except E.EmbeddingUnavailable:
            hits = []
    for h in hits:
        h.pop("s", None)
        h["related_assets"] = [r["dst_key"] for r in ctx.db.query(
            "select dst_key from lineage_edge where src_asset_key = lower('glossary://' || :t) and is_active limit 8",
            {"t": h["term"]}) if ctx.visible(r["dst_key"])]
    return {"terms": hits}


TOOLS = {f.__name__: f for f in (search_assets, get_asset, get_lineage, impact_of_change, get_dq_issues, get_dq_trend,
                                 get_schema_changes, list_undocumented_assets, list_unused_assets, search_glossary)}

_S, _I, _B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
_ns = {"type": ["string", "null"]}
SPECS = [
    ("search_assets", "Find datasets by meaning or name (pgvector + keyword). Use first for discovery questions.",
     {"query": _S, "domain": {"type": ["string", "null"], "enum": ["eligibility", "claims", "quality", "care-model",
                                                                    "finance", "HIE", "network", None]},
      "state": _ns, "platform": {"type": ["string", "null"], "enum": ["glue", "redshift", "extract", "datashare", None]},
      "k": {"type": ["integer", "null"]}}, ["query"]),
    ("get_asset", "Full description, columns, tags, freshness, open issues, readers and last-read date of one asset.",
     {"asset_key": _S}, ["asset_key"]),
    ("get_lineage", "Upstream/downstream lineage (depth<=3) including datashares, extracts and consumers. "
                    "Pass column for column-level lineage.",
     {"asset_key": _S, "direction": {"type": "string", "enum": ["upstream", "downstream", "both"]},
      "depth": {"type": ["integer", "null"]}, "column": _ns}, ["asset_key", "direction"]),
    ("impact_of_change", "Downstream impact of changing an asset or column, ranked: payer submissions, CareEmpower "
                         "feeds, practice deliveries, finance/actuarial datashares, marts, consumers.",
     {"asset_key": _S, "column": _ns}, ["asset_key"]),
    ("get_dq_issues", "Data quality issues with business impact, ranked by downstream impact. since accepts '7d'.",
     {"asset_key": _ns, "domain": _ns, "state": _ns, "payer": _ns,
      "status": {"type": ["string", "null"], "enum": ["open", "resolved", "all", None]}, "since": _ns,
      "issue_type": {"type": ["string", "null"], "enum": ["stale", "volume_anomaly", "null_spike", "duplicates",
                                                          "ri_orphans", "overlap", "invalid_values", "rule_failed",
                                                          "schema_drift", None]}}, []),
    ("get_dq_trend", "Daily time series of a DQ metric. Use daily_rows for volume (rows received per day; row_count is "
                     "the cumulative size), null_rate (with column), dup_rate, ri_orphan_rate, overlap_rate, "
                     "invalid_value_rate, hours_since_last_ingest. segment like 'state=LA' or 'payer_code=PAYER_TX2'.",
     {"asset_key": _S, "metric": _S, "column": _ns, "segment": _ns, "days": {"type": ["integer", "null"]}},
     ["asset_key", "metric"]),
    ("get_schema_changes", "Schema drift log (columns added/removed, type changes). since accepts '7d'.",
     {"asset_key": _ns, "since": _ns}, []),
    ("list_undocumented_assets", "Gold-layer assets without documentation, and assets whose documentation is "
                                 "outdated (from enrichment doc_issues).",
     {"domain": _ns, "include_outdated": {"type": ["boolean", "null"]}}, []),
    ("list_unused_assets", "Redshift assets not read (directly or through downstream views) in N days.",
     {"days": {"type": ["integer", "null"]}, "include_external": {"type": ["boolean", "null"]}}, []),
    ("search_glossary", "Business definitions for VBC / Medicaid terms (PMPM, care gap, HEDIS, Health at Home...).",
     {"term": _S}, ["term"]),
]


def tool_specs() -> list[dict]:
    out = []
    for name, desc, props, req in SPECS:
        out.append({"type": "function", "name": name, "description": desc, "strict": True,
                    "parameters": {"type": "object", "properties": props, "required": list(props),
                                   "additionalProperties": False}})
    return out


def call(ctx: Ctx, name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    args = {k: v for k, v in (args or {}).items() if v is not None}
    try:
        return TOOLS[name](ctx, **args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
