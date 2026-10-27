"""Evaluation harness (SPEC Phase 6). Runs the golden questions through the real agent (same code, same DB role,
same models as the service) and scores:
  tool-call correctness, answer correctness (LLM judge + rubric), citation precision,
  refusal and entitlement correctness, latency.
Targets: >=85% correct, >=90% citation precision, 100% refusal/entitlement, p95 <= 15 s.
Writes eval/report.html (+ results JSON); --upload copies both to s3://<dq-results>/eval/.
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import boto3
import yaml

from assistant.app import agent
from jobs.common import llm, settings

log = logging.getLogger("eval")
HERE = Path(__file__).resolve().parent
TARGETS = {"answer_correct": 0.85, "citation_precision": 0.90, "refusal_correct": 1.0, "entitlement_correct": 1.0,
           "p95_latency_s": 15.0}
REFUSAL_RE = re.compile(r"read[- ‑]only|can[’']t|cannot|can not|not able|unable|won[’']t|not permitted|"
                        r"don[’']t have permission|no row-level|not allowed|i[’']m sorry", re.I)
JUDGE = {"title": "judgement", "type": "object", "additionalProperties": False,
         "required": ["score", "correct", "reason"],
         "properties": {"score": {"type": "number"}, "correct": {"type": "boolean"}, "reason": {"type": "string"}}}
JUDGE_INSTRUCTIONS = """You grade answers from a read-only data-catalog / data-quality assistant (synthetic data).
Given the question, the rubric facts and the answer, judge whether the answer is correct and useful: it must be
consistent with the rubric facts (paraphrase is fine; extra correct detail is fine), must not contradict them, and
must not invent datasets. Partial answers that capture the main point count as correct. score is 0-1.
Return JSON only."""


def judge(q: dict, answer: str) -> dict:
    if q["refusal"]:
        ok = bool(REFUSAL_RE.search(answer))
        return {"score": 1.0 if ok else 0.0, "correct": ok, "reason": "refusal check"}
    payload = {"question": q["question"], "rubric_facts": q["facts"], "answer": answer[:6000]}
    for attempt in range(5):
        try:
            r = llm.respond("judge", json.dumps(payload), instructions=JUDGE_INSTRUCTIONS, json_schema=JUDGE,
                            max_output_tokens=1500, reasoning_effort="low")
            return llm.json_of(r, JUDGE)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            time.sleep(2 * (attempt + 1))
    return {"score": 0.0, "correct": False, "reason": f"judge error: {err[:200]}"}


def run_one(q: dict) -> dict:
    t0 = time.time()
    try:
        res = agent.answer(q["question"], q["groups"], user="eval")
    except Exception as e:  # noqa: BLE001
        log.exception("question %s failed", q["id"])
        res = {"answer": f"ERROR {type(e).__name__}: {e}", "refused": False, "tool_calls": [], "citations": [],
               "tool_result_keys": [], "latency_s": time.time() - t0}
    called = [c["name"] for c in res["tool_calls"]]
    tool_ok = (not called) if q["refusal"] else (not q["expect_tools"] or any(t in called for t in q["expect_tools"]))
    valid = set(res.get("tool_result_keys", []))
    cites = res["citations"]
    precise = [c for c in cites if c in valid]
    must = q.get("must_cite") or []
    recall = sum(1 for m in must if m in cites or m in res["answer"]) / len(must) if must else None
    refused = res.get("refused") or bool(REFUSAL_RE.search(res["answer"][:400]))
    refusal_ok = refused if q["refusal"] else not res.get("refused")
    text = res["answer"].lower()
    # leak = restricted *content* in the answer or in what tools returned (asset names in the user's own question
    # are not a leak; the forbidden list holds restricted column names / keys that must never be returned)
    leaked = [f for f in q.get("forbidden", []) if f.lower() in text or f in valid]
    ent_ok = not leaked
    j = judge(q, res["answer"])
    return {**q, "answer": res["answer"], "tools_called": called, "tool_ok": tool_ok, "citations": cites,
            "citation_precision": (len(precise) / len(cites)) if cites else None, "must_cite_recall": recall,
            "refusal_ok": refusal_ok, "entitlement_ok": ent_ok, "leaked": leaked, "judge": j,
            "correct": bool(j.get("correct")) and tool_ok and ent_ok and refusal_ok,
            "latency_s": round(res["latency_s"], 2)}


def summarise(rows: list[dict]) -> dict:
    cp = [r["citation_precision"] for r in rows if r["citation_precision"] is not None]
    lat = sorted(r["latency_s"] for r in rows)
    p95 = lat[max(0, int(round(0.95 * len(lat))) - 1)] if lat else 0
    ref = [r for r in rows if r["refusal"]]
    ent = [r for r in rows if r["category"] == "entitlement" or r["forbidden"]]
    s = {"n": len(rows), "answer_correct": sum(r["correct"] for r in rows) / len(rows),
         "tool_call_correct": sum(r["tool_ok"] for r in rows) / len(rows),
         "citation_precision": sum(cp) / len(cp) if cp else 1.0,
         "must_cite_recall": statistics.mean([r["must_cite_recall"] for r in rows if r["must_cite_recall"] is not None]
                                             or [1.0]),
         "refusal_correct": sum(r["refusal_ok"] for r in rows) / len(rows),
         "refusal_questions_correct": (sum(r["refusal_ok"] for r in ref) / len(ref)) if ref else 1.0,
         "entitlement_correct": (sum(r["entitlement_ok"] for r in ent) / len(ent)) if ent else 1.0,
         "p50_latency_s": statistics.median(lat) if lat else 0, "p95_latency_s": p95,
         "by_category": {}}
    for c in sorted({r["category"] for r in rows}):
        rs = [r for r in rows if r["category"] == c]
        s["by_category"][c] = {"n": len(rs), "correct": sum(r["correct"] for r in rs) / len(rs)}
    s["targets_met"] = {k: (s[k] <= v if k.endswith("latency_s") else s[k] >= v) for k, v in TARGETS.items()}
    return s


def report(rows: list[dict], s: dict, meta: dict) -> str:
    def pct(v):
        return f"{100 * v:.1f}%"

    tgt = "".join(f"<tr><td>{k}</td><td>{(f'{s[k]:.2f}s' if k.endswith('_s') else pct(s[k]))}</td>"
                  f"<td>{(f'≤ {v}s' if k.endswith('_s') else '≥ ' + pct(v))}</td>"
                  f"<td class={'ok' if s['targets_met'][k] else 'bad'}>{'met' if s['targets_met'][k] else 'missed'}</td></tr>"
                  for k, v in TARGETS.items())
    cats = "".join(f"<tr><td>{c}</td><td>{v['n']}</td><td>{pct(v['correct'])}</td></tr>"
                   for c, v in s["by_category"].items())
    body = "".join(
        f"<tr class={'ok' if r['correct'] else 'bad'}><td>{r['id']}</td><td>{html.escape(r['category'])}</td>"
        f"<td>{html.escape(r['question'])}<div class=m>groups: {', '.join(r['groups'])}</div></td>"
        f"<td>{'✔' if r['correct'] else '✘'}<div class=m>{html.escape(str(r['judge'].get('reason', '')))[:300]}</div></td>"
        f"<td>{html.escape(', '.join(r['tools_called']))}<div class=m>tool_ok={r['tool_ok']}</div></td>"
        f"<td>{'' if r['citation_precision'] is None else pct(r['citation_precision'])}</td>"
        f"<td>{r['latency_s']}</td>"
        f"<td><details><summary>answer</summary><pre>{html.escape(r['answer'])}</pre></details></td></tr>"
        for r in rows)
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Eval report</title><style>
body{{font:14px system-ui,sans-serif;margin:24px;color:#1d2433}}table{{border-collapse:collapse;margin:12px 0}}
td,th{{border:1px solid #e2e5ea;padding:5px 8px;vertical-align:top;text-align:left}}.ok td:first-child,.ok{{}}
td.ok{{color:#067647;font-weight:600}}td.bad{{color:#b42318;font-weight:600}}tr.bad td:first-child{{border-left:4px solid #b42318}}
tr.ok td:first-child{{border-left:4px solid #067647}}.m{{color:#5b6475;font-size:12px}}pre{{white-space:pre-wrap;max-width:700px}}
.banner{{background:#fff4e5;padding:6px 10px;border:1px solid #f5c58b}}</style></head><body>
<div class=banner>Prototype – synthetic data</div><h1>Data Quality Assistant — evaluation report</h1>
<p class=m>{html.escape(json.dumps(meta))}</p>
<h2>Targets</h2><table><tr><th>metric</th><th>result</th><th>target</th><th></th></tr>{tgt}</table>
<p>Tool-call correctness {pct(s['tool_call_correct'])} · must-cite recall {pct(s['must_cite_recall'])} ·
p50 latency {s['p50_latency_s']:.1f}s · refusal questions {pct(s['refusal_questions_correct'])}</p>
<h2>By category</h2><table><tr><th>category</th><th>n</th><th>correct</th></tr>{cats}</table>
<h2>Questions</h2><table><tr><th>id</th><th>cat</th><th>question</th><th>correct</th><th>tools</th><th>cit. prec.</th>
<th>s</th><th></th></tr>{body}</table></body></html>"""


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated ids or category names")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    qs = yaml.safe_load((HERE / "golden_questions.yaml").read_text())["questions"]
    if a.only:
        sel = set(a.only.split(","))
        qs = [q for q in qs if q["id"] in sel or q["category"] in sel]
    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(run_one, qs))
    s = summarise(rows)
    meta = {"run_at": started.isoformat(timespec="seconds"), "chat_model": llm.model("chat"),
            "judge_model": llm.model("judge"), "endpoint": llm.endpoint(), "questions": len(rows)}
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps({"summary": s, "meta": meta, "rows": rows}, indent=1, default=str))
    (HERE / "report.html").write_text(report(rows, s, meta))
    log.info("summary: %s", json.dumps({k: v for k, v in s.items() if k != "by_category"}, default=str))
    if a.upload:
        s3 = boto3.client("s3", region_name=settings.get()["region"])
        b = settings.get()["bucket_dq"]
        stamp = started.strftime("%Y%m%dT%H%M%S")
        for f, key in ((HERE / "report.html", f"eval/{stamp}/report.html"), (out / "results.json", f"eval/{stamp}/results.json"),
                       (HERE / "report.html", "eval/latest/report.html"), (out / "results.json", "eval/latest/results.json")):
            s3.upload_file(str(f), b, key)
        log.info("uploaded to s3://%s/eval/%s/", b, stamp)
    print(json.dumps({k: v for k, v in s.items()}, indent=1, default=str))


if __name__ == "__main__":
    main()
