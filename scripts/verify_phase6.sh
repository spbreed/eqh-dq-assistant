#!/usr/bin/env bash
# Phase 6: latest eval meets targets (run `make eval` first).
set -euo pipefail
source "$(dirname "$0")/env.sh"
B=$(python -c 'from jobs.common import settings; print(settings.get()["bucket_dq"])')
aws s3 cp "s3://$B/eval/latest/results.json" build/eval_latest.json --quiet
python - <<'PY'
import json
s = json.load(open("build/eval_latest.json"))["summary"]
for k, ok in s["targets_met"].items():
    print(("PASS " if ok else "MISS ") + f"{k}: {s[k]:.3f}")
PY
