#!/usr/bin/env bash
# Phase 7: security self-check + dashboard exists.
set -uo pipefail
source "$(dirname "$0")/env.sh"
aws cloudwatch get-dashboard --dashboard-name eqh-dq-assistant --query DashboardName --output text
python scripts/security_selfcheck.py
