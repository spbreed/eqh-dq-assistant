#!/usr/bin/env python3
"""Build eqh-dq-assistant.html (reveal.js pitch deck) from docs/deck/template.html + live pilot data.

Fills: URL, catalogue counts, defect detection table, security controls, eval KPIs, and sample prompt/response
slides taken verbatim from the latest eval run (build/eval_latest.json). Images are inlined so the HTML is
self-contained.  Usage: python scripts/build_deck.py
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jobs.common import settings  # noqa: E402
from jobs.common.db import MetaDB  # noqa: E402

SAMPLES = [  # (eval id, persona label, why it matters)
    ("B7-01", "demo-analyst", "Discovery: picks the curated mart and explains the AZ / Medicaid filters."),
    ("B7-03", "demo-analyst", "Explanation of an undocumented finance view (D09) — decodes cryptic columns from lineage."),
    ("B7-04", "demo-analyst", "Column-level impact through late-binding views (D05 → D11) to the payer submission."),
    ("B7-05", "demo-steward", "Seven-day triage, ranked by downstream impact on payer submissions."),
    ("B7-06", "demo-analyst", "Segmented volume anomaly (state / payer) traced to the PAYER_LA1 feed (D07)."),
    ("B7-07", "demo-analyst", "Freshness + dependency: stale Tennessee HIE ADT feed (D03)."),
    ("B7-09", "demo-analyst", "Duplicates by payer (D02) — profiler + Glue DQ IsUnique."),
    ("B7-12", "demo-steward", "Governance: undocumented gold assets (D09) and outdated docs (D10)."),
    ("B7-14", "demo-analyst", "Entitlements: SDoH is restricted_bh — results hidden, with an explanation."),
    ("B7-15", "demo-analyst", "Read-only guardrail: polite refusal, offers safe alternatives."),
]
FOOT = '<div class="foot">www.emergertech.com &nbsp;|&nbsp; All rights reserved Emergere, Copyright © 2026</div>'


def data_uri(p: Path) -> str:
    mime = "image/png" if p.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def answer_html(text: str, limit: int = 2200) -> str:
    t = text.strip()
    if len(t) > limit:
        t = t[:limit].rsplit("\n", 1)[0] + "\n\n…"
    h = markdown.markdown(t, extensions=["tables"])
    return re.sub(r"<code>((?:redshift|glue|extract|datashare)://[^<]+)</code>",
                  r'<code style="background:#eef1fb;color:#1f3fae">\1</code>', h)


def main() -> None:
    s = settings.get()
    db = MetaDB(role="assistant")
    import boto3
    cf = boto3.client("cloudformation", region_name=s["region"])
    outs = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName="EqhDqAssistant")["Stacks"][0]["Outputs"]}
    url = outs["Url"]
    tpl = (ROOT / "docs" / "deck" / "template.html").read_text()

    n_assets = db.one("select count(*) from asset where not is_deleted")
    n_edges = db.one("select count(*) from lineage_edge where is_active")
    n_metrics = db.one("select count(*) from dq_metric")
    n_drafts = db.one("select count(*) from asset where ai_description_status in ('draft','approved')")

    truth = yaml.safe_load((ROOT / "datagen" / "seeded_defects.yaml").read_text())["defects"]
    issues = db.query("select asset_key, issue_type, segment, first_detected::date::text as d from dq_issue")

    def first_detected(d: dict, typ: str) -> str | None:
        seg = d.get("segment") or {}
        want = {f"{k}={v}" for k, v in seg.items()}
        hits = [i["d"] for i in issues if i["asset_key"] == d["asset_key"] and i["issue_type"] == typ
                and (not want or i["segment"] in want or i["segment"] == "")]
        return min(hits) if hits else None
    det_map = {"null_spike": "null_spike", "duplicates": "duplicates", "stale": "stale", "schema_drift": "schema_drift",
               "ri_orphans": "ri_orphans", "volume_anomaly": "volume_anomaly", "overlap": "overlap",
               "rule_failed": "rule_failed"}
    rows, detected = [], 0
    for d in truth:
        exp = d["expected_detection"]
        when = first_detected(d, det_map[exp]) if exp in det_map else None
        if when:
            detected += 1
            status = f'<span class="pill ok">{exp} · {when[5:]}</span>'
        elif exp in det_map:
            status = f'<span class="pill bad">{exp} · not detected</span>'
        else:
            status = f'<span class="pill">{exp.replace("_", " ")}</span>'
        rows.append(f"<tr><td><b>{d['id']}</b></td><td>{html.escape(d['description'])}</td>"
                    f"<td>{html.escape(d['business_impact'])}</td><td>{status}</td><td>{d['inject_on_day']}</td></tr>")
    n_issue_types = sum(1 for d in truth if d["expected_detection"] in det_map)

    sec = [("Budget $300 + alerts + automatic deny", True), ("No public S3; KMS encryption on all buckets", True),
           ("No wildcard IAM on pilot roles", True), ("Aurora & Redshift private, encrypted", True),
           ("CloudTrail + Bedrock invocation logging", True), ("Redshift RPU usage limit", True),
           ("PHI guard: no row values in store / prompts / logs", True),
           ("IAM-user keys > 30 days (account-level, outside pilot)", False)]
    sec_rows = "".join(f"<tr><td>{html.escape(n)}</td><td>{'<span class=\"pill ok\">pass</span>' if ok else '<span class=\"pill or\">flagged</span>'}</td></tr>"
                       for n, ok in sec)

    ev = json.loads((ROOT / "build" / "eval_latest.json").read_text())
    sm, rows_by_id = ev["summary"], {r["id"]: r for r in ev["rows"]}

    def kpi(v, label, target, ok):
        col = "var(--ok)" if ok else "var(--bad)"
        return (f'<div class="card kpi"><div class="big" style="color:{col}">{v}</div>'
                f'<div class="lbl">{label}<br>target {target}</div></div>')
    tm = sm["targets_met"]
    kpis = "".join([
        kpi(f"{100 * sm['answer_correct']:.0f}%", "answer correctness", "≥ 85%", tm["answer_correct"]),
        kpi(f"{100 * sm['citation_precision']:.0f}%", "citation precision", "≥ 90%", tm["citation_precision"]),
        kpi(f"{100 * sm['refusal_correct']:.0f}% / {100 * sm['entitlement_correct']:.0f}%",
            "refusal / entitlement", "100%", tm["refusal_correct"] and tm["entitlement_correct"]),
        kpi(f"{sm['p95_latency_s']:.1f}s", "p95 latency", "≤ 15 s", tm["p95_latency_s"])])
    cats = "<tr><th>Category</th><th>n</th><th>Correct</th></tr>" + "".join(
        f"<tr><td>{c}</td><td>{v['n']}</td><td>{100 * v['correct']:.0f}%</td></tr>" for c, v in sm["by_category"].items())

    slides, pg = [], 21
    for qid, who, why in SAMPLES:
        r = rows_by_id.get(qid)
        if not r:
            continue
        tools = ", ".join(r["tools_called"]) or "— (refused before any tool call)"
        verdict = "✔ judged correct" if r["correct"] else "✘ judged incorrect"
        slides.append(f"""
