# Source me: non-secret session settings. Credentials come from the environment/profile only.
export AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$AWS_REGION" CDK_DEFAULT_REGION="$AWS_REGION"
export AWS_S3_US_EAST_1_REGIONAL_ENDPOINT=regional AWS_STS_REGIONAL_ENDPOINTS=regional
# us-east-1 RDS defaults to a region-less hostname in some SDKs; pin the regional one.
export AWS_ENDPOINT_URL_RDS="https://rds.${AWS_REGION}.amazonaws.com"
export EQH_PILOT_OWNER="${EQH_PILOT_OWNER:-karthik.ramamurthy@emergertech.com}"
[ -f /root/.ccr/ca-bundle.crt ] && export NODE_EXTRA_CA_CERTS=/root/.ccr/ca-bundle.crt
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -d "$REPO_ROOT/.venv" ] && . "$REPO_ROOT/.venv/bin/activate"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
