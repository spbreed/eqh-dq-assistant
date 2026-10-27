#!/usr/bin/env bash
# make pause / make resume: cost controls without redeploying.
set -euo pipefail
source "$(dirname "$0")/env.sh"
RDS="--endpoint-url https://rds.${AWS_REGION}.amazonaws.com"
case "${1:-}" in
  pause)
    aws rds modify-db-cluster $RDS --db-cluster-identifier eqh-dq-metadata --apply-immediately \
      --serverless-v2-scaling-configuration MinCapacity=0,MaxCapacity=4,SecondsUntilAutoPause=900 >/dev/null
    aws ecs update-service --cluster eqh-dq --service eqh-dq-assistant --desired-count 0 >/dev/null
    aws scheduler get-schedule --name eqh-dq-daily >/dev/null 2>&1 && python3 - <<'PY'
import boto3
s = boto3.client("scheduler"); g = s.get_schedule(Name="eqh-dq-daily")
keep = {k: g[k] for k in ("Name","ScheduleExpression","FlexibleTimeWindow","Target","ScheduleExpressionTimezone") if k in g}
s.update_schedule(**keep, State="DISABLED")
PY
    aws redshift-serverless update-workgroup --workgroup-name eqh-dq --max-capacity 8 >/dev/null || true
    echo "paused: Aurora auto-pauses after 15 min idle, assistant scaled to 0, scheduler disabled, Redshift max 8 RPU" ;;
  resume)
    aws rds modify-db-cluster $RDS --db-cluster-identifier eqh-dq-metadata --apply-immediately \
      --serverless-v2-scaling-configuration MinCapacity=0.5,MaxCapacity=4 >/dev/null
    aws ecs update-service --cluster eqh-dq --service eqh-dq-assistant --desired-count 1 >/dev/null
    aws redshift-serverless update-workgroup --workgroup-name eqh-dq --max-capacity 16 >/dev/null || true
    echo "resumed (scheduler stays as deployed: SCHEDULE=ENABLED make deploy STACK=EqhDqPipeline to enable it)" ;;
  *) echo "usage: $0 pause|resume"; exit 2 ;;
esac
