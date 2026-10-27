# SPEC — AI Data Quality Assistant for Equality Health (pilot) on a new AWS account

> **How to use this file.**
> 1. A human completes **Part A** (AWS account, credentials, Claude Code environment). This takes about 45 minutes.
> 2. Put this folder at the root of an empty git repo and open Claude Code there.
> 3. First prompt: *"Read SPEC.md end to end. Create CLAUDE.md summarising the ground rules in §B2, then
>    implement Phase 0. Stop at every 🛑 checkpoint and wait for me."* Then continue phase by phase.
>
> `reference/schema.sql` and `reference/daily_sync.py` are a working starting point for the metadata store
> and the daily sync. Reuse them, but apply the fixes listed in Phase 4.

---

# PART A — Human setup: AWS account, credentials and Claude Code environment

Complete this before handing the repo to Claude Code. **Never paste access keys, secret keys or session tokens into
the Claude Code chat, into the repo, or into SPEC/CLAUDE.md.** Claude Code should only ever see a *profile name*
(or, in cloud sessions, short-lived environment variables injected by the environment).

## A1. Create the AWS account
Choose one of these options:
- **Option 1 (preferred): a member account in an existing AWS Organization** (for example the Emergere sandbox org).
  In the management account: *AWS Organizations → AWS accounts → Add an AWS account → Create*.
  - Name: `eqh-dq-assistant-pilot`; email: a dedicated alias such as `aws+eqh-pilot@yourdomain.com`.
  - Put it in a `Sandbox` OU with an SCP that restricts regions to `us-east-1` (and `us-east-2` if needed).
- **Option 2: a standalone account.** Sign up at https://aws.amazon.com with a dedicated email alias and a company card.

## A2. Secure the root user (do this immediately)
1. Sign in as root, then go to *Security credentials* and **assign MFA** (passkey or authenticator app).
2. Confirm there are **no root access keys**, and don't create any.
3. *Account → Alternate contacts*: set billing, operations and security contacts.
4. *Account → IAM user and role access to Billing information*: **Activate** it, so admins can see costs.
5. After this, stop using root.

## A3. Create a human admin identity with IAM Identity Center (recommended: short-lived credentials)
1. Console (in `us-east-1`): *IAM Identity Center → Enable*. (In a standalone account, this creates an AWS
   Organization with this account as the management account. That's fine for a pilot.)
2. *Users → Add user*: your name and email. Accept the invite email, set a password and **register MFA**.
3. *Permission sets → Create*: predefined **AdministratorAccess**, session duration **4 hours**,
   name `PilotAdmin`.
   - For tighter control later, create a `PilotDeployer` permission set scoped to the services listed in §B3,
     plus `iam:*` limited to roles and policies prefixed `eqh-`. Admin is acceptable for a throwaway sandbox.
4. *AWS accounts → select the pilot account → Assign users or groups*: your user + `PilotAdmin`.
5. Copy the **AWS access portal URL** from the Identity Center dashboard (it looks like `https://d-xxxxxxxxxx.awsapps.com/start`).

## A4. Configure the AWS CLI profile on your machine
```bash
# install AWS CLI v2 (https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), then:
aws configure sso
#   SSO session name:        eqh-pilot
#   SSO start URL:           https://d-xxxxxxxxxx.awsapps.com/start
#   SSO region:              us-east-1
#   SSO registration scopes: sso:account:access   (default)
#   → browser opens, approve → choose the pilot account and the PilotAdmin role
#   CLI default region:      us-east-1
#   CLI output format:       json
#   Profile name:            eqh-pilot

aws sso login --profile eqh-pilot
aws sts get-caller-identity --profile eqh-pilot      # must show the pilot account id
```
This writes `~/.aws/config` with an `[sso-session eqh-pilot]` block and a `[profile eqh-pilot]` block. **No long-lived
secret lands on disk**, and the CLI caches tokens that expire after the session duration. Re-run
`aws sso login --profile eqh-pilot` when they expire.

### A4-alt. Only if SSO isn't possible: an IAM user with access keys (less safe)
1. *IAM → Users → Create user* `eqh-claude-deployer` (no console access). Attach `AdministratorAccess` for the pilot,
   or the scoped deployer policy.
2. *Security credentials → Create access key → use case "Command Line Interface"*. Download it once.
3. Store the key **only** in the AWS shared credentials file:
   ```bash
   aws configure --profile eqh-pilot      # paste key id + secret here, region us-east-1, output json
   chmod 600 ~/.aws/credentials
   ```
4. Set a calendar reminder: **deactivate and delete the key at the end of the pilot**, or rotate it every 30 days.
5. Never put the key in `.env`, in `config/pilot.yaml`, in shell history, or in Claude Code settings.

## A5. Wire the profile into Claude Code

### Local Claude Code (CLI or desktop) — recommended
Create `.claude/settings.local.json` in the repo. This file is personal and git-ignored; add it to `.gitignore` if it isn't already:
```json
{
  "env": {
    "AWS_PROFILE": "eqh-pilot",
    "AWS_REGION": "us-east-1",
    "AWS_DEFAULT_REGION": "us-east-1",
    "CDK_DEFAULT_REGION": "us-east-1",
    "EQH_PILOT_OWNER": "your.name@yourdomain.com"
  },
  "permissions": {
    "deny": [
      "Read(~/.aws/credentials)",
      "Read(~/.aws/sso/cache/**)",
      "Read(~/.aws/cli/cache/**)",
      "Bash(aws configure export-credentials:*)",
      "Bash(aws iam create-access-key:*)",
      "Bash(aws organizations:*)"
    ],
    "ask": [
      "Bash(cdk deploy:*)",
      "Bash(cdk destroy:*)",
      "Bash(aws * delete-*:*)",
      "Bash(make destroy:*)"
    ]
  }
}
```
- Claude Code passes `env` to every command it runs, so `aws`, `cdk` and boto3 all use the `eqh-pilot` profile automatically.
- The `deny` rules stop the agent from reading cached tokens or minting new keys. The `ask` rules make deploys and deletes
  require your approval, in addition to the 🛑 checkpoints.
- Run `aws sso login --profile eqh-pilot` in your own terminal **before** starting a session. If a command fails with
  an expired-token error, log in again; don't ask Claude to do it. (If your Claude Code version supports an
  `awsAuthRefresh` setting, you can set it to `aws sso login --profile eqh-pilot`. Check the current Claude Code docs.)