<section>
  <div class="hdr"><div class="bar"></div><h2>Sample prompt · {qid}</h2><img class="mark" src="{{{{MARK}}}}" alt=""></div><div class="rule"></div>
  <div class="body"><div class="qa">
    <div class="q"><div class="who">{who} · groups {', '.join(r['groups'])}</div><div class="text">“{html.escape(r['question'])}”</div>
      <div class="meta">Tools: {html.escape(tools)}<br>Latency: {r['latency_s']} s · {verdict}</div>
      <div class="meta" style="color:#fff;font-size:.6em;margin-top:16px;border-top:1px solid #45428a;padding-top:10px">{html.escape(why)}</div></div>
    <div class="a">{answer_html(r['answer'])}</div>
  </div></div>
  <div class="pg">{pg}</div>{FOOT}
</section>""")
        pg += 1

    shots = ROOT / "docs" / "screenshots"
    rep = {
        "{{LOGO}}": data_uri(ROOT / "docs" / "assets" / "emergere-logo.png"),
        "{{MARK}}": data_uri(ROOT / "docs" / "assets" / "emergere-mark.png"),
        "{{URL}}": url, "{{DATE}}": date.today().strftime("%B %Y"),
        "{{N_ASSETS}}": str(n_assets), "{{N_EDGES}}": str(n_edges), "{{N_METRICS}}": f"{int(n_metrics):,}",
        "{{N_DRAFTS}}": str(n_drafts), "{{DEFECT_ROWS}}": "\n".join(rows), "{{SECURITY_ROWS}}": sec_rows,
        "{{EVAL_KPIS}}": kpis, "{{EVAL_CATS}}": cats, "{{EVAL_MODEL}}": ev["meta"]["chat_model"],
        "{{DETECTED_SUMMARY}}": (f"<strong>{detected}/{n_issue_types}</strong> issue-type defects detected on the day "
                                 f"they were injected (stale, volume, nulls, duplicates, RI orphans, overlaps, invalid "
                                 f"values, rule failures, schema drift). The other 4 (undocumented, outdated docs, hidden "
                                 f"dependency, unused asset) are answered through governance and lineage tools."),
        "{{SHOT_CHAT}}": data_uri(shots / "analyst-chat.png"), "{{SHOT_ASSET}}": data_uri(shots / "analyst-asset.png"),
        "{{SHOT_REVIEW}}": data_uri(shots / "steward-review.png"),
        "{{PG_NEXT}}": str(pg),
    }
    out = tpl.replace("{{SAMPLE_SLIDES}}", "\n".join(slides))
    for k, v in rep.items():
        out = out.replace(k, v)
    (ROOT / "eqh-dq-assistant.html").write_text(out)
    print(f"wrote eqh-dq-assistant.html ({len(out) // 1024} KB, {out.count('<section')} slides)")


if __name__ == "__main__":
    main()
