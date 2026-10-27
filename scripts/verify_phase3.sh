#!/usr/bin/env bash
# Phase 3: migrations applied, pgvector present, least-privilege roles.
set -euo pipefail
source "$(dirname "$0")/env.sh"
python - <<'PY'
from jobs.common.db import MetaDB
db = MetaDB(role="assistant")
v = [r["version"] for r in db.query("select version from schema_migrations order by 1")]
print("migrations", v); assert v == ["001_reference_schema", "002_pilot_extensions"]
print("pgvector", db.one("select extversion from pg_extension where extname='vector'"))
for t in ("glossary_term", "asset_entitlement", "review_action"):
    db.one(f"select count(*) from {t}")
try:
    db.execute("delete from asset"); raise SystemExit("assistant role can delete!")
except Exception as e:
    print("assistant cannot delete:", type(e).__name__)
PY
echo "phase 3 OK"
