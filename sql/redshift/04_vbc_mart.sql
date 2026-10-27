-- VBC marts: materialized views, regular views and late-binding views (>= 3 late-binding).
CREATE MATERIALIZED VIEW vbc_mart.member_month AS
SELECT c.month_start AS month, e.member_id, e.payer_code, e.state, e.lob, e.program
FROM core.eligibility_span e
JOIN core.dim_calendar_month c
  ON c.month_start >= date_trunc('month', e.start_date)
 AND c.month_start <= coalesce(e.end_date, '2099-12-31'::date)
WHERE c.month_start >= '2025-10-01';

CREATE MATERIALIZED VIEW vbc_mart.pmpm_cost_by_practice AS
SELECT date_trunc('month', ch.service_date)::date AS month, ch.practice_id, ch.payer_code, ch.state,
       sum(ch.total_paid) AS total_paid, count(DISTINCT ch.member_id) AS members_with_claims
FROM core.claim_header ch
GROUP BY 1, 2, 3, 4;

CREATE OR REPLACE VIEW vbc_mart.ed_visits_per_1000_by_practice AS
SELECT ch.state, ch.payer_code, ch.practice_id, date_trunc('month', ch.service_date)::date AS month,
       count(*) AS ed_visits,
       round(1000.0 * 12 * count(*) / nullif(mm.member_months, 0), 1) AS ed_visits_per_1000
FROM core.claim_header ch
JOIN (SELECT pa.practice_id, mm.month, count(*) AS member_months
      FROM vbc_mart.member_month mm
      JOIN core.pcp_assignment pa ON pa.member_id = mm.member_id AND pa.effective_month = mm.month
      GROUP BY 1, 2) mm ON mm.practice_id = ch.practice_id AND mm.month = date_trunc('month', ch.service_date)
WHERE ch.service_category = 'er'
GROUP BY ch.state, ch.payer_code, ch.practice_id, 4, mm.member_months;
COMMENT ON VIEW vbc_mart.ed_visits_per_1000_by_practice IS 'ED visits per 1,000 member-years by practice and month';

CREATE OR REPLACE VIEW vbc_mart.quality_gap_closure_by_measure AS
SELECT g.payer_code, p.state, g.measure_code, date_trunc('month', g.opened_date)::date AS month,
       count(*) AS gaps, sum(CASE WHEN g.status = 'closed' THEN 1 ELSE 0 END) AS closed_gaps,
       round(100.0 * sum(CASE WHEN g.status = 'closed' THEN 1 ELSE 0 END) / count(*), 1) AS closure_rate_pct
FROM core.care_gap g
JOIN core.practice p ON p.practice_id = g.practice_id
GROUP BY 1, 2, 3, 4;

CREATE OR REPLACE VIEW vbc_mart.practice_scorecard AS
SELECT p.practice_id, p.practice_name, p.state, p.practice_type,
       sum(c.total_paid) / nullif(sum(c.members_with_claims), 0) AS paid_per_member,
       (SELECT round(avg(closure_rate_pct), 1) FROM vbc_mart.quality_gap_closure_by_measure q
         WHERE q.state = p.state) AS state_gap_closure_pct
FROM core.practice p
LEFT JOIN vbc_mart.pmpm_cost_by_practice c ON c.practice_id = p.practice_id
GROUP BY 1, 2, 3, 4;
COMMENT ON VIEW vbc_mart.practice_scorecard IS 'Practice scorecard: cost and quality';

-- D09: undocumented, cryptic column names. Finance-owned.
CREATE OR REPLACE VIEW vbc_mart.practice_shared_savings_calc AS
SELECT s.practice_id AS prac_id, s.payer_code AS pyr, s.performance_year AS py,
       s.benchmark_pmpm AS bm_pmpm_adj, s.actual_pmpm AS act_pmpm_rf, s.member_months AS mm_ct,
       s.gross_savings AS ss_amt_gross, c.practice_share_pct AS shr_pct_t2,
       CASE WHEN s.quality_gate_met THEN 1 ELSE 0 END AS qg_flg,
       s.practice_share_amount AS ss_net_prac,
       CASE WHEN c.contract_type = 'capitation' THEN 'C' WHEN c.contract_type = 'shared_risk' THEN 'SR' ELSE 'UO' END AS ctyp
FROM core.shared_savings_settlement s
JOIN core.practice_contract c ON c.practice_id = s.practice_id AND c.payer_code = s.payer_code;

CREATE OR REPLACE VIEW vbc_mart.hah_outcomes AS
SELECT state, status, risk_tier_at_referral, count(*) AS episodes,
       avg(ed_visits_pre_90d::float) AS avg_ed_pre_90d, avg(ed_visits_post_90d::float) AS avg_ed_post_90d,
       round(100.0 * (1 - sum(ed_visits_post_90d)::float / nullif(sum(ed_visits_pre_90d), 0)), 1) AS ed_reduction_pct
FROM core.health_at_home_episode
GROUP BY 1, 2, 3;
COMMENT ON VIEW vbc_mart.hah_outcomes IS 'Health at Home (12-week in-home program) outcomes: ED use before vs after';

-- D11 (late-binding): reads lab_result.result_value without schema binding. If the column changes type the
-- view keeps compiling, and censored text values like '>14.0' silently become NULL.
CREATE OR REPLACE VIEW vbc_mart.v_member_lab_measures AS
SELECT l.member_id, l.loinc_code, l.result_date,
       CASE WHEN l.result_value::varchar ~ '^[0-9]+(\\.[0-9]+)?$' THEN l.result_value::varchar::float END AS result_numeric,
       CASE WHEN l.loinc_code = '4548-4' AND l.result_value::varchar ~ '^[0-9]+(\\.[0-9]+)?$'
            AND l.result_value::varchar::float < 9.0 THEN 1 ELSE 0 END AS gsd_hba1c_controlled
FROM core.lab_result l
WITH NO SCHEMA BINDING;

-- Late-binding over Spectrum (cross-platform lineage): pharmacy adherence straight from silver
CREATE OR REPLACE VIEW vbc_mart.v_rx_controller_fills AS
SELECT r.member_id, r.drug_class, count(*) AS fills, sum(r.days_supply) AS days_supply
FROM spectrum_silver.rx_claim r
WHERE r.drug_class IN ('asthma_controller', 'asthma_reliever')
GROUP BY 1, 2
WITH NO SCHEMA BINDING;

-- D12: legacy table nobody reads any more
CREATE TABLE IF NOT EXISTS vbc_mart.legacy_pmpm_2023 (month date, practice_id varchar(64), pmpm double precision);
COMMENT ON TABLE vbc_mart.legacy_pmpm_2023 IS 'PMPM by practice, 2023 methodology (superseded)';
