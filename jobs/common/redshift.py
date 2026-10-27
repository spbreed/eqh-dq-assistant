"""Redshift Data API helper (Serverless by default; provisioned behind RS_CLUSTER_ID)."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import boto3

from jobs.common import settings


class Redshift:
    def __init__(self, secret_arn: str | None = None, database: str | None = None):
        s = settings.get()
        self.client = boto3.client("redshift-data", region_name=s["region"])
        self.database = database or s["redshift_database"]
        self.workgroup = os.environ.get("RS_WORKGROUP", s["redshift_workgroup"])
        self.cluster = os.environ.get("RS_CLUSTER_ID")  # provisioned path (flag)
        # None -> IAM identity of the caller (Serverless maps it to an IAM:/IAMR: database user).
        self.secret_arn = secret_arn if secret_arn is not None else os.environ.get("RS_SECRET_ARN") or None

    def _target(self) -> dict:
        t = {"Database": self.database}
        t.update({"ClusterIdentifier": self.cluster} if self.cluster else {"WorkgroupName": self.workgroup})
        if self.secret_arn:
            t["SecretArn"] = self.secret_arn
        return t

    def _wait(self, stmt_id: str, timeout: float = 1800) -> dict:
        delay, start = 0.25, time.time()
        while True:
            d = self.client.describe_statement(Id=stmt_id)
            if d["Status"] == "FINISHED":
                return d
            if d["Status"] in ("FAILED", "ABORTED"):
                raise RuntimeError(f"Redshift statement failed: {d.get('Error')}")
            if time.time() - start > timeout:
                raise TimeoutError(stmt_id)
            time.sleep(delay)
            delay = min(delay * 1.6, 3)

    def query(self, sql: str, params: dict | None = None) -> list[dict]:
        args = self._target() | {"Sql": sql}
        if params:
            args["Parameters"] = [{"name": k, "value": str(v)} for k, v in params.items()]
        d = self._wait(self.client.execute_statement(**args)["Id"])
        if not d.get("HasResultSet"):
            return []
        return self._results(d["Id"])

    def _results(self, stmt_id: str) -> list[dict]:
        rows, token = [], None
        while True:
            page = self.client.get_statement_result(Id=stmt_id, **({"NextToken": token} if token else {}))
            names = [c["name"] for c in page["ColumnMetadata"]]
            for rec in page["Records"]:
                rows.append({n: (None if v.get("isNull") else next(iter(v.values()))) for n, v in zip(names, rec)})
            token = page.get("NextToken")
            if not token:
                return rows

    def batch(self, sqls: list[str], label: str | None = None) -> list[dict]:
        """Run statements in one session/transaction. Returns the last statement's rows (if any)."""
        if label:
            sqls = [f"set query_group to '{label}'"] + sqls
        out: list[dict] = []
        for i in range(0, len(sqls), 40):  # Data API limit: 40 statements per batch
            d = self._wait(self.client.batch_execute_statement(**self._target(), Sqls=sqls[i:i + 40])["Id"])
            last = d["SubStatements"][-1]
            out = self._results(last["Id"]) if last.get("HasResultSet") else []
        return out

    def run_many(self, sqls: list[str], workers: int = 6) -> None:
        """Independent statements in parallel (e.g. COPYs into different tables)."""
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(self.query, sqls))
