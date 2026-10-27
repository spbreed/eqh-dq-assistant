#!/usr/bin/env bash
# Run a pipeline Fargate task once, wait, and print its logs. Usage: scripts/run_task.sh <profiler|daily_sync|enrich|eval|llm_smoke> [cmd override...]
set -euo pipefail
source "$(dirname "$0")/env.sh"
NAME=$1; shift || true
out() { aws cloudformation describe-stacks --stack-name EqhDqPipeline --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
SUBNETS=$(out TaskSubnets); SG=$(out TaskSecurityGroup)
OVR='{}'
if [ $# -gt 0 ]; then OVR=$(python3 -c 'import json,sys; print(json.dumps({"containerOverrides":[{"name":sys.argv[1],"command":sys.argv[2:]}]}))' "$NAME" "$@"); fi
ARN=$(aws ecs run-task --cluster eqh-dq --launch-type FARGATE --task-definition "eqh-dq-${NAME//_/_}" \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SG}],assignPublicIp=DISABLED}" \
  --overrides "$OVR" --query 'tasks[0].taskArn' --output text)
echo "task $ARN" >&2
aws ecs wait tasks-stopped --cluster eqh-dq --tasks "$ARN" 2>/dev/null || aws ecs wait tasks-stopped --cluster eqh-dq --tasks "$ARN"
CODE=$(aws ecs describe-tasks --cluster eqh-dq --tasks "$ARN" --query 'tasks[0].containers[0].exitCode' --output text)
aws logs get-log-events --log-group-name /eqh-dq/pipeline --log-stream-name "${NAME}/${NAME}/${ARN##*/}" \
  --query 'events[].message' --output text 2>/dev/null | tr '\t' '\n' | tail -${TAIL:-60}
echo "exit=$CODE" >&2
[ "$CODE" = "0" ]