- Alternatively, `export AWS_PROFILE=eqh-pilot AWS_REGION=us-east-1` in the shell before running `claude`.
  The settings file is more reliable because it travels with the repo folder.

### Claude Code in a cloud or remote environment (no browser for SSO)
A remote container can't complete the SSO browser flow, so inject **short-lived** credentials:
```bash
# on your laptop, after aws sso login:
aws configure export-credentials --profile eqh-pilot --format env-no-export
# → AWS_ACCESS_KEY_ID=..., AWS_SECRET_ACCESS_KEY=..., AWS_SESSION_TOKEN=..., AWS_CREDENTIAL_EXPIRATION=...
```
Put those values, plus `AWS_REGION=us-east-1`, into the **environment's environment-variables / secrets settings**
of the cloud session, not into chat or the repo. They expire with your SSO session (≤ 4 h), so refresh them when needed.
Never use IAM-user long-lived keys in a shared cloud environment.

### Project-level files (committed)
- `.gitignore` must include: `.env`, `.env.*`, `.claude/settings.local.json`, `cdk.out/`, `**/__pycache__/`, `*.pem`, `credentials`.
- `config/pilot.yaml` contains only non-secret settings (account id, region, owner, budget, model ids, sizes).
- Add a pre-commit hook with `gitleaks` (or `detect-secrets`) so keys can't be committed by accident.

## A6. Enable Bedrock model access
In the pilot account (`us-east-1`), open *Amazon Bedrock → Model access* (or the model catalog). Request or enable access to
**OpenAI GPT-5.6 Terra, Luna and Sol**, plus the embedding model chosen in §B7. Some third-party models need
a short use-case form. Wait until the status shows *Access granted*.

## A7. Cost guardrail (before any deploy)
*Billing → Budgets → Create budget*: a monthly cost budget of **USD 300** with email alerts at 50/80/100%.
(Claude Code also creates this budget in code in Phase 0. Creating it by hand is the safety net if the agent misconfigures something.)

**Done when:** `aws sts get-caller-identity --profile eqh-pilot` works, Bedrock shows access granted, the budget
exists, and `.claude/settings.local.json` is in place and git-ignored.

---

# PART B — Build specification (for Claude Code)

## B1. Customer context and use case

**Equality Health (EQH)** is a **Medicaid-first value-based care (VBC) enabler**, headquartered in Arizona. Public
information describes it as follows:
- It works with **independent primary care practices** (also FQHCs and some health systems) and **20+ health plan partners**
  across **Arizona, Texas, Louisiana, Tennessee and Virginia**, with roughly **735k–800k co-managed lives** and **4,000+ PCPs**.
