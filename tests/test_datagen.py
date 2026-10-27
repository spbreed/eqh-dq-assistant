"""Ground truth: defects are present in the generated data with the planted magnitudes; generator is deterministic."""
import functools

import pandas as pd
import pytest

from datagen import defects
from datagen.domain import reference as R
from datagen.domain.entities import SIZES, Gen
from datagen.writer import frame_checksums

SEED = 20261005


@functools.lru_cache(maxsize=1)
def frames():
    return defects.inject(Gen(SEED).all(), SEED)


def test_sizes_within_10pct():
    f = frames()
    for k in ("member", "claim_header", "rx_claim", "lab_result", "care_gap", "chw_encounter", "sdoh_screening"):
        assert abs(len(f[k]) - SIZES[k]) / SIZES[k] < 0.10, k
    assert 1_080_000 <= len(f["claim_line"]) <= 1_320_000


def test_d01_null_spike():
    cl = frames()["claim_line"]
    tx2 = cl[cl.payer_code == "PAYER_TX2"]
    before = tx2[tx2.ingest_day < 18].dx_code_1.isna().mean()
    after = tx2[tx2.ingest_day >= 18].dx_code_1.isna().mean()
    assert before < 0.05 and 0.25 < after < 0.35


def test_d02_d06_d07():
    ch = frames()["claim_header"]
    az2 = ch[ch.payer_code == "PAYER_AZ2"]
    assert 0.03 < az2.claim_id.duplicated().mean() < 0.05
    mem = set(frames()["member"].member_id)
    late = ch[ch.ingest_day >= 17]
    assert 0.01 < (~late.member_id.isin(mem)).mean() < 0.03
    la = ch[ch.payer_code == "PAYER_LA1"].groupby("ingest_day").size()
    assert la[21] < 0.45 * la[1:21].mean()


def test_d03_tn_adt_stops():
    adt = frames()["adt_event"]
    assert adt[(adt.state == "TN")].ingest_day.max() == 15


def test_d14_invalid_zcodes():
    sd = frames()["sdoh_screening"]
    bad = ~sd.z_code.isin(R.VALID_Z_CODES)
    assert bad[sd.ingest_day < 18].mean() == 0 and 0.03 < bad[sd.ingest_day >= 18].mean() < 0.07


def test_no_real_names():
    f = frames()
    text = " ".join(f["practice"].practice_name) + " ".join(f["provider"].provider_label)
    for banned in ("Equality Health", "UnitedHealthcare", "Aetna", "Anthem", "Humana", "Molina", "Centene",
                   "Banner", "Mercy Care", "Superior", "Amerigroup", "BlueCross"):
        assert banned.lower() not in text.lower()
    assert set(f["member"].payer_code) <= {f"PAYER_{x}" for x in ("AZ1", "AZ2", "AZ3", "TX1", "TX2", "LA1", "TN1",
                                                                   "VA1")}


@pytest.mark.slow
def test_deterministic():
    again = defects.inject(Gen(SEED).all(), SEED)
    assert frame_checksums(again) == frame_checksums(frames())
