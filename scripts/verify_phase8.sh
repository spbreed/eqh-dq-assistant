#!/usr/bin/env bash
# Phase 8: demo package present.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in docs/DECISIONS.md docs/RUNBOOK.md docs/DEMO_SCRIPT.md docs/COSTS.md Resources.md eqh-dq-assistant.html; do
  [ -s "$f" ] && echo "PASS $f" || { echo "FAIL $f"; exit 1; }
done