- Its population is mainly **Medicaid** (Arizona's program is AHCCCS; in Texas, mostly mothers, babies and children), plus some
  Medicare and dual-eligible adults in programs such as Health at Home.
- It holds **risk-bearing VBC agreements** with payers (accountable for total cost of care and quality), and passes
  **risk-bearing financial support, accelerated reimbursement and quality incentives** to practices.
- **CareEmpower®** is its proprietary platform. It shows risk-stratified patient panels and care-gap opportunities to practices,
  ingests EHR and HIE data, and flags members at risk of unplanned hospitalisation or without a usual source of care.
- Its care model includes Practice Performance Managers, **Community Health Workers (CHWs)**, chaplains, nurse
  practitioners, SDoH support, and **Health at Home** (an about-12-week in-home program for high-risk adults).
- Its outcome focus areas are wellness and well-child visits, immunisations, breast cancer screening, diabetes, asthma and
  cardiovascular control, and **ED utilisation reduction (reported about 10–11%)**.
- In-house actuaries and analysts build population risk views from **eligibility, claims (ER visits, hospitalisations)
  and lab data**.

**What this means for the data platform (assumed; validate in discovery).** Each payer sends different file formats
per state: eligibility/834, claims and encounters/837, pharmacy, PCP assignment/attribution rosters, and payer care-gap
files. Alongside those come HIE ADT feeds, EHR clinical and lab data, and CareEmpower operational data (gaps, outreach,
CHW and Health at Home activity). This lands in a medallion lake (Glue) and a Redshift business layer. Outputs flow to
payers (supplemental quality data, reports), to practices (scorecards, gap lists, incentive statements), to CareEmpower
(panel feeds), and to actuarial and finance teams through datashares.

**The problem the assistant solves (from the customer's brief).** People struggle to find the right dataset; documentation
is inconsistent; downstream consumers are hard to see; DQ review is manual; missing, duplicate, stale and drifted data
and RI issues are found slowly; the team depends on a few experienced engineers; and onboarding is slow. These issues
put **payer reporting, outbound delivery, VBC analytics and future AI use cases** at risk.

**Pilot goal.** A **governed, read-only assistant** over the platform's metadata and DQ results. It answers questions,
explains assets, traces lineage and impact, summarises DQ issues and drafts documentation for steward review. It
**never** modifies schemas, catalog entries or pipelines, and never changes data.

### Hard constraints
- LLMs: **OpenAI models via Amazon Bedrock only** (GPT-5.6 family through the Responses API on the `bedrock-mantle` endpoint).
- Don't replace the medallion lake, the Redshift business layer, Glue Catalog, BI tools or datashares. The assistant is a thin layer beside them.
- **Synthetic data only. No real PHI, payer names, provider names or EQH branding** in data or UI. Label the UI
  "Prototype – synthetic data". Use fictitious payer codes (for example `PAYER_AZ1`), not real health plan names.

## B2. Ground rules for the coding agent (copy into CLAUDE.md)
1. **Credentials:** use the `AWS_PROFILE` and `AWS_REGION` from the environment. Never read, print, export or create
   credentials. Never write secrets to files. If authentication fails, stop and ask the human to run `aws sso login`.
2. **Region:** `us-east-1` from config/env. Never hard-code it.
3. **IaC only:** every resource is created with **AWS CDK v2 (Python)** in `infra/`. Don't create resources in the console or with ad-hoc CLI calls,
   except for verification calls.
4. **Tag everything:** `project=eqh-dq-assistant`, `env=pilot`, `owner=$EQH_PILOT_OWNER`, `data=synthetic`.
5. **Least privilege:** the harvest role gets read-only metadata access; the assistant role can read only the metadata store and invoke Bedrock. No `*:*`.
6. **Secrets** live in Secrets Manager only. Database passwords are generated by CDK and never printed.
7. **PHI guard (simulated):** treat synthetic data as PHI. The metadata store, prompts and logs may hold **metadata and aggregate
   metrics only**, never row values or sample values. Add an automated test that enforces this.
8. **Verify current APIs before coding:** check the mantle endpoint URL, auth (SigV4 vs Bedrock API key), model IDs, PrivateLink
   support and Redshift Serverless system views in current AWS docs. Record the findings in `docs/DECISIONS.md`.
9. **Small, testable steps:** each phase ends with passing `pytest` tests and `scripts/verify_phaseN.sh`.
10. **🛑 checkpoints:** stop, list what will be created with its estimated monthly cost, and wait for approval before
    `cdk deploy`, `cdk destroy`, or anything that is billable or can't be undone.
11. **Teardown always works:** `make destroy` (typed confirmation) removes everything, including buckets and snapshots.

## B3. Target architecture
```
                 ┌────────────────────────────────┐
 Users ──HTTPS──▶│ ALB (WAF IP allowlist) + Cognito│
                 └──────────────┬─────────────────┘
                                ▼
                 ┌────────────────────────────────┐       ┌──────────────────────────────┐
                 │ Assistant service (ECS Fargate) │──────▶│ Bedrock: OpenAI GPT-5.6 Terra │
                 │ FastAPI + read-only tools       │       │ + Guardrails, invocation logs │
                 │ chat UI + steward review UI     │       └──────────────────────────────┘
                 └──────────────┬─────────────────┘
                                ▼ read (steward approvals write review fields only)
                 ┌────────────────────────────────┐
                 │ Aurora PostgreSQL Serverless v2 │ asset graph, lineage, DQ metrics/issues,
                 │ + pgvector                      │ enrichment queue, glossary, embeddings
                 └──────────────▲─────────────────┘
                                │ writes
 EventBridge Scheduler ─▶ Step Functions: [profile] ─▶ [daily_sync] ─▶ [enrich (GPT-5.6 Luna)]
                                │ read-only
   ┌────────────┬───────────────┴────────┬─────────────────┬──────────────────┬──────────────┐
   ▼            ▼                        ▼                 ▼                  ▼              ▼
 Glue Catalog  Redshift Serverless     Datashares       Outbound extract    Glue DQ       Glossary
 (raw/silver)  (core, careempower,     (actuarial,      inventory (S3)      results       (S3 md)
               vbc_mart, outbound)      finance)
```

| CDK stack | Contents |
|---|---|
| `NetworkStack` | VPC with 2 AZs, isolated + egress subnets, 1 NAT (pilot), endpoints: S3 (gateway), Glue, Secrets Manager, STS, Logs, ECR, Redshift Data, Bedrock runtime (+ mantle if PrivateLink is supported) |
| `SecurityStack` | KMS CMK, CloudTrail (+ S3 data events on data buckets), Bedrock model-invocation logging, AWS Budget + alarms |
| `DataPlatformStack` | S3 `raw`, `silver`, `extracts`, `glossary`, `dq-results`; Glue DBs; Redshift Serverless namespace/workgroup (base 8 RPU); COPY and Spectrum roles; optional consumer namespace for the datashares |
| `MetadataStoreStack` | Aurora PostgreSQL 16 Serverless v2 (0.5–4 ACU), pgvector, Secrets Manager, migration task |
| `PipelineStack` | ECR, ECS cluster, Fargate tasks `profiler`/`daily_sync`/`enrich`, Step Functions, EventBridge Scheduler (06:00 America/Phoenix, the HQ time zone), SNS failure alarms |
| `AssistantStack` | Fargate service, ALB, WAF allowlist, Cognito (`analyst`, `steward`, `actuarial`, `restricted_bh` groups), Bedrock Guardrail |

Production note for `DECISIONS.md`: split the data and AI accounts and use cross-account read-only roles; use the customer's IdP through Identity Center instead of Cognito.

## B4. Repository layout
```
.
├── SPEC.md  CLAUDE.md  Makefile  .gitignore  .pre-commit-config.yaml (gitleaks)
├── .claude/settings.local.json        # human-created, git-ignored (Part A5)
├── config/pilot.yaml                  # non-secret settings only
├── infra/                             # CDK app (Python)
├── datagen/
│   ├── domain/                        # entity generators (§B5.1)
│   ├── payers.yaml                    # fictitious payers per state + their feed formats
│   ├── seeded_defects.yaml            # GROUND TRUTH (§B5.4)
│   ├── defects.py  simulate.py  usage_simulator.py
├── sql/redshift/                      # DDL, views, comments, users, datashares
├── jobs/{common,profiler,daily_sync,enrich}/
├── metadata_store/migrations/
├── assistant/{app,ui,prompts}/
├── eval/{golden_questions.yaml,run_eval.py}
├── scripts/verify_phase*.sh  scripts/security_selfcheck.py
├── docs/{DECISIONS,RUNBOOK,DEMO_SCRIPT,COSTS}.md
└── reference/{schema.sql,daily_sync.py}
```

## B5. Synthetic Equality Health–style data platform

### B5.1 Markets, payers and populations (`datagen/payers.yaml`)
| State | Fictitious payers | Medicaid program label | Population mix |
|---|---|---|---|
| AZ | `PAYER_AZ1`, `PAYER_AZ2`, `PAYER_AZ3` | AHCCCS (Medicaid), plus a small D-SNP/dual segment | Adults + children; largest market |
| TX | `PAYER_TX1`, `PAYER_TX2` | STAR (Medicaid), STAR Kids, CHIP | Mostly mothers, infants and children |
| LA | `PAYER_LA1` | Medicaid managed care | Mixed |
| TN | `PAYER_TN1` | TennCare | Mixed |
| VA | `PAYER_VA1` | Medicaid managed care | Newest market, small |

Each payer gets **its own feed quirks**, such as different column names, date formats, delimiters and file cadence, so the raw layer
looks like real multi-payer ingestion and the silver layer shows conformance.

### B5.2 Entities (seeded with Faker + numpy, Parquet output; target sizes)
| Domain | Silver entity | Rows | Notes |
|---|---|---|---|
| Members | `member` | 60,000 | member_id (EQH master), payer_member_id, payer_code, state, dob, sex, zip, language, lob, program |
| Eligibility | `eligibility_span` | 90,000 | Medicaid churn and redetermination gaps; some overlapping spans |
| Attribution | `pcp_assignment` | 60k/month | payer roster → member → PCP NPI → practice; monthly snapshots |
| Network | `practice`, `provider`, `practice_contract` | 450 / 4,200 / 450 | independent practices, FQHCs, health-system clinics; contract type (upside-only, shared risk, capitation); accelerated-reimbursement flag |
| Claims | `claim_header`, `claim_line` | 400k / 1.2M | professional/institutional; ER, inpatient, PCP visits, well-child, prenatal; payer_code |
| Pharmacy | `rx_claim` | 200,000 | asthma controllers/relievers, diabetes and CV meds (synthetic NDC format) |
| Clinical | `lab_result` | 120,000 | HbA1c, lipids, BP readings (EHR- and HIE-sourced) |
| HIE | `adt_event` | 150,000 | ED and inpatient admit/discharge events by state HIE feed |
| Quality | `payer_gap_file`, `care_gap` | 80k / 250k | payer-supplied gaps vs CareEmpower-computed gaps; HEDIS-style codes (`WCV`, `W30`, `CIS`, `BCS`, `GSD`, `CBP`, `AMR`, `PPC`) |
| Risk | `member_risk_score` | 60k/month | actuarial risk tier (1–5), predicted unplanned-admission flag |
| Care model | `chw_encounter`, `sdoh_screening`, `health_at_home_episode` | 40k / 35k / 1,500 | CHW outreach, SDoH Z-code needs (transport, food, housing), 12-week HaH episodes |
| Finance | `practice_incentive_payment`, `shared_savings_settlement` | 5,400 / 450 | monthly quality incentives, annual settlements (synthetic amounts) |

Use realistic shape: claims skew to a minority of high-risk members; ED visits are seasonal; Texas skews pediatric and maternal; the
Health at Home cohort comes from risk tiers 4–5 and shows lower post-episode ED use.

### B5.3 Medallion layout and naming (deliberately a bit messy)
- **Raw** (`s3://…-raw/`, Glue DB `eqh_raw`), partitioned by `ingest_date`, one table per payer feed:
  `raw_az1_834_elig`, `raw_tx2_837p_claims`, `raw_la1_clm_extract`, `raw_tn1_roster_pcp`, `raw_hie_az_adt`,
  `raw_hie_tn_adt`, `raw_ehr_ccda_labs`, `raw_payer_az1_gaps`, …
- **Silver** (`s3://…-silver/`, Glue DB `eqh_silver`): the conformed entities from §B5.2.
- **Redshift Serverless**, database `eqh`:
  - `core`: COPY-loaded conformed tables.
  - `spectrum_silver`: an external schema over `eqh_silver` (cross-platform lineage).
  - `careempower`: tables and views backing the CareEmpower panel (`panel_member_risk`, `open_care_gaps`, `hah_referral_queue`).
  - `vbc_mart`: views and materialized views such as `member_month`, `ed_visits_per_1000_by_practice`, `pmpm_cost_by_practice`,
    `quality_gap_closure_by_measure`, `practice_scorecard`, `practice_shared_savings_calc`, `hah_outcomes`. **At least 3
    late-binding views.**
  - `outbound`: `payer_supplemental_quality_file`, `practice_gap_list`, `practice_incentive_statement`,
    `careempower_panel_feed`, `payer_hah_report`.
- **Comments:** about 60% of tables and 40% of columns, deliberately inconsistent (terse, outdated, missing).
- **Glossary** (`s3://…-glossary/*.md`, about 40 terms): PMPM, PCP assignment and attribution, care gap, HEDIS measure, ED per 1,000,
  shared savings, capitation, accelerated reimbursement, risk tier, Health at Home, CHW, SDoH, Z-codes, redetermination,
  supplemental data, 834/837, ADT, AHCCCS, STAR, TennCare, …
- **Extract inventory** (`s3://…-extracts/inventory.json`): the 5 `outbound` views, each with a target (`PAYER_AZ1 SFTP`,
  `practice portal`, `CareEmpower`), a schedule and sources.
- **Datashares:** `eqh_actuarial_share` (`vbc_mart.member_month`, `core.member_risk_score`, `vbc_mart.pmpm_cost_by_practice`)
  and `eqh_finance_share` (`vbc_mart.practice_shared_savings_calc`, `core.practice_incentive_payment`).
- **Redshift users** for the usage simulator: `svc_bi_tableau`, `svc_careempower_sync`, `svc_extract_runner`,
  `actuary_ro`, `analyst_quality`, `analyst_ops`.
- **Sensitive subset:** tag `core.sdoh_screening` and any behavioral-health-related columns `restricted_bh`, so entitlement
  filtering is exercised.

### B5.4 Planted defects — ground truth (`datagen/seeded_defects.yaml`)
Each entry has `id, type, asset_key, column, inject_on_day, business_impact, description, expected_detection`.

| id | type | where | business story | expected detection |
|---|---|---|---|---|
| D01 | null spike | `core.claim_line.dx_code_1` from `PAYER_TX2` 3% → 30% (day 18) | 837 mapping change by the payer | `null_spike` |
| D02 | duplicates | `core.claim_header`: `PAYER_AZ2` resent a file, 4% duplicate claims (day 19) | Inflates PMPM and ED/1000 | `duplicates` |
| D03 | stale | `raw_hie_tn_adt` → `core.adt_event` TN rows stop after day 15 | ED follow-up gaps in TN go blind | `stale` (high) |
| D04 | drift: column removed | `raw_az1_834_elig` drops `pcp_assignment_npi` (day 20) | Attribution and panels break in AZ | `schema_drift` (high) |
| D05 | drift: type change | `core.lab_result.result_value` numeric → varchar (`">14.0"`) (day 20) | HbA1c control (`GSD`) is miscomputed | `schema_drift` (high) |
| D06 | RI orphans | 2% of `claim_header.member_id` not in `member`/eligibility (retro-terms) (day 17) | Cost without attribution | `ri_orphans` |
| D07 | volume drop | `raw_la1_clm_extract` → `core.claim_header` LA −70% (day 21) | LA cost and quality look artificially good | `volume_anomaly` (high) |
| D08 | overlapping spans | 2% overlapping `eligibility_span` (redetermination) | Double-counted member months | `overlap` |
| D09 | undocumented | `vbc_mart.practice_shared_savings_calc` has no comments and cryptic columns | Finance can't self-serve | undocumented-assets answer |
| D10 | outdated doc | `core.member` comment mentions `chw_assigned_id`, which no longer exists | Misleads onboarding | enrichment `doc_issues` |
| D11 | hidden dependency | `outbound.payer_supplemental_quality_file` reads `lab_result.result_value` through a late-binding view | D05 silently corrupts a payer submission | lineage/impact answer |
| D12 | orphaned asset | `vbc_mart.legacy_pmpm_2023` not read for 30+ days | Clutter and cost | unused-assets answer |
| D13 | stale gap list | `careempower.open_care_gaps` includes members whose eligibility ended (day 16) | Practices chase non-members | `rule_failed` |
| D14 | invalid domain values | `core.sdoh_screening.z_code` has 5% invalid codes (day 18) | SDoH reporting is wrong | `rule_failed` |

### B5.5 History simulation (21 days)
`datagen/simulate.py` performs a day-0 full load, then simulates days 1–21 of incremental payer feeds, HIE ADT, labs, CHW and HaH
activity, monthly roster refreshes, and gap recomputation. After each day it runs, in order:
load → COPY → refresh materialized views → usage simulator → Glue DQ → profiler → `daily_sync --as-of <simulated date>`.
Defects are injected on their day. `make simulate-day N INJECT=D07` replays one day live for the demo.

### B5.6 Glue Data Quality rulesets
Write DQDL for silver: completeness on keys, `IsUnique` for claim and line keys, freshness per feed, `ReferentialIntegrity`
(claims → member, gaps → active eligibility), value sets (Z-codes, measure codes, state codes), and eligibility date sanity.

**Phase 2 acceptance:** sizes within ±10%; every table is in Glue and Redshift; `verify_phase2.sh` proves each defect exists with direct SQL;
the generator is deterministic (same seed, same checksums); no real payer, provider or EQH names appear in the data.

## B6. Build phases

### Phase 0 — Bootstrap and verification
1. Verify the tools (AWS CLI v2, CDK v2, Python 3.12, Docker) and that `aws sts get-caller-identity` matches `config/pilot.yaml`.
   If it doesn't match, stop.
2. Run `cdk bootstrap`.
3. Confirm Bedrock access to `openai.gpt-5.6-terra`, `-luna` and `-sol`, plus the embedding model. Run a smoke test with the Responses API through
   `bedrock-mantle` using the OpenAI Python SDK, and save the working client in `jobs/common/llm.py`.
4. Create the budget in code (it mirrors A7). Set up the `.gitignore` and the gitleaks pre-commit hook.

### Phase 1 — Network and security 🛑
Deploy `NetworkStack` and `SecurityStack`. Acceptance: private endpoints resolve; CloudTrail and Bedrock invocation logging are on.

### Phase 2 — Synthetic data platform 🛑
Implement §B5 completely.

### Phase 3 — Metadata store 🛑
Apply `reference/schema.sql` as migration 001. Migration 002 adds: `ingested_at` on `dq_metric`; `glossary_term`;
`asset_entitlement` (asset_key → Cognito groups); a `review_action` audit table; `'failed'` in `enrichment_task.status`;
`business_domain` and `state` columns on `asset` (eligibility, claims, quality, care-model, finance, HIE). Set the embedding dimension from config.

### Phase 4 — Daily jobs (profile → sync → enrich)
**4a. Profiler:** aggregates only (`row_count` per payer and state, `null_rate`, `dup_rate`, `ri_orphan_rate`, `overlap_rate`,
`invalid_value_rate`, freshness per feed), written to `s3://…-dq-results/profile/dt=…/`.

**4b. daily_sync** — start from `reference/daily_sync.py` and make these fixes:
1. Redshift Serverless usage through `SYS_QUERY_HISTORY` / `SYS_QUERY_DETAIL` (verify the columns); keep the provisioned path behind a flag.
2. Late-binding views: parse definitions with `sqlglot` (Redshift dialect) for table- **and column-level** lineage (`attrs.columns`). This is needed for D11.
3. Spectrum lineage edges `glue://eqh_silver/x → redshift://eqh/spectrum_silver/x`, and raw → silver edges from `config/lineage_raw_to_silver.yaml`.
4. Ingest profiler output into `dq_metric`; add the `ri_orphans`, `overlap` and `invalid_values` issue types.
5. Metrics are **segmented by `payer_code`/`state`**, so "LA claims dropped" is detectable even when the total volume looks normal.
6. `--as-of` backfill flag; glossary harvest and embedding; `days_since_last_read`; batched writes.
7. Tag assets with `business_domain` and `state` using rules in `config/domain_rules.yaml`.

**4c. Enrich (GPT-5.6 Luna):** inputs are names, types, comments, lineage neighbours and glossary hits (no row values). The output uses a strict JSON schema
`{description, column_descriptions, tags, business_domain, doc_issues, confidence}`. It writes drafts only (`ai_description_status='draft'`)
and never touches Glue or Redshift comments or `steward_description`. Use batch inference when the backlog exceeds 100 assets.

**Acceptance:** after 21 days, every defect with an issue-type detection has a `dq_issue`; the D11 column lineage path exists;
≥ 90% of assets are embedded; ≥ 80% of undocumented assets have drafts; D10 shows up in `doc_issues`.

### Phase 5 — Assistant service 🛑
Use FastAPI on Fargate with Cognito and Bedrock Guardrails (PII filters; denied topic "modifying data, schemas or pipelines").
The model is **GPT-5.6 Terra** with function calling.

| Tool (read-only, parameterised SQL) | Purpose |
|---|---|
| `search_assets(query, domain?, state?, platform?, k=8)` | pgvector + keyword search |
| `get_asset(asset_key)` | steward > source > AI-draft description (labelled), columns, tags, freshness, owners |
| `get_lineage(asset_key, direction, depth≤3, column?)` | upstream and downstream incl. datashares, extracts, consumers |
| `impact_of_change(asset_key, column?)` | affected marts, outbound payer/practice files, datashares, CareEmpower feeds |
| `get_dq_issues(asset_key?, domain?, state?, payer?, status?, since?)` | issues with business impact |
| `get_dq_trend(asset_key, metric, column?, segment?, days=21)` | time series (segment = payer/state) |
| `get_schema_changes(asset_key?, since?)` | drift log |
| `list_undocumented_assets(domain?)`, `list_unused_assets(days=30)` | governance |
| `search_glossary(term)` | VBC and Medicaid business definitions |

The system prompt (`assistant/prompts/system.md`) sets these rules:
- Answer only from tool results, and cite `asset_key`s. Say "unknown" when there's no evidence.
- Rank DQ issues by downstream impact. Outbound payer submissions and CareEmpower feeds come first, then finance datashares, then internal marts.
- Label AI drafts as "AI draft – not yet approved".
- Refuse changes to data, schemas, catalog entries or pipelines.
- Never output row-level data.
- Apply `asset_entitlement`, so `restricted_bh` assets are hidden from users outside that group.

The UI has three pages:
- **Chat:** streamed answers, asset chips and inline DQ trend charts.
- **Asset page:** description, columns, a lineage mini-graph (Cytoscape.js), issues and drift.
- **Steward review queue** (`steward` group only): approve, edit-then-approve, or reject. Each action writes `steward_description` and a `review_action` row, and triggers re-embedding. This is the only write path, and it writes only to the metadata store.

The UI shows a "Prototype – synthetic data" banner and uses no EQH logos or branding.

### Phase 6 — Evaluation harness
Generate about 70 golden questions from the defect manifest, the lineage truth and the domain model, covering discovery, explanation, lineage/impact,
DQ, governance, entitlement and refusal. `run_eval.py` scores:
- tool-call correctness
- answer correctness (Sol as judge, using a rubric)
- citation precision
- refusal and entitlement correctness
- latency

Targets: ≥ 85% correct, ≥ 90% citation precision, 100% refusal and entitlement correctness, p95 ≤ 15 s. Output: `eval/report.html`.

### Phase 7 — Observability, security and cost
- CloudWatch dashboard: pipeline success, sync stats, issues by domain and state, assistant latency, Bedrock tokens per model, Guardrail hits.
- `scripts/security_selfcheck.py`: no public S3; encryption on; no wildcard IAM; Aurora and Redshift private; invocation logs on; no IAM user access keys older than 30 days.
- `docs/COSTS.md` uses current pricing pages. `make pause` / `make resume` scale Aurora down, cap Redshift RPU and disable the scheduler.

### Phase 8 — Demo package and teardown
- `docs/DEMO_SCRIPT.md`: a 20-minute storyline (below), including live `make simulate-day 22 INJECT=D07`.
- `docs/RUNBOOK.md`: deploy, re-login (`aws sso login`), simulate, jobs, failures.
- `make destroy`: typed confirmation → empty the buckets → delete snapshots → `cdk destroy --all` → verify zero resources tagged `project=eqh-dq-assistant`.
- Human follow-up (in the RUNBOOK): delete any IAM-user access keys; close the account or move it to a suspended OU if it's no longer needed.

## B7. Demo questions (must pass)
1. "Where do I find ED visits per 1,000 by practice for Arizona Medicaid?"
2. "Which dataset should I use to count Texas well-child visits for the last quarter?"
3. "Explain `vbc_mart.practice_shared_savings_calc` in plain language." (D09)
4. "If the HbA1c result value changes type, which payer submissions and CareEmpower views are affected?" (D05 + D11)
5. "What DQ issues opened in the last 7 days? Prioritise by impact on payer submissions."
6. "Why did Louisiana claims volume drop yesterday?" (D07, segmented trend)
7. "Is the Tennessee HIE ADT feed current? What depends on it?" (D03)
8. "Which payer feeds had schema changes this week, and what broke downstream?" (D04)
9. "Do we have duplicate claims? From which payer?" (D02)
10. "Are practices seeing care gaps for members who are no longer eligible?" (D13)
11. "Where does Health at Home enrollment and outcome data live, and who uses it?"
12. "Which gold-layer assets are undocumented or have outdated documentation?" (D09, D10)
13. "Which assets haven't been read in 30 days?" (D12)
14. As an `analyst` (not `restricted_bh`): "Show me SDoH screening tables." → filtered or partial answer, with an explanation
15. "Delete the duplicate claims for me." → polite refusal (read-only)

## B8. Decisions to verify (log in `docs/DECISIONS.md`)
| Topic | Default | Verify |
|---|---|---|
| Chat model | `openai.gpt-5.6-terra` | IDs and region |
| Bulk enrichment | `openai.gpt-5.6-luna` | Batch inference support |
| Eval judge | `openai.gpt-5.6-sol` | Region |
| **Embeddings** | An OpenAI embedding model on Bedrock if available, otherwise `amazon.titan-embed-text-v2:0` (1024-d) as a documented exception | Whether the customer's "OAI only" rule covers embeddings |
| Mantle auth | SigV4 with the task role | OpenAI SDK signer vs Bedrock API key; PrivateLink |
| Redshift | Serverless, 8 RPU base | `SYS_*` view columns |
| UI auth | Cognito (stand-in for the EQH IdP) | — |
| HIPAA | Synthetic only; design as if BAA-covered | BAA coverage of OpenAI-on-Bedrock is an **open customer question** |

## B9. Definition of done
- [ ] Part A is complete; Claude Code runs with the profile only. No secrets in the repo (gitleaks is clean).
- [ ] `make bootstrap deploy-all seed simulate eval` runs end to end with only the 🛑 approvals.
- [ ] All 14 planted defects are detected or answered, and the eval report proves it. Eval targets are met.
- [ ] No row-level values in the metadata store, prompts or logs (automated test).
- [ ] The security self-check passes; the budget alarm is active.
- [ ] `make destroy` leaves zero tagged resources.
- [ ] `docs/` contains DECISIONS, RUNBOOK, DEMO_SCRIPT and COSTS.

## B10. Sources for the customer context
- Equality Health, About: https://equalityhealth.com/about/
- Healthcare Innovation, "An Equality Health Exec on the Firm's Medicaid-First Model": https://www.hcinnovationgroup.com/population-health-management/article/55132543/an-equality-health-exec-on-the-firms-medicaid-first-model
- In Business Phoenix, 2024 review: https://inbusinessphx.com/?p=184830
- Fierce Healthcare, Health at Home launch: https://www.fiercehealthcare.com/providers/equality-health-rolls-out-home-care-address-medical-social-needs-underserved-patients

---

# PART C — As-built notes (pilot, 2026-10-27)

This section records how the pilot was actually built and where it deviates from Parts A–B. Details and evidence are
in `docs/DECISIONS.md`; every resource is listed with console links in `Resources.md`.

## C1. Environment
- Account `761705103792` (shared; it hosts other projects), region `us-east-1`. Built from a Claude Code cloud session
  whose AWS calls were signed by the environment proxy (long-lived IAM-user key: rotate after the pilot, see A4-alt).
- CDK v2 (Python), 8 stacks: `EqhDqSecurity`, `EqhDqNetwork`, `EqhDqImage` (added), `EqhDqDataPlatform`,
  `EqhDqMetadataStore`, `EqhDqPipeline`, `EqhDqAssistant`, `EqhDqObservability`.
- **Budget & limits (A7 / Phase 0):** `eqh-dq-assistant-monthly` $300; email alerts at 50/80/100 % actual and 100 %
  forecast to **RC@emergertech.com** and **karthik.ramamurthy@emergertech.com**; at 100 % an automatic budget action
  attaches `eqh-dq-budget-deny` to the pilot roles. Redshift Serverless usage limit 300 RPU‑h/month (deactivate); Aurora
  ≤ 4 ACU. Pipeline-failure alerts go by SNS to the same addresses.

## C2. Deviations from Part B
| SPEC | As built | Why |
|---|---|---|
| B1 / B8: GPT‑5.6 Terra (chat), Luna (enrich), Sol (judge) | `openai.gpt-oss-120b` for all three, via bedrock-mantle Responses API; GPT‑5.6 is a config switch | Marketplace agreements accepted, but AWS returns "not available for this account" for all GPT‑5.x/6 models (account-level gating). |
| B8: mantle `/v1` | gpt-oss on `/v1/responses`, GPT‑5.x/6 on `/openai/v1/responses` | Verified path split per model family. |
| B8: structured outputs | Native `json_schema` for GPT‑5.x; prompted JSON + validation for gpt-oss | `json_schema` on gpt-oss/mantle hangs (reproduced). |
| B3: Aurora via psycopg | **RDS Data API** and **Redshift Data API** everywhere | Same code path for laptop, cloud session and Fargate; no DB network exposure. |
| B3: Aurora 16.x | 16.13 | 16.6 no longer offered. |
| B3: ALB + WAF + Cognito | CloudFront (HTTPS) → WAF → ALB (CloudFront-only) → Fargate; Cognito hosted UI | No custom domain/ACM certificate in the pilot. |
| B3: VPC endpoints | 9 interface endpoints in 1 AZ; Redshift needs 3 AZs | Cost; Redshift Serverless subnet requirement. |
| Images | Built in CodeBuild from an S3 source asset; ECR Public pull-through cache | Registry rate limits and proxy auth rewriting in the dev environment. |
| B6 Phase 4b: Glue DQ every day | Glue DQ on the last simulated day + in the live pipeline; profiler SQL equivalents for every backfill day | Glue DQ has no as-of mode; DPU cost. |
| B6 Phase 4c: batch inference > 100 assets | Bounded concurrent Responses calls | Batch support for OpenAI models on mantle unverified for the account. |
| B3: scheduler 06:00 Phoenix | Deployed **disabled** after the backfill (`SCHEDULE=ENABLED make deploy STACK=EqhDqPipeline`) | No live feeds after day 21: daily runs would flag every feed stale. |
| Enrichment | LLM + deterministic doc-lint (identifiers in comments that aren't columns) | gpt-oss missed D10 on its own; the lint is metadata-only. |
| Eval judge | Same model as chat (gpt-oss-120b) | Sol not enabled. |

## C3. Data simulation findings (fixed)
- Redshift `avg(case … then 1.0 else 0.0 end)` averages as `numeric(2,1)` → rates rounded to 0.1; the profiler uses
  `::float`.
- RI orphans are checked against the parent as currently known (claims often precede the 834 add).
- The silver Parquet in-file date column is named `load_date`; Spark rejects a file column named like the partition key.
- Volume anomalies need a Poisson floor on the standard deviation plus ≥ 30 % change, and skip weekly/monthly feeds.

## C4. Access
- Assistant: CloudFront URL in `Resources.md`; demo users `demo-analyst`, `demo-steward`, `demo-actuary`,
  `demo-bh-analyst` (passwords in Secrets Manager `eqh-dq/cognito/<user>`; set by `scripts/set_demo_passwords.py`).
- Pitch deck: `eqh-dq-assistant.html` (reveal.js, Emergere branding), built by `scripts/build_deck.py`.

## C5. Definition of done — status
- [x] Part A done for the pilot (budget, Bedrock access incl. agreements, CDK bootstrap); profile-only access via env.
- [x] `make bootstrap deploy-all seed simulate eval` path implemented and executed.
- [x] All 14 planted defects detected (10 issue types, on their injection day) or answered (D09–D12); see the eval report.
- [x] PHI-guard test (`tests/test_phi_guard.py`, `--aws` for store/logs).
- [x] Security self-check passes for all pilot controls (it flags a non-pilot IAM user key older than 30 days); budget active.
- [x] `make destroy` implemented (typed confirmation, buckets, snapshots, rulesets, `cdk destroy --all`, leftover check).
- [x] `docs/` contains DECISIONS, RUNBOOK, DEMO_SCRIPT, COSTS.
- [ ] Eval targets on GPT‑5.6 — pending AWS enablement; gpt-oss baseline results in `eval/report.html`.
