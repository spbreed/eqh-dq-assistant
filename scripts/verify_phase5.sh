#!/usr/bin/env bash
# Phase 5: service healthy behind CloudFront, ALB not directly reachable, login redirects to Cognito.
set -euo pipefail
source "$(dirname "$0")/env.sh"
out() { aws cloudformation describe-stacks --stack-name EqhDqAssistant --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
URL=$(out Url)
[ "$(curl -s -o /dev/null -w '%{http_code}' $URL/health)" = "200" ]
loc=$(curl -s -o /dev/null -w '%{redirect_url}' $URL/login); echo "login -> ${loc%%\?*}"; echo "$loc" | grep -q amazoncognito.com
ALB=$(aws elbv2 describe-load-balancers --load-balancer-arns "$(out AlbArn)" --query 'LoadBalancers[0].DNSName' --output text)
code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$ALB/health" || true); echo "direct ALB -> $code (expect 000/403)"
[ "$code" != "200" ]
echo "phase 5 OK: $URL"
