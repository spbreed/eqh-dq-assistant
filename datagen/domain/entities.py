"""Clean synthetic entities (SPEC §B5.2). Every frame carries `ingest_day` (0 = historical full load).

Realistic shape: utilisation skews to high-risk members, ED visits are seasonal, Texas skews pediatric/maternal,
Health at Home comes from risk tiers 4–5 and shows lower post-episode ED use. Defects are injected later
(datagen/defects.py), never here.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
from faker import Faker

from datagen.domain import reference as R

SIZES = {"member": 60_000, "practice": 450, "provider": 4_200, "claim_header": 400_000, "rx_claim": 200_000,
         "lab_result": 120_000, "adt_event": 150_000, "payer_gap_file": 80_000, "care_gap": 250_000,
         "chw_encounter": 40_000, "sdoh_screening": 35_000, "health_at_home_episode": 1_500}
DAY0_SHARE = 0.85


class Gen:
    def __init__(self, seed: int):
        self.rng = np.random.default_rng(seed)
        self.fake = Faker("en_US")
        Faker.seed(seed)
        self.payers = R.load_yaml("datagen/payers.yaml")
        self.days = R.sim_cfg()["days"]
        self.d0 = R.day0()
        self.hist_start = self.d0 - timedelta(days=365)
        self.out: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ helpers
    def _ingest(self, n: int, share: float = DAY0_SHARE) -> np.ndarray:
        return R.ingest_days(self.rng, n, share, self.days)

    def _event_dates(self, ingest_day: np.ndarray, lag_lo: int, lag_hi: int, seasonal: bool = False) -> pd.Series:
        """Date an event so it is consistent with the day it arrived (historical rows spread over a year)."""
        n = len(ingest_day)
        hist = self.rng.integers(0, 365, n)
        if seasonal:  # winter-heavy: resample by month weight (ED seasonality)
            month = ((self.hist_start.month - 1 + hist // 30) % 12) + 1
            w = np.where(np.isin(month, [12, 1, 2]), 1.0, np.where(np.isin(month, [6, 7, 8]), 0.55, 0.75))
            keep = self.rng.random(n) < w
            hist = np.where(keep, hist, self.rng.integers(0, 365, n))
        lag = self.rng.integers(lag_lo, lag_hi + 1, n)
        recv = np.where(ingest_day == 0, hist, 365 + ingest_day)
        return R.to_dates(self.hist_start, recv - lag)

    # ------------------------------------------------------------------ network
    def network(self) -> None:
        rng, n = self.rng, SIZES["practice"]
        states = rng.choice(R.STATES, n, p=[0.45, 0.25, 0.12, 0.12, 0.06])
        ptype = rng.choice(["independent", "fqhc", "health_system_clinic"], n, p=[0.7, 0.18, 0.12])
        names = [f"{rng.choice(R.PRACTICE_WORDS)} {rng.choice(R.PRACTICE_SUFFIX)} {i:03d}" for i in range(n)]
        self.out["practice"] = pd.DataFrame({
            "practice_id": [f"PR{i:04d}" for i in range(n)], "practice_name": names, "practice_type": ptype,
            "state": states, "tin": [f"9{rng.integers(10**7, 10**8)}" for _ in range(n)],
            "accelerated_reimbursement_flag": rng.random(n) < 0.35,
            "onboarded_date": R.to_dates(self.d0 - timedelta(days=2000), rng.integers(0, 1900, n)),
            "ingest_day": 0})
        m = SIZES["provider"]
        prac_idx = rng.integers(0, n, m)
        self.out["provider"] = pd.DataFrame({
            "npi": [f"9{900000000 + i:09d}"[:10] for i in range(m)],
            "provider_label": [f"Provider {i:05d}" for i in range(m)],
            "specialty": rng.choice(["family_medicine", "pediatrics", "internal_medicine", "ob_gyn", "nurse_practitioner"],
                                    m, p=[0.38, 0.27, 0.18, 0.07, 0.10]),
            "practice_id": self.out["practice"]["practice_id"].to_numpy()[prac_idx],
            "state": states[prac_idx], "is_pcp": rng.random(m) < 0.85, "ingest_day": 0})
        payer_codes = list(self.payers["payers"])
        rows = []
        for i, (pid, st) in enumerate(zip(self.out["practice"]["practice_id"], states)):
            payer = rng.choice([p for p in payer_codes if self.payers["payers"][p]["state"] == st])
            rows.append((f"CT{i:04d}", pid, payer, rng.choice(["upside_only", "shared_risk", "capitation"], p=[0.5, 0.35, 0.15]),
                         self.d0.replace(month=1, day=1), self.d0.replace(month=12, day=31),
                         float(rng.choice([0.3, 0.4, 0.5, 0.6]))))
        self.out["practice_contract"] = pd.DataFrame(rows, columns=[
            "contract_id", "practice_id", "payer_code", "contract_type", "effective_start", "effective_end",
            "practice_share_pct"]).assign(ingest_day=0)

    # ------------------------------------------------------------------ members, eligibility, attribution, risk
    def members(self) -> None:
        rng, n = self.rng, SIZES["member"]
        codes = list(self.payers["payers"])
        share = np.array([self.payers["payers"][c]["share"] for c in codes])
        payer = rng.choice(codes, n, p=share / share.sum())
        state = np.array([self.payers["payers"][p]["state"] for p in payer])
        ped_share = np.array([self.payers["states"][s]["pediatric_share"] for s in state])
        is_child = rng.random(n) < ped_share
        age = np.where(is_child, rng.integers(0, 19, n), rng.integers(19, 80, n))
        # Texas skews to mothers: adult TX members are mostly women of child-bearing age
        tx_mother = (state == "TX") & ~is_child & (rng.random(n) < 0.7)
        age = np.where(tx_mother, rng.integers(18, 40, n), age)
        sex = np.where(tx_mother, "F", rng.choice(["F", "M"], n, p=[0.55, 0.45]))
        dob = R.to_dates(self.d0, -(age * 365 + rng.integers(0, 365, n)))
        lob = np.array([rng.choice(self.payers["states"][s]["lobs"]) if s != "TX" or is_child[i] else "MEDICAID"
                        for i, s in enumerate(state)])
        lob = np.where((state == "AZ") & (age >= 65), "DSNP", np.where((state == "AZ") & (lob == "DSNP"), "MEDICAID", lob))
        program = np.array([self.payers["states"][s]["program"] for s in state])
        program = np.where(lob == "STAR_KIDS", "STAR_KIDS", np.where(lob == "CHIP", "CHIP", program))
        lang = np.array([rng.choice(R.LANGS_BY_STATE[s][1], p=R.LANGS_BY_STATE[s][0]) for s in state])
        zips = np.array([self.fake.zipcode_in_state(s) for s in state])
        ingest = self._ingest(n, share=0.958)  # ~120 new enrollments a day
        mid = np.array([f"M{i:07d}" for i in range(n)])
        enroll = self._event_dates(ingest, 0, 3)
        self.out["member"] = pd.DataFrame({
            "member_id": mid, "payer_member_id": [f"{p[-3:]}{rng.integers(10**8, 10**9)}" for p in payer],
            "payer_code": payer, "state": state, "dob": dob, "sex": sex, "zip": zips, "language": lang,
            "lob": lob, "program": program, "enrollment_date": enroll, "ingest_day": ingest})
        tier = rng.choice(np.arange(1, 6), n, p=R.RISK_TIER_P)
        tier = np.where((age >= 55) & (tier < 5) & (rng.random(n) < 0.3), tier + 1, tier)
        self._tier = tier
        self._age = age

        # Eligibility spans: Medicaid churn (redetermination gaps); current span open-ended
        spans = []
        two = rng.random(n) < 0.5
        for i in range(n):
            start = enroll.iloc[i]
            if two[i] and ingest[i] == 0:
                s1 = start - timedelta(days=int(rng.integers(400, 700)))
                e1 = s1 + timedelta(days=int(rng.integers(120, 330)))
                spans.append((mid[i], payer[i], state[i], lob[i], program[i], s1, e1, "redetermination", 0))
            spans.append((mid[i], payer[i], state[i], lob[i], program[i], start, None, None, ingest[i]))
        el = pd.DataFrame(spans, columns=["member_id", "payer_code", "state", "lob", "program", "start_date",
                                          "end_date", "term_reason", "ingest_day"])
        # a few naturally overlapping spans (baseline ~0.2%)
        k = int(n * 0.002)
        ov = el[el["end_date"].isna()].sample(k, random_state=int(rng.integers(1e9))).copy()
        ov["start_date"] = ov["start_date"] - timedelta(days=30)
        ov["end_date"] = ov["start_date"] + timedelta(days=60)
        el = pd.concat([el, ov], ignore_index=True)
        el.insert(0, "span_id", [f"ES{i:07d}" for i in range(len(el))])
        self.out["eligibility_span"] = el

        # PCP attribution: member -> PCP in the same state -> practice; monthly snapshots (3 months)
        prov = self.out["provider"]
        pcps = prov[prov["is_pcp"]]
        by_state = {s: pcps[pcps["state"] == s] for s in R.STATES}
        pick = np.empty(n, dtype=object)
        prac = np.empty(n, dtype=object)
        for s in R.STATES:
            idx = np.where(state == s)[0]
            sel = by_state[s].iloc[rng.integers(0, len(by_state[s]), len(idx))]
            pick[idx] = sel["npi"].to_numpy()
            prac[idx] = sel["practice_id"].to_numpy()
        self._pcp_npi, self._practice = pick, prac
        months = [(self.d0.replace(day=1) - timedelta(days=62)).replace(day=1),
                  (self.d0.replace(day=1) - timedelta(days=1)).replace(day=1), self.d0.replace(day=1)]
        snaps = []
        for mth in months:
            active = ingest == 0
            snaps.append(pd.DataFrame({
                "member_id": mid[active], "payer_code": payer[active], "state": state[active],
                "pcp_npi": pick[active], "practice_id": prac[active], "effective_month": mth,
                "assignment_source": "payer_roster", "ingest_day": 0}))
        new = ingest > 0  # weekly roster refreshes pick up new members
        snaps.append(pd.DataFrame({
            "member_id": mid[new], "payer_code": payer[new], "state": state[new], "pcp_npi": pick[new],
            "practice_id": prac[new], "effective_month": months[-1], "assignment_source": "payer_roster",
            "ingest_day": np.minimum(((ingest[new] + 6) // 7) * 7, self.days)}))
        self.out["pcp_assignment"] = pd.concat(snaps, ignore_index=True)

        risk = []
        for j, mth in enumerate(months):
            noise = rng.normal(0, 0.15, n)
            risk.append(pd.DataFrame({
                "member_id": mid, "score_month": mth, "risk_tier": tier,
                "risk_score": np.round(tier * 0.8 + noise + rng.gamma(1.2, 0.3, n), 3),
                "predicted_unplanned_admit_flag": (tier >= 4) & (rng.random(n) < 0.45),
                "model_version": "rsk-2.3", "ingest_day": 0 if j < 2 else 1}))
        self.out["member_risk_score"] = pd.concat(risk, ignore_index=True)

    # ------------------------------------------------------------------ utilisation
    def _member_pick(self, n: int, weight_by_risk: bool = True, mask: np.ndarray | None = None) -> np.ndarray:
        w = R.RISK_UTIL_WEIGHT[self._tier - 1] if weight_by_risk else np.ones(len(self._tier))
        if mask is not None:
            w = w * mask
        return self.rng.choice(len(w), n, p=w / w.sum())

    def claims(self) -> None:
        rng, n = self.rng, SIZES["claim_header"]
        mem = self.out["member"]
        midx = self._member_pick(n)
        st = mem["state"].to_numpy()[midx]
        age = self._age[midx]
        cat_p = np.tile(np.array([0.36, 0.08, 0.04, 0.12, 0.025, 0.12, 0.2, 0.055]), (n, 1))
        child = age < 19
        cat_p[child, 1] += 0.12; cat_p[child, 5] -= 0.06; cat_p[child, 4] -= 0.012
        mother = (st == "TX") & (mem["sex"].to_numpy()[midx] == "F") & (age >= 18) & (age < 40)
        cat_p[mother, 2] += 0.12; cat_p[mother, 0] -= 0.06
        cat_p = np.clip(cat_p, 0.001, None)
        cat_p /= cat_p.sum(axis=1, keepdims=True)
        cats = np.array(R.SERVICE_CATEGORIES)[(cat_p.cumsum(axis=1) > rng.random((n, 1))).argmax(axis=1)]
        ingest = self._ingest(n)
        svc = self._event_dates(ingest, 5, 40, seasonal=False)
        # ED seasonality: re-date historical ER claims with winter weighting
        er = cats == "er"
        svc_er = self._event_dates(ingest[er], 5, 40, seasonal=True)
        svc = svc.to_numpy().copy()
        svc[er] = svc_er.to_numpy()
        hist_recv = pd.to_datetime(pd.Series(svc)) + pd.to_timedelta(rng.integers(5, 40, n), unit="D")
        day_recv = pd.to_datetime(pd.Series([R.day_date(d) for d in ingest]))
        recv = hist_recv.where(ingest == 0, day_recv)
        paid = np.round(np.array([R.PAID_BY_CATEGORY[c] for c in cats]) * rng.lognormal(0, 0.45, n), 2)
        prov = self.out["provider"]
        hdr = pd.DataFrame({
            "claim_id": [f"C{i:08d}" for i in range(n)], "member_id": mem["member_id"].to_numpy()[midx],
            "payer_code": mem["payer_code"].to_numpy()[midx], "state": st,
            "claim_type": np.where(np.isin(cats, ["inpatient"]) | (er & (rng.random(n) < 0.6)), "institutional",
                                   "professional"),
            "service_category": cats, "service_date": svc, "received_date": recv.dt.date.to_numpy(),
            "billing_npi": self._pcp_npi[midx], "practice_id": self._practice[midx],
            "total_allowed": np.round(paid * 1.18, 2), "total_paid": paid, "ingest_day": ingest})
        # non-PCP categories are billed by another provider in the same state
        other = ~np.isin(cats, ["pcp_visit", "well_child"])
        hdr.loc[other, "billing_npi"] = prov["npi"].to_numpy()[rng.integers(0, len(prov), other.sum())]
        self.out["claim_header"] = hdr

        nl = rng.choice([1, 2, 3, 4, 5, 6], n, p=[0.2, 0.22, 0.2, 0.16, 0.12, 0.1])
        rep = np.repeat(np.arange(n), nl)
        line_no = np.concatenate([np.arange(1, k + 1) for k in nl])
        lcat = cats[rep]
        cpt = np.array([R.CPT_BY_CATEGORY[c][i % len(R.CPT_BY_CATEGORY[c])] for c, i in
                        zip(lcat, rng.integers(0, 4, len(rep)))])
        dx = np.array([R.DX_BY_CATEGORY[c][i % len(R.DX_BY_CATEGORY[c])] for c, i in
                       zip(lcat, rng.integers(0, 5, len(rep)))])
        dx = np.where(rng.random(len(rep)) < 0.03, None, dx)  # baseline 3% missing dx
        dx2 = np.where(rng.random(len(rep)) < 0.55, None, np.array(R.DX_BY_CATEGORY["pcp_visit"])[
            rng.integers(0, 5, len(rep))])
        lpaid = np.round(paid[rep] / nl[rep] * rng.uniform(0.6, 1.4, len(rep)), 2)
        self.out["claim_line"] = pd.DataFrame({
            "claim_id": hdr["claim_id"].to_numpy()[rep], "line_no": line_no, "payer_code": hdr["payer_code"].to_numpy()[rep],
            "cpt_code": cpt, "dx_code_1": dx, "dx_code_2": dx2, "units": rng.choice([1, 1, 1, 2, 3], len(rep)),
            "paid_amount": lpaid, "service_date": hdr["service_date"].to_numpy()[rep],
            "ingest_day": ingest[rep]})

    def pharmacy(self) -> None:
        rng, n = self.rng, SIZES["rx_claim"]
        mem = self.out["member"]
        midx = self._member_pick(n)
        classes = list(R.DRUG_CLASSES)
        cls = rng.choice(classes, n, p=[0.16, 0.12, 0.16, 0.14, 0.16, 0.06, 0.20])
        ingest = self._ingest(n)
        self.out["rx_claim"] = pd.DataFrame({
            "rx_claim_id": [f"RX{i:08d}" for i in range(n)], "member_id": mem["member_id"].to_numpy()[midx],
            "payer_code": mem["payer_code"].to_numpy()[midx],
            "ndc": [f"{rng.integers(70000, 79999):05d}-{rng.integers(1000, 9999):04d}-{rng.integers(10, 99):02d}"
                    for _ in range(n)],
            "drug_class": cls, "fill_date": self._event_dates(ingest, 1, 4),
            "days_supply": rng.choice([30, 30, 30, 90, 14], n),
            "paid_amount": np.round(np.array([R.DRUG_CLASSES[c] for c in cls]) * rng.lognormal(0, 0.5, n), 2),
            "ingest_day": ingest})

    def labs(self) -> None:
        rng, n = self.rng, SIZES["lab_result"]
        mem = self.out["member"]
        adult = (self._age >= 18).astype(float)
        midx = self._member_pick(n, mask=adult)
        codes = list(R.LABS)
        loinc = rng.choice(codes, n, p=[0.4, 0.2, 0.2, 0.2])
        mu = np.array([R.LABS[c][2] for c in loinc]) + (self._tier[midx] - 3) * np.array(
            [R.LABS[c][3] for c in loinc]) * 0.25
        sd = np.array([R.LABS[c][3] for c in loinc])
        val = np.round(rng.normal(mu, sd), 1)
        val = np.where(loinc == "4548-4", np.clip(val, 4.2, 14.0), np.clip(val, 20, None))
        ingest = self._ingest(n)
        self.out["lab_result"] = pd.DataFrame({
            "lab_id": [f"L{i:08d}" for i in range(n)], "member_id": mem["member_id"].to_numpy()[midx],
            "state": mem["state"].to_numpy()[midx], "loinc_code": loinc,
            "test_name": [R.LABS[c][0] for c in loinc], "result_value": val,
            "unit": [R.LABS[c][1] for c in loinc], "result_date": self._event_dates(ingest, 1, 7),
            "source": rng.choice(["EHR", "HIE"], n, p=[0.7, 0.3]), "ingest_day": ingest})

    def adt(self) -> None:
        rng, n = self.rng, SIZES["adt_event"]
        mem = self.out["member"]
        midx = self._member_pick(n)
        st = mem["state"].to_numpy()[midx]
        ingest = self._ingest(n)
        d = self._event_dates(ingest, 0, 1, seasonal=True)
        hours = rng.integers(0, 24 * 60, n)
        ts = pd.to_datetime(pd.Series(d)) + pd.to_timedelta(hours, unit="m")
        self.out["adt_event"] = pd.DataFrame({
            "adt_id": [f"A{i:08d}" for i in range(n)], "member_id": mem["member_id"].to_numpy()[midx],
            "state": st, "hie_feed": [self.payers["states"][s]["hie_feed"] for s in st],
            "event_type": rng.choice(["A04", "A01", "A03"], n, p=[0.55, 0.15, 0.30]),
            "facility_type": rng.choice(["ED", "IP"], n, p=[0.78, 0.22]), "event_ts": ts,
            "ingest_day": ingest})

    # ------------------------------------------------------------------ quality
    def gaps(self) -> None:
        rng = self.rng
        mem = self.out["member"]
        age = self._age
        sex = mem["sex"].to_numpy()
        elig = {
            "WCV": (age >= 3) & (age <= 21), "W30": age <= 2, "CIS": age == 2, "BCS": (sex == "F") & (age >= 50) & (age <= 74),
            "GSD": (age >= 18) & (self._tier >= 2), "CBP": (age >= 18) & (self._tier >= 2), "AMR": (age >= 5) & (age <= 64),
            "PPC": (sex == "F") & (age >= 16) & (age <= 40)}
        p = np.array([0.30, 0.05, 0.03, 0.08, 0.16, 0.16, 0.08, 0.14])
        n = SIZES["care_gap"]
        measure = rng.choice(R.MEASURES, n, p=p / p.sum())
        midx = np.empty(n, dtype=int)
        for mcode in R.MEASURES:
            sel = measure == mcode
            midx[sel] = self._member_pick(int(sel.sum()), weight_by_risk=False, mask=elig[mcode].astype(float))
        ingest = self._ingest(n)
        # Gaps are only computed for members enrolled by that day (keeps D13 baseline clean)
        ingest = np.maximum(ingest, mem["ingest_day"].to_numpy()[midx])
        opened = self._event_dates(ingest, 0, 0)
        closed = rng.random(n) < 0.45
        cdate = pd.Series([o + timedelta(days=int(k)) if c else None
                           for o, c, k in zip(opened, closed, rng.integers(5, 120, n))])
        cdate = cdate.where(pd.to_datetime(cdate) <= pd.Timestamp(R.day_date(self.days)), None)
        self.out["care_gap"] = pd.DataFrame({
            "care_gap_id": [f"G{i:08d}" for i in range(n)], "member_id": mem["member_id"].to_numpy()[midx],
            "practice_id": self._practice[midx], "payer_code": mem["payer_code"].to_numpy()[midx],
            "measure_code": measure, "status": np.where(cdate.notna(), "closed", "open"),
            "opened_date": opened, "closed_date": cdate, "source": "careempower", "ingest_day": ingest})
        m = SIZES["payer_gap_file"]
        pidx = rng.integers(0, n, m)
        cg = self.out["care_gap"].iloc[pidx]
        ing = np.where(rng.random(m) < 0.8, 0, rng.choice([7, 14, 21], m))  # weekly payer gap files
        months = pd.to_datetime(pd.Series([R.day_date(d) for d in ing])).dt.to_period("M").dt.to_timestamp().dt.date
        self.out["payer_gap_file"] = pd.DataFrame({
            "payer_gap_id": [f"PG{i:08d}" for i in range(m)], "member_id": cg["member_id"].to_numpy(),
            "payer_code": cg["payer_code"].to_numpy(), "measure_code": cg["measure_code"].to_numpy(),
            "gap_status": np.where(rng.random(m) < 0.6, "OPEN", "MET"), "report_month": months,
            "ingest_day": ing})

    # ------------------------------------------------------------------ care model
    def care_model(self) -> None:
        rng = self.rng
        mem = self.out["member"]
        mid = mem["member_id"].to_numpy()
        n = SIZES["chw_encounter"]
        midx = self._member_pick(n)
        ing = self._ingest(n)
        self.out["chw_encounter"] = pd.DataFrame({
            "encounter_id": [f"CHW{i:07d}" for i in range(n)], "member_id": mid[midx],
            "chw_id": [f"CHW-{rng.integers(1, 180):03d}" for _ in range(n)], "encounter_date": self._event_dates(ing, 0, 2),
            "encounter_type": rng.choice(["phone", "home_visit", "clinic", "text"], n, p=[0.45, 0.25, 0.15, 0.15]),
            "outcome": rng.choice(["reached", "not_reached", "referred", "declined"], n, p=[0.5, 0.25, 0.18, 0.07]),
            "ingest_day": ing})
        n = SIZES["sdoh_screening"]
        midx = self._member_pick(n)
        ing = self._ingest(n)
        z = rng.choice(list(R.VALID_Z_CODES), n)
        self.out["sdoh_screening"] = pd.DataFrame({
            "screening_id": [f"SD{i:07d}" for i in range(n)], "member_id": mid[midx],
            "screening_date": self._event_dates(ing, 0, 3), "z_code": z,
            "need_category": [R.VALID_Z_CODES[c] for c in z], "referral_made": rng.random(n) < 0.4,
            "screening_tool": rng.choice(["AHC-HRSN", "PRAPARE"], n), "ingest_day": ing})
        n = SIZES["health_at_home_episode"]
        hi = np.where(self._tier >= 4)[0]
        sel = rng.choice(hi, n, replace=False)
        start = R.to_dates(self.d0, -rng.integers(30, 330, n))
        pre = rng.poisson(2.4, n)
        post = rng.binomial(pre, 0.55)  # lower post-episode ED use
        self.out["health_at_home_episode"] = pd.DataFrame({
            "episode_id": [f"HAH{i:05d}" for i in range(n)], "member_id": mid[sel], "state": mem["state"].to_numpy()[sel],
            "start_date": start, "end_date": [s + timedelta(days=84) for s in start],
            "status": np.where(pd.to_datetime(pd.Series(start)) + pd.Timedelta(days=84) < pd.Timestamp(self.d0),
                               "completed", "active"),
            "risk_tier_at_referral": self._tier[sel], "ed_visits_pre_90d": pre, "ed_visits_post_90d": post,
            "ingest_day": 0})

    # ------------------------------------------------------------------ finance
    def finance(self) -> None:
        rng = self.rng
        con = self.out["practice_contract"]
        rows = []
        for _, c in con.iterrows():
            for m in range(12):
                mth = (pd.Timestamp(self.d0) - pd.DateOffset(months=12 - m)).to_period("M").to_timestamp().date()
                rows.append((c["practice_id"], c["payer_code"], mth, rng.choice(["peds_bundle", "adult_bundle", "maternal_bundle"]),
                             round(float(rng.gamma(2.0, 1800)), 2)))
        inc = pd.DataFrame(rows, columns=["practice_id", "payer_code", "payment_month", "measure_bundle", "amount"])
        inc.insert(0, "payment_id", [f"IP{i:06d}" for i in range(len(inc))])
        self.out["practice_incentive_payment"] = inc.assign(ingest_day=0)
        n = len(con)
        bench = np.round(rng.normal(410, 45, n), 2)
        actual = np.round(bench * rng.normal(0.97, 0.05, n), 2)
        self.out["shared_savings_settlement"] = pd.DataFrame({
            "settlement_id": [f"SS{i:04d}" for i in range(n)], "practice_id": con["practice_id"],
            "payer_code": con["payer_code"], "performance_year": self.d0.year - 1, "benchmark_pmpm": bench,
            "actual_pmpm": actual, "member_months": rng.integers(800, 9000, n),
            "gross_savings": np.round((bench - actual) * rng.integers(800, 9000, n), 2),
            "quality_gate_met": rng.random(n) < 0.8, "ingest_day": 0})
        s = self.out["shared_savings_settlement"]
        s["practice_share_amount"] = np.round(np.where(s["quality_gate_met"], s["gross_savings"] * con["practice_share_pct"], 0), 2)

    def all(self) -> dict[str, pd.DataFrame]:
        self.network(); self.members(); self.claims(); self.pharmacy(); self.labs(); self.adt()
        self.gaps(); self.care_model(); self.finance()
        return self.out
