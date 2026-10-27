from jobs.common.db import split_sql
from jobs.daily_sync.lineage import parse_view, referenced_tables
from datagen.domain import reference as R


def views():
    out = {}
    for f in ("03_careempower.sql", "04_vbc_mart.sql", "05_outbound.sql"):
        for st in split_sql((R.ROOT / "sql" / "redshift" / f).read_text()):
            w = st.split()
            if w[0].upper() == "CREATE" and "VIEW" in [x.upper() for x in w[:5]]:
                out[w[[x.upper() for x in w].index("VIEW") + 1]] = st
    return out


def test_d11_column_path():
    v = views()
    src, m = parse_view(v["vbc_mart.v_member_lab_measures"])
    assert src == {"core.lab_result"}
    assert {"src": "core.lab_result", "src_col": "result_value", "dst_col": "result_numeric"} in m
    src, m = parse_view(v["outbound.payer_supplemental_quality_file"])
    assert "vbc_mart.v_member_lab_measures" in src
    assert {"src": "vbc_mart.v_member_lab_measures", "src_col": "result_numeric", "dst_col": "result_value"} in m


def test_at_least_three_late_binding_views():
    assert sum("NO SCHEMA BINDING" in s.upper() for s in views().values()) >= 3


def test_views_do_not_list_themselves():
    for name, st in views().items():
        src, _ = parse_view(st)
        assert name not in src, name


def test_usage_query_parsing():
    assert referenced_tables("/* x */ SELECT count(*) FROM (SELECT * FROM vbc_mart.member_month LIMIT 50)") == \
        {"vbc_mart.member_month"}
