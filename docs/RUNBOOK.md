# Runbook — EQH DQ Assistant pilot

Account `761705103792`, region `us-east-1`. Everything is driven from the repo root with `make` (run `make help`).
Every command sources `scripts/env.sh` (region, regional endpoints, `.venv`, `PYTHONPATH`).

## 0. Prerequisites (human, SPEC Part A)
- AWS CLI v2, Node 22 + `npm i -g aws-cdk@2`, Python 3.12 + `uv`, Docker (only for local experiments — images are
  built in CodeBuild). `make venv`.
- Credentials: `aws sso login --profile eqh-pilot` and `export AWS_PROFILE=eqh-pilot` (or the cloud session's
  short-lived env vars). If any command fails with an expired-token error, **log in again** — never paste keys.
- Bedrock: Titan Text Embeddings v2 and `openai.gpt-oss-120b` must be enabled. GPT‑5.6 Terra/Luna/Sol agreements are
  accepted but AWS has not enabled them for this account yet (docs/DECISIONS.md D‑01).

## 1. Deploy (🛑 each deploy is a checkpoint)
```bash
make bootstrap                 # identity check + cdk bootstrap (+ titan smoke)
make image                     # EqhDqImage stack + CodeBuild image build -> build/image_tag
make deploy-all                # all stacks; scheduler stays DISABLED unless SCHEDULE=ENABLED
make smoke                     # LLM smoke test in Fargate (bedrock-mantle)
```
Stacks: `EqhDqSecurity` (KMS, roles, budget + deny action, CloudTrail, Bedrock logging) → `EqhDqNetwork` →
`EqhDqImage` → `EqhDqDataPlatform` (S3, Glue DBs, Redshift Serverless + RPU limit) → `EqhDqMetadataStore` (Aurora +
Data API) → `EqhDqPipeline` (ECS tasks, Step Functions, Scheduler, SNS) → `EqhDqAssistant` (Fargate, ALB, CloudFront,
WAF, Cognito, Guardrail) → `EqhDqObservability` (dashboard).

## 2. Seed and simulate
```bash
make seed                      # migrations, generate data (deterministic), day-0 load + 30 days usage history + sync
make simulate                  # days 1..21 (~3 min/day), redetect, enrichment in Fargate
make verify                    # verify_phase0..8
make test-aws                  # unit + PHI-guard integration tests
```
Resume after an interruption: `python -m datagen.simulate days <next> 21` (state in `build/sim_state.json`). If a day
was loaded but its chain did not run: `python -m datagen.simulate chain <day>`.

## 3. Daily jobs
| Job | How | Notes |
|---|---|---|
| profiler | `scripts/run_task.sh profiler` or `python -m jobs.profiler.profile --as-of YYYY-MM-DD` | aggregates only → `s3://…-dq-results/profile/dt=…/` |
| daily_sync | `scripts/run_task.sh daily_sync` or `python -m jobs.daily_sync.sync --as-of …` | `--redetect [--reload-profiles]` replays issue detection |
| enrich | `make enrich` (Fargate) | needs bedrock-mantle → run in AWS |
| full chain | Step Functions `eqh-dq-daily` (manual "Start execution", or the 06:00 America/Phoenix schedule) | failures → SNS `eqh-dq-pipeline-alerts` (email) |
| Glue DQ | `python -c "from datagen import glue_dq; ..."` / Glue console | DQDL rulesets `eqh_silver_*` |

## 4. Assistant
- URL: `aws cloudformation describe-stacks --stack-name EqhDqAssistant --query "Stacks[0].Outputs[?OutputKey=='Url'].OutputValue" --output text`
- Demo users: `demo-analyst`, `demo-steward`, `demo-actuary`, `demo-bh-analyst`. Passwords live in Secrets Manager
  `eqh-dq/cognito/<user>` (open the secret in the console → *Retrieve secret value*). Add real users in the Cognito
  console (user pool `eqh-dq-assistant`) and put them in groups `analyst` / `steward` / `actuarial` / `restricted_bh`.
- Logs: CloudWatch `/eqh-dq/assistant`; dashboard `eqh-dq-assistant`.
- Redeploy after code changes: `make image && make deploy STACK=EqhDqAssistant`.

## 5. Evaluation
`make eval` runs the 74 golden questions in Fargate (same code, role and models as the service), uploads
`s3://…-dq-results/eval/<timestamp>/` and downloads `eval/report.html`. `scripts/verify_phase6.sh` checks targets.

## 6. Live demo day
`make simulate-day N=22 INJECT=D07` derives day 22 from a normal day, drops ~70% of PAYER_LA1 claims, loads it and
runs usage → profiler → daily_sync (~3 min). Supported injections: D01 D02 D03 D06 D07 D14.

## 7. Cost controls
- `make pause`: Aurora min 0 ACU (auto-pause after 15 min), assistant service to 0 tasks, scheduler disabled,
  Redshift max 8 RPU. `make resume` reverses it.
- Budget `eqh-dq-assistant-monthly` ($300): alerts to RC@ and karthik.ramamurthy@emergertech.com at 50/80/100 %
  actual and 100 % forecast; at 100 % AWS Budgets automatically attaches `eqh-dq-budget-deny` to the pilot roles
  (stops Bedrock, ECS RunTask, Step Functions, Redshift Data). To lift it: detach the policy from the roles in IAM
  (or reset the action in the Budgets console) after raising the budget.
- Redshift Serverless usage limit: 300 RPU-hours/month → workgroup deactivated.

## 8. Failures
| Symptom | Fix |
|---|---|
| `ExpiredToken` / `InvalidClientTokenId` | `aws sso login --profile eqh-pilot` (human) |
| Data API `DatabaseResumingException` | Aurora resuming from pause; `db.py` retries automatically |
| Redshift COPY hangs | Redshift SG egress / S3 gateway endpoint (see DataPlatformStack) |
| ECS task `ResourceInitializationError … KMS` | execution role needs `kms:Decrypt` via Secrets Manager (AssistantStack) |
| `403 … not available for this account` from Bedrock | model not enabled for the account (D‑01); check `config/pilot.yaml › models` |
| Glue DQ `COLUMN_ALREADY_EXISTS` | silver files must not contain a column named like the partition key (D‑13) |
| Step Functions failure email | open the execution, then the ECS task logs in `/eqh-dq/pipeline` |

## 9. Teardown
`make destroy` → typed confirmation → empties buckets → deletes snapshots and Glue DQ rulesets → `cdk destroy --all`
→ lists anything still tagged `project=eqh-dq-assistant`.

Human follow-up after the pilot:
1. Rotate or delete the IAM-user access key used by the cloud session (and any other key older than 30 days).
2. Delete the `CDKToolkit` stack if nothing else in the account uses CDK.
3. Cancel the GPT‑5.6 Marketplace agreements if they will not be used.
4. If the account is pilot-only: close it or move it to a suspended OU.
