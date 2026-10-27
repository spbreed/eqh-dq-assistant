-- CareEmpower panel views (regular views).
CREATE OR REPLACE VIEW careempower.panel_member_risk AS
SELECT m.member_id, m.payer_code, m.state, m.lob, pa.practice_id, pa.pcp_npi,
       r.risk_tier, r.risk_score, r.predicted_unplanned_admit_flag, r.score_month
FROM core.member m
JOIN core.pcp_assignment pa
  ON pa.member_id = m.member_id
 AND pa.effective_month = (SELECT max(effective_month) FROM core.pcp_assignment)
LEFT JOIN core.member_risk_score r
  ON r.member_id = m.member_id
 AND r.score_month = (SELECT max(score_month) FROM core.member_risk_score);

-- D13: the gap list does not check current eligibility, so retro-terminated members keep showing up.
CREATE OR REPLACE VIEW careempower.open_care_gaps AS
SELECT g.care_gap_id, g.member_id, g.practice_id, g.payer_code, g.measure_code, g.opened_date,
       datediff(day, g.opened_date, current_date) AS days_open
FROM core.care_gap g
WHERE g.status = 'open';

CREATE OR REPLACE VIEW careempower.hah_referral_queue AS
SELECT r.member_id, r.practice_id, r.state, r.risk_tier, ed.ed_visits_90d
FROM careempower.panel_member_risk r
JOIN (SELECT member_id, count(*) AS ed_visits_90d
      FROM core.adt_event
      WHERE facility_type = 'ED' AND event_ts >= dateadd(day, -90, current_date)
      GROUP BY member_id) ed ON ed.member_id = r.member_id
LEFT JOIN core.health_at_home_episode h ON h.member_id = r.member_id AND h.status = 'active'
WHERE r.risk_tier >= 4 AND ed.ed_visits_90d >= 2 AND h.episode_id IS NULL;
COMMENT ON VIEW careempower.hah_referral_queue IS 'High-risk members with 2+ ED visits in 90 days, not in Health at Home';
