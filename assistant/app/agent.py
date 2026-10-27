"""Tool-using chat agent: GPT-5.6 Terra via the Responses API, Bedrock Guardrails on input and output."""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable

import boto3

from assistant.app import tools as T
from jobs.common import llm, settings

log = logging.getLogger("agent")
PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "system.md").read_text()
MAX_TURNS = 8
KEY_RE = re.compile(r"`((?:redshift|glue|extract|datashare)://[a-z0-9_./-]+)`")
REFUSAL = ("I can't make changes — this assistant is read-only. It never modifies data, schemas, catalog entries or "
           "pipelines. I can explain the issue, show its downstream impact and who consumes the affected data, so the "
           "owning team can fix it through their normal change process.")
WRITE_INTENT = re.compile(r"\b(delete|drop|truncate|update|insert|remove|dedup(e|licate)?|fix|alter|rename|reload|"
                          r"modify|overwrite|purge|grant|revoke)\b.*\b(data|row|rows|record|records|claim|claims|table|"
                          r"schema|column|comment|catalog|pipeline|job|duplicates?|member|members|view)\b", re.I)


def _guardrail(text: str, source: str) -> tuple[bool, str]:
    gid = os.environ.get("GUARDRAIL_ID")
    if not gid:
        return False, ""
    rt = boto3.client("bedrock-runtime", region_name=settings.get()["region"])
    try:
        r = rt.apply_guardrail(guardrailIdentifier=gid, guardrailVersion=os.environ.get("GUARDRAIL_VERSION", "DRAFT"),
                               source=source, content=[{"text": {"text": text[:20000]}}])
    except Exception:  # noqa: BLE001 - guardrail outage must not take the assistant down; logged for alarms
        log.exception("guardrail call failed")
        return False, ""
    if r.get("action") == "GUARDRAIL_INTERVENED":
        topics = [t["name"] for a in r.get("assessments", []) for t in a.get("topicPolicy", {}).get("topics", [])]
        out = (r.get("outputs") or [{}])[0].get("text", "")
        log.info("guardrail intervened (%s): %s", source, topics)
        return True, out if source == "OUTPUT" else ("topics:" + ",".join(topics))
    return False, ""


def _summary(name: str, result: dict) -> str:
    if "error" in result:
        return result["error"]
    for k in ("results", "issues", "changes", "unused_marts_and_views", "terms", "impact_ranked", "series"):
        if k in result:
            return f"{len(result[k])} {k}"
    return "ok"


def answer(question: str, groups: list[str], history: list[dict] | None = None,
           on_event: Callable[[dict], None] | None = None, user: str = "anonymous") -> dict:
    emit = on_event or (lambda e: None)
    t0 = time.time()
    ctx = T.Ctx(groups)
    calls: list[dict] = []
    seen_keys: set[str] = set()

    blocked, info = _guardrail(question, "INPUT")
    if (blocked and "topics:" in info) or WRITE_INTENT.search(question):
        emit({"type": "delta", "text": REFUSAL})
        res = {"answer": REFUSAL, "refused": True, "tool_calls": [], "citations": [], "tool_result_keys": [],
               "latency_s": round(time.time() - t0, 2)}
        emit({"type": "done", **res})
        return res

    instructions = PROMPT.format(as_of=ctx.as_of.date().isoformat(), groups=", ".join(sorted(groups)) or "analyst")
    items: list = list(history or []) + [{"role": "user", "content": question}]
    text = ""
    for _turn in range(MAX_TURNS):
        stream = llm.client(llm.model("chat")).responses.create(
            model=llm.model("chat"), instructions=instructions, input=items, tools=T.tool_specs(),
            reasoning={"effort": "low"}, max_output_tokens=3000, stream=True, store=False,
            include=["reasoning.encrypted_content"])
        final = None
        for ev in stream:
            if ev.type == "response.output_text.delta":
                emit({"type": "delta", "text": ev.delta})
            elif ev.type == "response.completed":
                final = ev.response
            elif ev.type in ("response.failed", "error"):
                raise RuntimeError(f"model error: {getattr(ev, 'response', ev)}")
        fcalls = [o for o in final.output if o.type == "function_call"]
        if not fcalls:
            text = final.output_text or ""
            break
        for o in final.output:
            items.append(o.model_dump(exclude_none=True))
        for fc in fcalls:
            args = json.loads(fc.arguments or "{}")
            emit({"type": "tool_call", "name": fc.name, "args": args})
            ts = time.time()
            result = T.call(ctx, fc.name, args)
            calls.append({"name": fc.name, "args": args, "ms": int((time.time() - ts) * 1000),
                          "summary": _summary(fc.name, result)})
            emit({"type": "tool_result", "name": fc.name, "summary": _summary(fc.name, result)})
            if fc.name == "get_dq_trend" and result.get("series"):
                emit({"type": "trend", "data": result})
            out_json = json.dumps(result, default=str)
            seen_keys |= set(re.findall(r"(?:redshift|glue|extract|datashare)://[a-z0-9_./-]+", out_json))
            items.append({"type": "function_call_output", "call_id": fc.call_id, "output": out_json[:60000]})
    else:
        text = text or "I couldn't complete this within the tool-call budget; please narrow the question."

    blocked, masked = _guardrail(text, "OUTPUT")
    if blocked and masked:
        text = masked
    cites = sorted(set(KEY_RE.findall(text)))
    res = {"answer": text, "refused": False, "tool_calls": calls, "citations": cites,
           "tool_result_keys": sorted(seen_keys),
           "latency_s": round(time.time() - t0, 2), "as_of": ctx.as_of.date().isoformat()}
    emit({"type": "done", **{k: v for k, v in res.items() if k != "answer"}})
    log.info(json.dumps({"event": "answer", "user": user, "tools": [c["name"] for c in calls],
                         "latency_s": res["latency_s"], "n_citations": len(cites)}))
    return res
