#!/usr/bin/env bash
# Phase 0: tools, identity matches config, CDK bootstrapped, Bedrock models reachable, budget present.
set -euo pipefail
source "$(dirname "$0")/env.sh"
for t in aws cdk python docker; do command -v $t >/dev/null || { echo "missing $t"; exit 1; }; done
want=$(python -c 'from jobs.common import settings; print(settings.get()["account_id"])')
got=$(aws sts get-caller-identity --query Account --output text)
[ "$want" = "$got" ] || { echo "identity $got != config $want — STOP"; exit 1; }
aws cloudformation describe-stacks --stack-name CDKToolkit --query 'Stacks[0].StackStatus' --output text
aws bedrock list-foundation-models --query "modelSummaries[?modelId=='openai.gpt-5.6-terra'].modelId" --output text
aws budgets describe-budget --account-id "$got" --budget-name eqh-dq-assistant-monthly --query 'Budget.BudgetLimit' --output text
python - <<'PY'
from jobs.common import embed
print("titan embedding dim", len(embed.embed("PMPM by practice")))
PY
echo "phase 0 OK (LLM smoke runs in Fargate: make smoke)"
