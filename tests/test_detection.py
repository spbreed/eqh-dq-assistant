"""Issue detection rules on synthetic metric histories (no database: a fake MetaDB records writes)."""
from datetime import datetime, timedelta, timezone

from jobs.daily_sync import sync


class FakeDB:
    def __init__(self, history):
        self.history, self.issues = history, []

    def executemany(self, sql, rows, chunk=400):
        if "insert into dq_issue" in sql:
            self.issues += rows

    def query(self, sql, params=None):
        if "from dq_metric" in sql:
            return self.history
        return []


AT = datetime(2026, 10, 26, 13, 30, tzinfo=timezone.utc)


def hist(key, metric, values, seg="", col=""):
    return [{"asset_key": key, "column_name": col, "metric": metric, "segment": seg, "value": v} for v in values]


def m(key, metric, value, seg="", col=""):
    return {"asset_key": key, "column_name": col, "metric": metric, "segment": seg, "value": value,
            "measured_at": AT.isoformat()}


def run(history, metrics):
    db = FakeDB(history)
    sync.record_metrics_and_issues(db, "r", metrics, AT)
    return {(i["k"], i["t"], i["s"]) for i in db.issues}


CH = "redshift://eqh/core/claim_header"


def test_volume_drop_detected_noise_ignored():
    h = hist(CH, "daily_rows", [330, 310, 345, 320, 335, 328, 316], "state=LA")
    assert (CH, "volume_anomaly", "state=LA") in run(h, [m(CH, "daily_rows", 100, "state=LA")])
    assert not run(h, [m(CH, "daily_rows", 362, "state=LA")])  # +10%: noise


def test_weekly_feeds_not_flagged_on_off_days():
    k = "redshift://eqh/core/payer_gap_file"
    assert not run(hist(k, "daily_rows", [0, 0, 5000, 0, 0, 0, 0]), [m(k, "daily_rows", 0)])


def test_null_spike_and_stale_and_rule():
    k = "redshift://eqh/core/claim_line"
    h = hist(k, "null_rate", [0.03] * 8, "payer_code=PAYER_TX2", "dx_code_1")
    got = run(h, [m(k, "null_rate", 0.30, "payer_code=PAYER_TX2", "dx_code_1"),
                  m("glue://eqh_raw/raw_hie_tn_adt", "hours_since_last_ingest", 155.0),
                  m("glue://eqh_raw/raw_hie_tn_adt", "freshness_sla_hours", 36.0),
                  m("redshift://eqh/careempower/open_care_gaps", "rule:open_gaps_active_eligibility", 0.0)])
    assert (k, "null_spike", "payer_code=PAYER_TX2") in got
    assert ("glue://eqh_raw/raw_hie_tn_adt", "stale", "") in got
    assert ("redshift://eqh/careempower/open_care_gaps", "rule_failed", "") in got


def test_rate_thresholds():
    got = run([], [m(CH, "dup_rate", 0.04, "payer_code=PAYER_AZ2"), m(CH, "ri_orphan_rate", 0.02),
                   m("redshift://eqh/core/eligibility_span", "overlap_rate", 0.022),
                   m("redshift://eqh/core/eligibility_span", "overlap_rate", 0.002, "x")])
    assert {(CH, "duplicates", "payer_code=PAYER_AZ2"), (CH, "ri_orphans", ""),
            ("redshift://eqh/core/eligibility_span", "overlap", "")} == got
