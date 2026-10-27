"""Simulated BI / CareEmpower / extract / analyst usage against Redshift.

Each consumer runs its usual reads as its own Redshift user (SET SESSION AUTHORIZATION) with query_group
'simday:<date>', so SYS_QUERY_HISTORY carries both the consumer and the simulated day. vbc_mart.legacy_pmpm_2023
(D12) is never read.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from datagen.domain import reference as R
from datagen.load import admin

log = logging.getLogger("usage")

WORKLOAD = {
    "svc_bi_tableau": ["vbc_mart.practice_scorecard", "vbc_mart.ed_visits_per_1000_by_practice",
                       "vbc_mart.pmpm_cost_by_practice", "vbc_mart.quality_gap_closure_by_measure",
                       "vbc_mart.hah_outcomes"],
    "svc_careempower_sync": ["careempower.panel_member_risk", "careempower.open_care_gaps",
                             "careempower.hah_referral_queue", "outbound.careempower_panel_feed"],
    "svc_extract_runner": ["outbound.payer_supplemental_quality_file", "outbound.practice_gap_list",
                           "outbound.practice_incentive_statement", "outbound.payer_hah_report"],
    "actuary_ro": ["vbc_mart.member_month", "core.member_risk_score", "vbc_mart.pmpm_cost_by_practice"],
    "analyst_quality": ["vbc_mart.quality_gap_closure_by_measure", "core.care_gap", "core.lab_result",
                        "vbc_mart.v_member_lab_measures", "core.sdoh_screening"],
    "analyst_ops": ["core.claim_header", "core.adt_event", "core.eligibility_span", "vbc_mart.v_rx_controller_fills"],
}
WEEKLY = {"vbc_mart.practice_shared_savings_calc": "svc_bi_tableau", "core.practice_incentive_payment": "actuary_ro",
          "vbc_mart.hah_outcomes": "analyst_quality", "outbound.payer_hah_report": "svc_extract_runner"}


def statements_for(day: int) -> dict[str, list[str]]:
    out = {u: [f"/* usage-sim {u} */ SELECT count(*) FROM (SELECT * FROM {obj} LIMIT 50)" for obj in objs]
           for u, objs in WORKLOAD.items()}
    if day % 7 == 0:
        for obj, u in WEEKLY.items():
            out[u].append(f"/* usage-sim {u} weekly */ SELECT count(*) FROM (SELECT * FROM {obj} LIMIT 50)")
    return out


def run_day(day: int) -> None:
    rs = admin()
    label = f"simday:{R.day_date(day).isoformat()}"
    jobs = list(statements_for(day).items())

    def one(job):
        u, sqls = job
        try:
            rs.batch([f"SET SESSION AUTHORIZATION '{u}'"] + sqls, label=label)
        except RuntimeError as e:  # a broken view must not stop the simulation; it shows up as a failed query
            log.warning("usage %s day %s: %s", u, day, str(e)[:200])

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(one, jobs))


def run_history(days_before: int = 30) -> None:
    """Pre-history so 'not read in 30 days' is observable at the start of the simulation."""
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(run_day, range(-days_before, 0)))
