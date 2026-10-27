"""Glue Data Catalog objects for the raw and silver layers (tables + daily partitions)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError

from datagen.domain import reference as R
from datagen.writer import silver_types
from jobs.common import settings

GLUE_TYPES = {"string": "string", "date": "date", "double": "double", "int": "bigint", "boolean": "boolean",
              "timestamp": "timestamp"}
# ~60% of tables described; inconsistent on purpose
RAW_DESCRIPTIONS = {
    "raw_az1_834_elig": "PAYER_AZ1 834 eligibility, daily, pipe-delimited",
    "raw_tx2_837p_claims": "TX2 837P professional claims",
    "raw_la1_clm_extract": "LA1 claims extract (legacy layout)",
    "raw_tn1_roster_pcp": "TN1 PCP roster (weekly)",
    "raw_hie_az_adt": "AZ state HIE ADT feed",
    "raw_hie_tn_adt": "Tennessee HIE ADT messages, flattened",
    "raw_ehr_ccda_labs": "EHR CCDA lab results",
    "raw_payer_az1_gaps": "AZ1 gap file",
    "raw_az2_837p_claims": "AZ2 claims",
    "raw_tx1_834_elig": "TX1 eligibility (STAR / STAR Kids / CHIP)",
    "raw_careempower_ops": "CareEmpower operational export: CHW encounters and SDoH screenings",
}
SILVER_DESCRIPTIONS = {
    "member": "Conformed member", "eligibility_span": "Conformed eligibility spans",
    "claim_header": "Conformed claim headers (all payers)", "claim_line": "Conformed claim lines",
    "lab_result": "Conformed lab results", "adt_event": "Conformed ADT events", "care_gap": "Care gaps",
    "sdoh_screening": "SDoH screenings (restricted)", "rx_claim": "Pharmacy claims", "practice": "Practices",
    "provider": "Providers",
}


def _glue():
    return boto3.client("glue", region_name=settings.get()["region"])


def _upsert_table(glue, db: str, table_input: dict) -> None:
    try:
        glue.create_table(DatabaseName=db, TableInput=table_input)
    except ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
        glue.update_table(DatabaseName=db, TableInput=table_input)


def raw_table_input(name: str, columns: list[str], delimiter: str) -> dict:
    s = settings.get()
    ti = {
        "Name": name, "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "csv", "skip.header.line.count": "1", "delimiter": delimiter},
        "PartitionKeys": [{"Name": "ingest_date", "Type": "string"}],
        "StorageDescriptor": {
            "Columns": [{"Name": c, "Type": "string"} for c in columns],
            "Location": f"s3://{s['bucket_raw']}/{name}/",
            "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                          "Parameters": {"field.delim": delimiter, "serialization.format": delimiter}}},
    }
    if name in RAW_DESCRIPTIONS:
        ti["Description"] = RAW_DESCRIPTIONS[name]
    return ti


def silver_table_input(entity: str, day: int) -> dict:
    s = settings.get()
    ti = {
        "Name": entity, "TableType": "EXTERNAL_TABLE", "Parameters": {"classification": "parquet"},
        "PartitionKeys": [{"Name": "ingest_date", "Type": "date"}],
        "StorageDescriptor": {
            "Columns": [{"Name": c, "Type": GLUE_TYPES[t]} for c, t in silver_types(entity, day).items()],
            "Location": f"s3://{s['bucket_silver']}/{entity}/",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"}},
    }
    if entity in SILVER_DESCRIPTIONS:
        ti["Description"] = SILVER_DESCRIPTIONS[entity]
    return ti


def register_day(raw_schemas: dict[str, dict], silver_entities: list[str], day: int) -> None:
    """Create/update tables whose structure is defined by today's files, then add today's partitions."""
    glue, s = _glue(), settings.get()
    d = R.day_date(day).isoformat()

    def raw(item):
        name, sch = item
        _upsert_table(glue, "eqh_raw", raw_table_input(name, sch["columns"], sch["delimiter"]))
        _add_partition(glue, "eqh_raw", name, d, f"s3://{s['bucket_raw']}/{name}/ingest_date={d}/",
                       raw_table_input(name, sch["columns"], sch["delimiter"])["StorageDescriptor"])

    def silver(entity):
        ti = silver_table_input(entity, day)
        _upsert_table(glue, "eqh_silver", ti)
        _add_partition(glue, "eqh_silver", entity, d, f"s3://{s['bucket_silver']}/{entity}/ingest_date={d}/",
                       ti["StorageDescriptor"])

    with ThreadPoolExecutor(8) as ex:
        list(ex.map(raw, raw_schemas.items()))
        list(ex.map(silver, silver_entities))


def _add_partition(glue, db: str, table: str, value: str, location: str, sd: dict) -> None:
    sd = dict(sd, Location=location)
    try:
        glue.create_partition(DatabaseName=db, TableName=table,
                              PartitionInput={"Values": [value], "StorageDescriptor": sd})
    except ClientError as e:
        if e.response["Error"]["Code"] != "AlreadyExistsException":
            raise
