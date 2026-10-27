"""OpenAI models on Amazon Bedrock through the OpenAI Python SDK (Responses API).

Endpoint: bedrock-runtime's OpenAI-compatible route (`https://bedrock-runtime.<region>.amazonaws.com/openai/v1`)
by default, or bedrock-mantle (`https://bedrock-mantle.<region>.api.aws/v1`) with LLM_ENDPOINT=mantle.
Auth: SigV4 (service `bedrock`) with the caller's AWS credentials — no Bedrock API keys. See docs/DECISIONS.md.

Only metadata and aggregate metrics may be sent to a model (PHI guard).
"""
from __future__ import annotations

import json
import logging
import os
import time

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from openai import APIStatusError, OpenAI

from jobs.common import settings

log = logging.getLogger("llm")
SIGNED_HEADERS = ("host", "content-type", "x-amz-date", "x-amz-security-token")


class _SigV4(httpx.Auth):
    requires_request_body = True

    def __init__(self, region: str, service: str = "bedrock"):
        self.session = boto3.Session()
        self.region, self.service = region, service

    def auth_flow(self, request: httpx.Request):
        creds = self.session.get_credentials()
        if creds is None:  # a signing proxy (cloud session) adds auth itself
            yield request
            return
        headers = {k: v for k, v in request.headers.items() if k.lower() in ("host", "content-type")}
        aws = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=headers)
        SigV4Auth(creds.get_frozen_credentials(), self.service, self.region).add_auth(aws)
        request.headers.pop("authorization", None)
        for k, v in aws.headers.items():
            request.headers[k] = v
        yield request


def endpoint() -> str:
    """mantle inside AWS (task roles sign SigV4); runtime route where a signing proxy is in front."""
    default = "mantle" if os.environ.get("ECS_CONTAINER_METADATA_URI_V4") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") \
        else "runtime"
    return os.environ.get("LLM_ENDPOINT", default)


def base_url(model_id: str | None = None) -> str:
    """On mantle, GPT-5.x/6 are served under /openai/v1 and gpt-oss under /v1."""
    s = settings.get()
    if endpoint() == "mantle":
        if os.environ.get("MANTLE_BASE_URL"):
            return os.environ["MANTLE_BASE_URL"]
        frontier = bool(model_id) and model_id.startswith(("openai.gpt-5", "openai.gpt-6"))
        return s["models"]["mantle_openai_base_url" if frontier else "mantle_base_url"]
    return s["models"]["runtime_openai_base_url"]


_clients: dict[str, OpenAI] = {}


def client(model_id: str | None = None) -> OpenAI:
    url = base_url(model_id or model("chat"))
    if url not in _clients:
        region = settings.get()["region"]
        _clients[url] = OpenAI(api_key="sigv4", base_url=url, max_retries=0, timeout=120,
                               http_client=httpx.Client(auth=_SigV4(region), timeout=120))
    return _clients[url]


def model(role: str) -> str:
    """role: chat | enrich | judge -> model id from config (env override MODEL_<ROLE>)."""
    return os.environ.get(f"MODEL_{role.upper()}", settings.get()["models"][role])


def respond(role: str, input, *, instructions: str | None = None, tools: list | None = None,
            json_schema: dict | None = None, max_output_tokens: int = 2000, reasoning_effort: str | None = "low"):
    """One Responses API call with retries. Returns the SDK Response object."""
    kw = {"model": model(role), "input": input, "max_output_tokens": max_output_tokens}
    if instructions:
        kw["instructions"] = instructions
    if tools:
        kw["tools"] = tools
    if json_schema:
        kw["text"] = {"format": {"type": "json_schema", "name": json_schema.get("title", "output"),
                                 "schema": json_schema, "strict": True}}
    if reasoning_effort:
        kw["reasoning"] = {"effort": reasoning_effort}
    for attempt in range(6):
        try:
            return client(kw["model"]).responses.create(**kw)
        except APIStatusError as e:
            if e.status_code in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(min(2 ** attempt, 30))
                continue
            raise


def text_of(resp) -> str:
    return getattr(resp, "output_text", None) or ""


def json_of(resp) -> dict:
    t = text_of(resp).strip()
    if t.startswith("```"):
        t = t.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t)


def smoke() -> dict:
    """Phase 0 smoke test: each configured model answers through the Responses API."""
    out = {}
    for role in ("chat", "enrich", "judge"):
        try:
            r = respond(role, "Reply with exactly: pong", max_output_tokens=200)
            out[role] = {"model": model(role), "ok": "pong" in text_of(r).lower(), "text": text_of(r)[:40]}
        except Exception as e:  # noqa: BLE001
            out[role] = {"model": model(role), "ok": False, "error": str(e)[:200]}
    return out


if __name__ == "__main__":
    print(json.dumps(smoke(), indent=1))
