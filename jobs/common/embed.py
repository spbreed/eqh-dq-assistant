"""Embeddings via Bedrock (Titan Text Embeddings v2 by default; see docs/DECISIONS.md)."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError

from jobs.common import settings


class EmbeddingUnavailable(RuntimeError):
    pass


def _client():
    return boto3.client("bedrock-runtime", region_name=settings.get()["region"])


def embed(text: str, client=None) -> list[float]:
    s = settings.get()
    client = client or _client()
    body = json.dumps({"inputText": text[:30000], "dimensions": s["embed_dim"], "normalize": True})
    for attempt in range(6):
        try:
            r = client.invoke_model(modelId=s["embed_model"], body=body)
            return json.loads(r["body"].read())["embedding"]
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "AccessDeniedException":
                raise EmbeddingUnavailable(e.response["Error"]["Message"][:160]) from e
            if code in ("ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException"):
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("embedding throttled after retries")


def embed_many(texts: list[str], workers: int = 8) -> list[list[float]]:
    client = _client()
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda t: embed(t, client), texts))


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
