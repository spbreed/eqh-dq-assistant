-- Outbound extracts (all late-binding views).
CREATE OR REPLACE VIEW outbound.payer_supplemental_quality_file AS
SELECT m.payer_code, m.payer_member_id, 'GSD' AS measure_code, lm.result_date AS service_date,
       lm.loinc_code, lm.result_numeric AS result_value, lm.gsd_hba1c_controlled AS numerator_flag
FROM vbc_mart.v_member_lab_measures lm
JOIN core.member m ON m.member_id = lm.member_id
WHERE lm.loinc_code = '4548-4'
WITH NO SCHEMA BINDING;

CREATE OR REPLACE VIEW outbound.practice_gap_list AS
SELECT g.practice_id, p.practice_name, g.member_id, g.measure_code, g.opened_date, g.days_open
FROM careempower.open_care_gaps g
JOIN core.practice p ON p.practice_id = g.practice_id
WITH NO SCHEMA BINDING;

CREATE OR REPLACE VIEW outbound.practice_incentive_statement AS
SELECT i.practice_id, p.practice_name, i.payer_code, i.payment_month, i.measure_bundle, i.amount
FROM core.practice_incentive_payment i
JOIN core.practice p ON p.practice_id = i.practice_id
WITH NO SCHEMA BINDING;

CREATE OR REPLACE VIEW outbound.careempower_panel_feed AS
SELECT r.member_id, r.practice_id, r.risk_tier, r.predicted_unplanned_admit_flag,
       coalesce(g.open_gaps, 0) AS open_gaps
FROM careempower.panel_member_risk r
LEFT JOIN (SELECT member_id, count(*) AS open_gaps FROM careempower.open_care_gaps GROUP BY 1) g
  ON g.member_id = r.member_id
WITH NO SCHEMA BINDING;

CREATE OR REPLACE VIEW outbound.payer_hah_report AS
SELECT h.state, h.status, h.episodes, h.avg_ed_pre_90d, h.avg_ed_post_90d, h.ed_reduction_pct
FROM vbc_mart.hah_outcomes h
WITH NO SCHEMA BINDING;
