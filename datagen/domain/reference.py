"""Code sets and shared helpers for the synthetic EQH-style data platform. All values are synthetic."""
from __future__ import annotations

import functools
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]

MEASURES = ["WCV", "W30", "CIS", "BCS", "GSD", "CBP", "AMR", "PPC"]
VALID_Z_CODES = {
    "Z59.00": "housing", "Z59.01": "housing", "Z59.1": "housing", "Z59.41": "food", "Z59.48": "food",
    "Z59.82": "transport", "Z59.86": "financial", "Z56.0": "employment", "Z60.2": "social_isolation",
    "Z63.8": "family", "Z59.7": "financial", "Z55.6": "education",
}
INVALID_Z_CODES = ["Z59.9X", "Z99.999", "ZZ1.0", "Z59", "Z0.00"]
STATES = ["AZ", "TX", "LA", "TN", "VA"]
RISK_TIER_P = np.array([0.35, 0.30, 0.20, 0.10, 0.05])
RISK_UTIL_WEIGHT = np.array([1.0, 2.0, 4.0, 9.0, 18.0])          # claims skew to a minority of high-risk members
SERVICE_CATEGORIES = ["pcp_visit", "well_child", "prenatal", "er", "inpatient", "specialist", "outpatient", "other"]
CPT_BY_CATEGORY = {
    "pcp_visit": ["99213", "99214", "99203", "99204"], "well_child": ["99391", "99392", "99393", "99394"],
    "prenatal": ["59425", "59426", "0500F", "76805"], "er": ["99283", "99284", "99285"],
    "inpatient": ["99221", "99222", "99223", "99232"], "specialist": ["99243", "99244", "93000"],
    "outpatient": ["36415", "80053", "85025", "71046"], "other": ["A0425", "E0607", "97110"],
}
DX_BY_CATEGORY = {
    "pcp_visit": ["E11.9", "I10", "J45.909", "E78.5", "R51.9"], "well_child": ["Z00.129", "Z00.121", "Z23"],
    "prenatal": ["Z34.90", "O09.90", "Z34.80"], "er": ["R07.9", "J06.9", "S09.90XA", "R10.9", "J45.901"],
    "inpatient": ["I50.9", "J18.9", "E11.65", "O80", "N39.0"], "specialist": ["I25.10", "M54.5", "E11.40"],
    "outpatient": ["Z13.1", "E11.9", "D64.9"], "other": ["Z74.09", "R26.89"],
}
PAID_BY_CATEGORY = {"pcp_visit": 95, "well_child": 110, "prenatal": 180, "er": 850, "inpatient": 9500,
                    "specialist": 210, "outpatient": 140, "other": 75}
LABS = {"4548-4": ("HbA1c", "%", 7.4, 1.6), "13457-7": ("LDL cholesterol", "mg/dL", 118, 32),
        "8480-6": ("Systolic BP", "mmHg", 132, 16), "8462-4": ("Diastolic BP", "mmHg", 82, 10)}
DRUG_CLASSES = {"asthma_controller": 45, "asthma_reliever": 28, "diabetes": 160, "statin": 18,
                "antihypertensive": 14, "prenatal_vitamin": 9, "other": 35}
LANGS_BY_STATE = {"AZ": ([0.62, 0.33, 0.05], ["en", "es", "other"]), "TX": ([0.52, 0.44, 0.04], ["en", "es", "other"]),
                  "LA": ([0.92, 0.05, 0.03], ["en", "es", "other"]), "TN": ([0.9, 0.07, 0.03], ["en", "es", "other"]),
                  "VA": ([0.85, 0.1, 0.05], ["en", "es", "other"])}
PRACTICE_WORDS = ["Mesa", "Canyon", "River", "Pine", "Cedar", "Prairie", "Bayou", "Ridge", "Valley", "Harbor",
                  "Summit", "Willow", "Oak", "Sun", "Lake", "Creek", "Meadow", "Stone"]
PRACTICE_SUFFIX = ["Family Medicine", "Primary Care", "Pediatrics", "Community Health Center", "Health Clinic",
                   "Internal Medicine"]


def load_yaml(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text())


@functools.lru_cache(maxsize=1)
def sim_cfg() -> dict:
    return load_yaml("config/pilot.yaml")["simulation"]


@functools.lru_cache(maxsize=1)
def day0() -> date:
    return date.fromisoformat(sim_cfg()["day0_date"])


@functools.lru_cache(maxsize=None)
def day_date(n: int) -> date:
    return day0() + timedelta(days=int(n))


def ingest_days(rng: np.random.Generator, n: int, day0_share: float, days: int) -> np.ndarray:
    """Day 0 = historical full load; days 1..N get an even share of the remaining rows."""
    out = rng.integers(1, days + 1, size=n)
    out[rng.random(n) < day0_share] = 0
    return out


def to_dates(base: date, offsets) -> pd.Series:
    ts = pd.Timestamp(base) + pd.to_timedelta(np.asarray(offsets, dtype="int64"), unit="D")
    return pd.Series(ts).dt.date
