#!/usr/bin/env bash
# make park: destroy every stack except EqhDqSecurity, keeping the latest backup (snapshots + backup bucket) and the
# CMK that encrypts it. Requires a backup taken in the last 12 hours. Bring it back with `make restore`.
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$(dirname "$0")/.."
ACCT=$(python -c 'from jobs.common import settings; print(settings.get()["account_id"])')
python scripts/backup_restore.py status
python - <<'PY'
import json, sys, boto3
from datetime import datetime, timezone, timedelta
from jobs.common import settings
s3 = boto3.client("s3"); b = f"eqh-dq-{settings.get()['account_id']}-backup"
m = json.loads(s3.get_object(Bucket=b, Key=json.loads(s3.get_object(Bucket=b, Key="LATEST.json")["Body"].read())["manifest"])["Body"].read())
age = datetime.now(timezone.utc) - datetime.fromisoformat(m["created_at"])
if age > timedelta(hours=12):
    sys.exit(f"latest backup {m['id']} is {age} old: run `make backup` first")
print(f"latest backup {m['id']} ({age} old) will be kept")
PY
read -r -p "Type 'park eqh-dq-assistant ${ACCT}' to destroy all stacks except EqhDqSecurity: " ans
[ "$ans" = "park eqh-dq-assistant ${ACCT}" ] || { echo "aborted"; exit 1; }
python - <<'PY'
import boto3
g = boto3.client("glue")
for r in g.list_data_quality_rulesets().get("Rulesets", []):
    if r["Name"].startswith("eqh_silver_"):
        g.delete_data_quality_ruleset(Name=r["Name"])
PY
TAG=$(cut -d= -f2 build/image_tag 2>/dev/null || echo latest)
(cd infra && cdk destroy EqhDqObservability EqhDqAssistant EqhDqPipeline EqhDqMetadataStore EqhDqDataPlatform \
   EqhDqImage EqhDqNetwork --force -c image_tag="$TAG")
python scripts/backup_restore.py purge-secrets
rm -f config/restore_state.json
python scripts/backup_restore.py status
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE \
  --query "StackSummaries[?starts_with(StackName,'EqhDq')].StackName" --output text
echo "parked: only EqhDqSecurity (CMK, roles, budget, trail, backup bucket) and the backup snapshots remain"
