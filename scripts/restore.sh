#!/usr/bin/env bash
# make restore: rebuild the pilot from the latest backup (after `make park`).
#   1 image  2 cdk deploy --all with Aurora created from the snapshot  3 Redshift snapshot, S3, Glue, build/ restored
#   4 DB roles + passwords  5 demo passwords  6 verify counts against the backup manifest  7 deck + Resources.md
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$(dirname "$0")/.."
python scripts/backup_restore.py status
python scripts/backup_restore.py purge-secrets
python - <<'PY'
import json, boto3
from jobs.common import settings
s3 = boto3.client("s3"); b = f"eqh-dq-{settings.get()['account_id']}-backup"
latest = json.loads(s3.get_object(Bucket=b, Key="LATEST.json")["Body"].read())
m = json.loads(s3.get_object(Bucket=b, Key=latest["manifest"])["Body"].read())
open("config/restore_state.json", "w").write(json.dumps(
    {"backup": m["id"], "aurora_snapshot": m["aurora_snapshot"], "redshift_snapshot": m["redshift_snapshot"]}, indent=1) + "\n")
print("restoring backup", m["id"])
PY
make image
TAG=$(cut -d= -f2 build/image_tag)
(cd infra && cdk deploy --all -c image_tag="$TAG" -c schedule_state=DISABLED --require-approval never)
python scripts/backup_restore.py restore-data
python -m metadata_store.migrate
python scripts/set_demo_passwords.py
python scripts/backup_restore.py verify
python scripts/gen_resources.py
python scripts/build_deck.py
URL=$(aws cloudformation describe-stacks --stack-name EqhDqAssistant --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text)
echo "restored. Assistant: $URL (commit config/restore_state.json, Resources.md and eqh-dq-assistant.html)"
