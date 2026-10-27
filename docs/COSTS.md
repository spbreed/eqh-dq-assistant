# Costs — EQH DQ Assistant pilot (us-east-1)

On-demand list prices, us-east-1, October 2026. Check the pricing pages before relying on them. Cost Explorer
lags about 24 h; this account had $9.01 of month-to-date spend from other projects before the pilot was deployed
on 2026-10-27.

## Steady state (24×7, pilot running)
| Component | Sizing | Unit price | ≈ $/month |
|---|---|---|---|
| NAT gateway | 1 | $0.045/h + $0.045/GB | 33 + data |
| VPC interface endpoints | 9 endpoints × 1 AZ | $0.01/h each + $0.01/GB | 66 |
| Aurora PostgreSQL Serverless v2 | 0.5 ACU min, ≤ 4 ACU | $0.12/ACU-h; storage $0.10/GB-mo | 44 + ~1 |
| Application Load Balancer | 1 | $0.0225/h + LCU | 17 |
| ECS Fargate — assistant | 0.5 vCPU / 1 GB, 1 task | $0.04048/vCPU-h, $0.004445/GB-h | 18 |
| CloudFront + WAF | 1 distribution, 1 web ACL, 2 rules | WAF $5/ACL + $1/rule + $0.60/M req | 8 |
| Redshift Serverless | 8 RPU base; billed only while queries run | $0.375/RPU-h | 5–15 (daily jobs ≈ 10 min/day) |
| Fargate — daily jobs | profiler + sync + enrich ≈ 15 min/day | as above | 1 |
| Bedrock — gpt-oss-120b (chat, enrich, judge) | demo + eval traffic | $0.15/M input, $0.60/M output tokens | 1–5 |
| Bedrock — Titan Text Embeddings v2 | ~350 chunks + queries | $0.02/M tokens | < 1 |
| Bedrock Guardrails | ApplyGuardrail on input + output | $0.15/1k text units (content/topic policies) | 1–3 |
| KMS, Secrets Manager (≈ 12 secrets), CloudTrail data events, CloudWatch logs/dashboard, S3 (~250 MB), Step Functions, SNS | — | — | 10 |
| **Total** | | | **≈ $210–230** |

When GPT‑5.6 is enabled (docs/DECISIONS.md D‑01), Terra is $2.20/M input tokens (accepted offer), with higher output
pricing. At pilot volumes, chat + enrichment + eval is estimated at $10–30/month.

## One-time (already incurred during the build)
| Item | ≈ $ |
|---|---|
| Redshift Serverless for the 21-day simulation + re-profiling (≈ 3 RPU-hours of active compute × 8 RPU) | 10–20 |
| CodeBuild image builds (small, ~3 min each × 8) | < 1 |
| Glue Data Quality evaluations (7 rulesets × 2 runs, 2 workers) | 2–4 |
| Bedrock enrichment (124 assets) + evals | < 5 |

## Cost controls in place
- **Budget** `eqh-dq-assistant-monthly`: $300, email alerts at 50/80/100 % actual and 100 % forecast to RC@ and
  karthik.ramamurthy@emergertech.com.
- **Automatic limit**: at 100 % actual, AWS Budgets attaches `eqh-dq-budget-deny` to the pilot roles (harvest,
  assistant, eval, Redshift), which blocks Bedrock calls, ECS RunTask, Step Functions starts and Redshift Data API.
- **Redshift Serverless usage limit**: 300 RPU-hours/month, breach action *deactivate*; max capacity 16 RPU.
- **Aurora** capped at 4 ACU; `make pause` sets min 0 ACU with auto-pause after 15 minutes idle.
- **`make pause`**: also scales the assistant to 0 tasks and disables the scheduler → ≈ $110/month (NAT, endpoints,
  ALB, WAF remain). `make destroy` removes everything.

## Biggest levers if the pilot continues
1. Drop interface endpoints you don't need, or the NAT (if mantle PrivateLink is added): −$30–60.
2. Aurora auto-pause outside business hours: −$30.
3. Replace ALB + CloudFront with an internal ALB behind the customer's VPN/SSO: −$20.
