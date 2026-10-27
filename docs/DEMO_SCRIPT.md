# Demo script — 20 minutes

**URL:** see `Resources.md` → *Assistant* (CloudFront). **Users:** `demo-analyst`, `demo-steward`,
`demo-bh-analyst` (passwords in Secrets Manager `eqh-dq/cognito/<user>`). **Data as of:** 2026-10-26 (simulated day 21).
Every page shows the "Prototype – synthetic data" banner; there's no customer branding.

Before the demo: `make resume` (if paused), open the URL and sign in as `demo-analyst` in one browser profile and
`demo-steward` in another, open the CloudWatch dashboard `eqh-dq-assistant`, and have a terminal at the repo root.

| Min | Beat | Do / ask | What to point out |
|---|---|---|---|
| 0–1 | Frame | Slides 1–8 of `eqh-dq-assistant.html` (or skip) | Multi-payer Medicaid platform, 14 planted failure modes |
| 1–3 | **Find data** (analyst) | *Where do I find ED visits per 1,000 by practice for Arizona Medicaid?* | Semantic + keyword search; recommends `vbc_mart.ed_visits_per_1000_by_practice`; filters by state/payer |
| 3–4 | | *Which dataset should I use to count Texas well-child visits for the last quarter?* | Core claims with `service_category = well_child` vs WCV gaps; "last quarter" relative to the data date |
| 4–6 | **Understand** | *Explain `vbc_mart.practice_shared_savings_calc` in plain language.* → click the asset chip | D09: undocumented view; label **AI draft – not yet approved**; cryptic columns decoded from lineage; lineage graph |
| 6–9 | **Impact** | *If the HbA1c result value changes type, which payer submissions and CareEmpower views are affected?* | D05 + D11: column lineage `core.lab_result.result_value → vbc_mart.v_member_lab_measures (late-binding) → outbound.payer_supplemental_quality_file → PAYER_AZ1 SFTP`; why late-binding hides it |
| 9–11 | **Triage** | *What DQ issues opened in the last 7 days? Prioritise by impact on payer submissions.* | Ranking: payer submissions › CareEmpower › practice deliveries › finance › marts; schema drift (D04, D05), LA volume (D07), TX2 nulls (D01), AZ2 dups (D02), orphans (D06), invalid Z-codes (D14) |
| 11–13 | | *Why did Louisiana claims volume drop yesterday?* | Segmented `daily_rows` trend chart for `payer_code=PAYER_LA1`/`state=LA` (≈ −66%); upstream raw feed `raw_la1_clm_extract`; impact: LA cost/quality look artificially good |
| 13–15 | **Live day** (terminal) | `make simulate-day N=22 INJECT=D07` (~3 min) then ask again *Is the PAYER_LA1 claims feed normal today?* | Fresh data → profile → sync → issue updated; nothing pre-baked |
| | | (while it runs) *Is the Tennessee HIE ADT feed current? What depends on it?* | D03 stale (≈155 h vs 36 h SLA) → `core.adt_event` → HaH referral queue |
| 15–17 | **Govern** | *Which gold-layer assets are undocumented or have outdated documentation?* | D09 + D10 (`core.member` comment mentions `chw_assigned_id`, which doesn't exist) |
| | (steward) | Steward review → approve or edit one draft | Only write path; writes `steward_description` + `review_action`; re-embeds; Glue/Redshift untouched |
| | | *Which assets haven't been read in 30 days?* | D12 `vbc_mart.legacy_pmpm_2023` (retirement candidate) |
| 17–19 | **Guardrails** | analyst: *Show me SDoH screening tables.* | Entitlements: `restricted_bh` assets hidden, with an explanation; compare as `demo-bh-analyst` |
| | | *Delete the duplicate claims for me.* | Polite refusal (deterministic pre-filter + Bedrock Guardrail denied topic) |
| 19–20 | **Trust** | Open `eval/report.html` and the CloudWatch dashboard | 74 golden questions: correctness, citation precision, refusal/entitlement, latency; tokens per model, guardrail hits |

## Backup answers if something is slow
- The LLM is `openai.gpt-oss-120b` on bedrock-mantle (GPT‑5.6 pending AWS enablement). p50 ≈ 4 s, p95 < 15 s.
- If Aurora was paused, the first question takes ~15 s while it resumes.
- The asset page works without the LLM: `/asset?key=redshift://eqh/core/lab_result`.
