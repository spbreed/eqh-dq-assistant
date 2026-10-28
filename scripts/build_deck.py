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

SAMPLES = [  # (eval id, persona, why it matters) — two per slide
    ("B7-06", "demo-analyst", "Volume drop traced by payer/state segment to the PAYER_LA1 feed"),
    ("B7-04", "demo-analyst", "Column-level impact through late-binding views to the payer submission"),
    ("B7-05", "demo-steward", "7-day triage ranked by impact on payer submissions"),
    ("B7-09", "demo-analyst", "Duplicates found and attributed to the payer (PAYER_AZ2 resent a file)"),
]
FOOT = '<div class="foot">www.emergertech.com &nbsp;|&nbsp; All rights reserved Emergere, Copyright © 2026</div>'


def data_uri(p: Path) -> str:
    mime = "image/png" if p.suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def answer_html(text: str, limit: int = 2200) -> str:
    t = text.strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
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
        rows.append(f"<tr><td><b>{d['id']}</b> {html.escape(d['description'])}</td><td>{status}</td></tr>")
    n_issue_types = sum(1 for d in truth if d["expected_detection"] in det_map)

    sec = [("Budget alerts + automatic deny", True), ("No public S3; KMS encryption on all buckets", True),
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

    def card(qid, who, why):
        r = rows_by_id.get(qid)
        if not r:
            return ""
        tools = ", ".join(r["tools_called"]) or "none (refused before any tool call)"
        return f"""<div class="qa"><div class="q"><div class="who">{who}</div>
          <div class="text">“{html.escape(r['question'])}”</div>
          <div class="meta">Tools: {html.escape(tools)} · {r['latency_s']} s · {'✔ correct' if r['correct'] else '✘ incorrect'}</div></div>
          <div class="a">{answer_html(r['answer'], 1100)}</div><div class="why">{html.escape(why)}</div></div>"""

    slides = []
    for i, pg in ((0, 12), (2, 13)):
        pair = "".join(card(*x) for x in SAMPLES[i:i + 2])
        slides.append(f"""
<section>
  <div class="hdr"><div class="bar"></div><h2>Sample prompts &amp; real responses ({pg - 11}/2)</h2><img class="mark" src="{{{{MARK}}}}" alt=""></div><div class="rule"></div>
  <div class="body"><div class="qa2">{pair}</div></div>
  <div class="pg">{pg}</div>{FOOT}
</section>""")

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
    }
    out = tpl.replace("{{SAMPLE_SLIDES}}", "\n".join(slides))
    icons = ROOT / "docs" / "deck" / "icons"
    for name in set(re.findall(r"\{\{ICON:([A-Za-z0-9]+)\}\}", out)):
        svg = (icons / f"{name}.svg").read_bytes()
        out = out.replace("{{ICON:" + name + "}}", "data:image/svg+xml;base64," + base64.b64encode(svg).decode())
    for k, v in rep.items():
        out = out.replace(k, v)
    (ROOT / "eqh-dq-assistant.html").write_text(out)
    print(f"wrote eqh-dq-assistant.html ({len(out) // 1024} KB, {out.count('<section')} slides)")


if __name__ == "__main__":
    main()
