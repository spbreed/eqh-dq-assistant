#!/usr/bin/env bash
# Phase 4 acceptance: every issue-type defect has a dq_issue; D11 column path; >=90% embedded; >=80% drafts; D10 doc_issues.
set -euo pipefail
source "$(dirname "$0")/env.sh"
python - <<'PY'
import json
import yaml
from jobs.common.db import MetaDB
db = MetaDB()
truth = {d["id"]: d for d in yaml.safe_load(open("datagen/seeded_defects.yaml"))["defects"]}
need = {"D01": ("redshift://eqh/core/claim_line", "null_spike"), "D02": ("redshift://eqh/core/claim_header", "duplicates"),
        "D03": ("glue://eqh_raw/raw_hie_tn_adt", "stale"), "D04": ("glue://eqh_raw/raw_az1_834_elig", "schema_drift"),
        "D05": ("redshift://eqh/core/lab_result", "schema_drift"), "D06": ("redshift://eqh/core/claim_header", "ri_orphans"),
        "D07": ("redshift://eqh/core/claim_header", "volume_anomaly"), "D08": ("redshift://eqh/core/eligibility_span", "overlap"),
        "D13": ("redshift://eqh/careempower/open_care_gaps", "rule_failed"), "D14": ("redshift://eqh/core/sdoh_screening", "rule_failed")}
bad = []
for d, (k, t) in need.items():
    n = db.one("select count(*) from dq_issue where asset_key=:k and issue_type=:t", {"k": k, "t": t})
    print(("PASS " if n else "FAIL ") + f"{d} {t} on {k}"); bad += [] if n else [d]
p = db.query("""select attrs from lineage_edge where src_asset_key='redshift://eqh/vbc_mart/v_member_lab_measures'
                and dst_key='redshift://eqh/outbound/payer_supplemental_quality_file' and is_active""")
p0 = db.query("""select attrs from lineage_edge where src_asset_key='redshift://eqh/core/lab_result'
                 and dst_key='redshift://eqh/vbc_mart/v_member_lab_measures' and is_active""")
J = lambda a: a if isinstance(a, dict) else json.loads(a or "{}")
ok11 = p and p0 and any(c["src_col"] == "result_value" for c in J(p0[0]["attrs"])["columns"]) and \
       any(c["src_col"] == "result_numeric" for c in J(p[0]["attrs"])["columns"])
print(("PASS " if ok11 else "FAIL ") + "D11 column path lab_result.result_value -> v_member_lab_measures -> payer file"); bad += [] if ok11 else ["D11"]
emb = db.one("select round(100.0 * count(distinct e.asset_key) / count(distinct a.asset_key)) from asset a left join embedding e using (asset_key) where not a.is_deleted")
print(f"{'PASS' if float(emb) >= 90 else 'FAIL'} embedded assets {emb}%"); bad += [] if float(emb) >= 90 else ["embed"]
und = db.one("""select round(100.0 * count(*) filter (where ai_description_status in ('draft','approved')) / nullif(count(*),0))
                from asset where not is_deleted and source_comment is null and steward_description is null""")
print(f"{'PASS' if und and float(und) >= 80 else 'FAIL'} undocumented assets with drafts {und}%"); bad += [] if und and float(und) >= 80 else ["drafts"]
d10 = db.one("select ai_meta->'doc_issues' from asset where asset_key='redshift://eqh/core/member'")
ok10 = "chw_assigned_id" in str(d10)
print(("PASS " if ok10 else "FAIL ") + f"D10 doc_issues: {str(d10)[:120]}"); bad += [] if ok10 else ["D10"]
assert not bad, bad
PY
echo "phase 4 OK"
