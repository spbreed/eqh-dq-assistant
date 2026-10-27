"""Apply metadata-store migrations through the RDS Data API and (re)create least-privilege DB roles.

Usage: python -m metadata_store.migrate
Role passwords are taken from their Secrets Manager secrets inside this process and never printed.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import boto3

from jobs.common import settings
from jobs.common.db import MetaDB

log = logging.getLogger("migrate")
MIGRATIONS = Path(__file__).parent / "migrations"

GRANTS = {
    "eqh_harvest": [
        "GRANT USAGE ON SCHEMA public TO eqh_harvest",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO eqh_harvest",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO eqh_harvest",
    ],
    "eqh_assistant": [
        "GRANT USAGE ON SCHEMA public TO eqh_assistant",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO eqh_assistant",
        # steward review is the only write path: review fields + audit row + re-embedding of that asset
        "GRANT UPDATE (steward_description, ai_description_status, doc_hash, updated_at) ON asset TO eqh_assistant",
        "GRANT UPDATE (steward_description) ON asset_column TO eqh_assistant",
        "GRANT INSERT ON review_action TO eqh_assistant",
        "GRANT USAGE, SELECT ON SEQUENCE review_action_id_seq TO eqh_assistant",
        "GRANT INSERT, DELETE ON embedding TO eqh_assistant",
        "GRANT UPDATE (status, updated_at) ON enrichment_task TO eqh_assistant",
    ],
}


def apply_migrations(db: MetaDB) -> list[str]:
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, "
               "applied_at timestamptz NOT NULL DEFAULT now())")
    done = {r["version"] for r in db.query("SELECT version FROM schema_migrations")}
    dim = settings.get()["embed_dim"]
    applied = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.stem in done:
            continue
        text = f.read_text()
        if "{{embed_dim_alter}}" in text:
            cur = db.one("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'embedding'::regclass "
                         "AND attname = 'embedding'")
            alter = "" if cur == dim else (
                "\nDROP INDEX IF EXISTS embedding_hnsw_idx;\nDELETE FROM embedding;\n"
                f"ALTER TABLE embedding ALTER COLUMN embedding TYPE vector({dim});\n"
                "CREATE INDEX embedding_hnsw_idx ON embedding USING hnsw (embedding vector_cosine_ops) "
                "WITH (m = 16, ef_construction = 64);\n")
            text = text.replace("-- {{embed_dim_alter}}", alter)
        log.info("applying %s", f.name)
        with db.transaction():
            db.script(text)
            db.execute("INSERT INTO schema_migrations(version) VALUES (:v)", {"v": f.stem})
        applied.append(f.stem)
    return applied


def ensure_roles(db: MetaDB) -> None:
    sm = boto3.client("secretsmanager", region_name=settings.get()["region"])
    for role, key in (("eqh_harvest", "aurora_harvest_secret_arn"), ("eqh_assistant", "aurora_assistant_secret_arn")):
        pwd = json.loads(sm.get_secret_value(SecretId=settings.get()[key])["SecretString"])["password"]
        exists = db.one("SELECT count(*) FROM pg_roles WHERE rolname = :r", {"r": role})
        verb = "ALTER" if exists else "CREATE"
        # identifiers/literals can't be bound parameters in DDL; the password charset excludes quotes
        db.execute(f"{verb} ROLE {role} WITH LOGIN PASSWORD '{pwd}'")
        for g in GRANTS[role]:
            db.execute(g)
        log.info("role %s ready", role)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = MetaDB(role="admin")
    log.info("applied: %s", apply_migrations(db) or "nothing new")
    ensure_roles(db)


if __name__ == "__main__":
    main()
