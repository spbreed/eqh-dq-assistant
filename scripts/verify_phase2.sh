#!/usr/bin/env bash
# Phase 2: every table in Glue and Redshift, sizes within ±10%, every data defect provable with direct SQL.
set -euo pipefail
source "$(dirname "$0")/env.sh"
python - <<'PY'
import boto3
from datagen.load import admin
from datagen.domain.entities import SIZES
rs, glue = admin(), boto3.client("glue")
n_raw = len(glue.get_tables(DatabaseName="eqh_raw")["TableList"]); n_silver = len(glue.get_tables(DatabaseName="eqh_silver")["TableList"])
print("glue raw/silver tables:", n_raw, n_silver); assert n_raw >= 40 and n_silver == 19
q = lambda sql: list(rs.query(sql)[0].values())[0]
for t in ("member", "claim_header", "rx_claim", "lab_result", "care_gap", "sdoh_screening", "chw_encounter"):
    n = int(q(f"select count(*) from core.{t}")); assert abs(n - SIZES[t]) / SIZES[t] <= 0.10, (t, n); print(t, n)
checks = {
 "D01 TX2 dx null >25% after day 18": "select avg(case when dx_code_1 is null then 1.0::float else 0 end) > 0.25 from core.claim_line where payer_code='PAYER_TX2' and ingest_date >= '2026-10-23'",
 "D02 AZ2 duplicate claims": "select count(*) - count(distinct claim_id) > 500 from core.claim_header where payer_code='PAYER_AZ2'",
 "D03 TN ADT stops after day 15": "select max(ingest_date) = '2026-10-20' from core.adt_event where state='TN'",
 "D05 lab_result.result_value is varchar": "select data_type like 'character varying%' from svv_columns where table_schema='core' and table_name='lab_result' and column_name='result_value'",
 "D06 orphan claim members": "select count(*) > 100 from core.claim_header c left join core.member m using(member_id) where m.member_id is null",
 "D07 LA day-21 volume < 45% of prior mean": "select sum(case when ingest_date='2026-10-26' then 1 else 0 end) < 0.45 * sum(case when ingest_date between '2026-10-06' and '2026-10-25' then 1 else 0 end)/20.0 from core.claim_header where payer_code='PAYER_LA1'",
 "D08 overlapping spans > 1% of members": "select count(distinct a.member_id) > 600 from core.eligibility_span a join core.eligibility_span b on a.member_id=b.member_id and a.span_id<b.span_id and a.start_date<=coalesce(b.end_date,'2099-12-31') and b.start_date<=coalesce(a.end_date,'2099-12-31')",
 "D09 shared savings view has no comment": "select count(*) = 0 from svv_tables where table_schema='vbc_mart' and table_name='practice_shared_savings_calc' and remarks is not null",
 "D10 member comment mentions chw_assigned_id": "select remarks like '%chw_assigned_id%' from svv_tables where table_schema='core' and table_name='member'",
 "D12 legacy_pmpm_2023 exists": "select count(*) = 1 from svv_tables where table_schema='vbc_mart' and table_name='legacy_pmpm_2023'",
 "D13 open gaps for termed members": "select count(*) > 100 from careempower.open_care_gaps g where not exists (select 1 from core.eligibility_span e where e.member_id=g.member_id and coalesce(e.end_date,'2099-12-31') >= '2026-10-26')",
 "D14 invalid z-codes": "select count(*) > 50 from core.sdoh_screening where z_code not in ('Z59.00','Z59.01','Z59.1','Z59.41','Z59.48','Z59.82','Z59.86','Z56.0','Z60.2','Z63.8','Z59.7','Z55.6')",
}
bad = []
for name, sql in checks.items():
    ok = str(q(sql)).lower() in ("true", "1", "t")
    print(("PASS " if ok else "FAIL ") + name); bad += [] if ok else [name]
cols = {c["Name"] for c in glue.get_table(DatabaseName="eqh_raw", Name="raw_az1_834_elig")["Table"]["StorageDescriptor"]["Columns"]}
print(("PASS " if "pcp_asgn_npi" not in cols else "FAIL ") + "D04 raw_az1_834_elig dropped pcp_asgn_npi"); bad += [] if "pcp_asgn_npi" not in cols else ["D04"]
print("D11 lineage: see verify_phase4.sh")
assert not bad, bad
PY
python -m pytest -q tests/test_datagen.py
echo "phase 2 OK"
