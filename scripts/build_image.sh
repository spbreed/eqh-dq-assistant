#!/usr/bin/env bash
# Build the service/jobs image in AWS CodeBuild (EqhDqImage stack) and print the image tag.
set -euo pipefail
source "$(dirname "$0")/env.sh"
out() { aws cloudformation describe-stacks --stack-name EqhDqImage --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
TAG=$(out ImageTag); REPO=eqh-dq-assistant; PROJECT=$(out BuildProject)
if aws ecr describe-images --repository-name "$REPO" --image-ids imageTag="$TAG" >/dev/null 2>&1; then
  echo "$TAG"; exit 0
fi
ID=$(aws codebuild start-build --project-name "$PROJECT" --query build.id --output text)
echo "building $ID" >&2
while true; do
  S=$(aws codebuild batch-get-builds --ids "$ID" --query 'builds[0].buildStatus' --output text)
  case "$S" in SUCCEEDED) break;; IN_PROGRESS) sleep 15;; *) echo "build $S" >&2; exit 1;; esac
done
echo "$TAG"
