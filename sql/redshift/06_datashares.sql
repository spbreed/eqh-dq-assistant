-- Outbound datashares for actuarial and finance consumers.
CREATE DATASHARE eqh_actuarial_share;
ALTER DATASHARE eqh_actuarial_share ADD SCHEMA vbc_mart;
ALTER DATASHARE eqh_actuarial_share ADD SCHEMA core;
ALTER DATASHARE eqh_actuarial_share ADD TABLE vbc_mart.member_month;
ALTER DATASHARE eqh_actuarial_share ADD TABLE core.member_risk_score;
ALTER DATASHARE eqh_actuarial_share ADD TABLE vbc_mart.pmpm_cost_by_practice;
CREATE DATASHARE eqh_finance_share;
ALTER DATASHARE eqh_finance_share ADD SCHEMA vbc_mart;
ALTER DATASHARE eqh_finance_share ADD SCHEMA core;
ALTER DATASHARE eqh_finance_share ADD TABLE vbc_mart.practice_shared_savings_calc;
ALTER DATASHARE eqh_finance_share ADD TABLE core.practice_incentive_payment;
