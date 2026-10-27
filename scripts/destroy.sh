#!/usr/bin/env bash
# make destroy: typed confirmation -> empty buckets -> delete snapshots -> cdk destroy --all -> verify zero tagged.
set -euo pipefail
source "$(dirname "$0")/env.sh"
ACCT=$(python -c 'from jobs.common import settings; print(settings.get()["account_id"])')
read -r -p "Type 'destroy eqh-dq-assistant ${ACCT}' to delete EVERYTHING in the pilot: " ans
[ "$ans" = "destroy eqh-dq-assistant ${ACCT}" ] || { echo "aborted"; exit 1; }
for b in raw silver extracts glossary dq-results; do
  aws s3 rm "s3://eqh-dq-${ACCT}-${b}" --recursive --quiet || true
done
RDS="--endpoint-url https://rds.${AWS_REGION}.amazonaws.com"
for s in $(aws rds describe-db-cluster-snapshots $RDS --snapshot-type manual --query \
    "DBClusterSnapshots[?starts_with(DBClusterIdentifier,'eqh-dq')].DBClusterSnapshotIdentifier" --output text); do
  aws rds delete-db-cluster-snapshot $RDS --db-cluster-snapshot-identifier "$s" >/dev/null
done
for s in $(aws redshift-serverless list-snapshots --namespace-name eqh-dq --query 'snapshots[].snapshotName' --output text 2>/dev/null); do
  aws redshift-serverless delete-snapshot --snapshot-name "$s" >/dev/null
done
# Glue DQ rulesets and catalog tables are data created by datagen; remove them before the databases go
python - <<'PY'
import boto3
g = boto3.client("glue")
for r in g.list_data_quality_rulesets().get("Rulesets", []):
    if r["Name"].startswith("eqh_silver_"):
        g.delete_data_quality_ruleset(Name=r["Name"])
PY
TAG=$(cut -d= -f2 build/image_tag 2>/dev/null || echo latest)
(cd infra && cdk destroy --all --force -c image_tag="$TAG")
python3 scripts/security_selfcheck.py --leftovers
