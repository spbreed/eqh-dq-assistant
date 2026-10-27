#!/usr/bin/env bash
# Phase 1: network + security: endpoints, CloudTrail, Bedrock invocation logging.
set -euo pipefail
source "$(dirname "$0")/env.sh"
VPC=$(aws cloudformation describe-stacks --stack-name EqhDqNetwork --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text)
n=$(aws ec2 describe-vpc-endpoints --filters Name=vpc-id,Values=$VPC --query 'length(VpcEndpoints[?State==`available`])')
echo "vpc endpoints available: $n"; [ "$n" -ge 10 ]
aws cloudtrail get-trail-status --name eqh-dq-assistant --query IsLogging | grep -q true
aws bedrock get-model-invocation-logging-configuration --query 'loggingConfig.cloudWatchConfig.logGroupName' --output text | grep -q eqh-dq
echo "phase 1 OK"
