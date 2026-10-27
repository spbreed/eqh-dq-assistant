"""Metadata store access through the RDS Data API (Aurora PostgreSQL Serverless v2).

SQL uses Data API named parameters (`:name`). Values are mapped to Data API types; dict/list values are sent as
JSON text (cast with ::jsonb in SQL), dates/datetimes with type hints. Vectors are sent as text ('[...]'::vector).
"""
from __future__ import annotations

import contextlib
import json
import time
from datetime import date, datetime
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from jobs.common import settings

RETRYABLE = ("DatabaseResumingException", "StatementTimeoutException", "ServiceUnavailableError",
             "ThrottlingException", "TooManyRequestsException")


def _param(name: str, v) -> dict:
    if v is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(v, bool):
        return {"name": name, "value": {"booleanValue": v}}
    if isinstance(v, int):
        return {"name": name, "value": {"longValue": v}}
    if isinstance(v, (float, Decimal)):
        return {"name": name, "value": {"doubleValue": float(v)}}
    if isinstance(v, datetime):
        return {"name": name, "typeHint": "TIMESTAMP",
                "value": {"stringValue": v.strftime("%Y-%m-%d %H:%M:%S.%f")}}
    if isinstance(v, date):
        return {"name": name, "typeHint": "DATE", "value": {"stringValue": v.isoformat()}}
    if isinstance(v, (dict, list, tuple)):
        return {"name": name, "value": {"stringValue": json.dumps(v, default=str)}}
    return {"name": name, "value": {"stringValue": str(v)}}


class MetaDB:
    def __init__(self, secret_arn: str | None = None, role: str = "harvest"):
        s = settings.get()
        self.client = boto3.client("rds-data", region_name=s["region"])
        self.cluster_arn = s["aurora_cluster_arn"]
        self.secret_arn = secret_arn or s[f"aurora_{role}_secret_arn"]
        self.database = s["aurora_database"]
        self._tx: str | None = None

    def _call(self, fn, **kw):
        kw |= {"resourceArn": self.cluster_arn, "secretArn": self.secret_arn, "database": self.database}
        if self._tx:
            kw["transactionId"] = self._tx
        for attempt in range(8):
            try:
                return fn(**kw)
            except ClientError as e:
                code = e.response["Error"]["Code"]
                msg = str(e)
                if code in RETRYABLE or "resuming" in msg.lower() or "Communications link failure" in msg:
                    time.sleep(min(2 ** attempt, 20))
                    continue
                raise
        raise RuntimeError("Data API retries exhausted")

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        r = self._call(self.client.execute_statement, sql=sql, formatRecordsAs="JSON",
                       parameters=[_param(k, v) for k, v in (params or {}).items()])
        return json.loads(r["formattedRecords"]) if r.get("formattedRecords") else []

    def one(self, sql: str, params: dict | None = None):
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def execute(self, sql: str, params: dict | None = None) -> int:
        r = self._call(self.client.execute_statement, sql=sql,
                       parameters=[_param(k, v) for k, v in (params or {}).items()])
        return r.get("numberOfRecordsUpdated", 0)

    def executemany(self, sql: str, rows: list[dict], chunk: int = 400) -> int:
        n = 0
        for i in range(0, len(rows), chunk):
            sets = [[_param(k, v) for k, v in r.items()] for r in rows[i:i + chunk]]
            self._call(self.client.batch_execute_statement, sql=sql, parameterSets=sets)
            n += len(sets)
        return n

    def script(self, sql_text: str) -> None:
        """Run a migration file statement by statement (no dollar-quoted bodies with ';' inside)."""
        for stmt in split_sql(sql_text):
            self.execute(stmt)

    @contextlib.contextmanager
    def transaction(self):
        if self._tx:  # nested: join the outer transaction
            yield self
            return
        tx = self.client.begin_transaction(resourceArn=self.cluster_arn, secretArn=self.secret_arn,
                                           database=self.database)["transactionId"]
        self._tx = tx
        try:
            yield self
            self._tx = None
            self.client.commit_transaction(resourceArn=self.cluster_arn, secretArn=self.secret_arn, transactionId=tx)
        except Exception:
            self._tx = None
            self.client.rollback_transaction(resourceArn=self.cluster_arn, secretArn=self.secret_arn, transactionId=tx)
            raise


def split_sql(text: str) -> list[str]:
    out, buf, in_dollar = [], [], False
    for line in text.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        if "$$" in line:
            in_dollar = (line.count("$$") % 2 == 1) != in_dollar
        buf.append(line)
        if stripped.endswith(";") and not in_dollar:
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt:
                out.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
