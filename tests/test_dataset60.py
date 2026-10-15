"""Tests for the 60-ticket dataset (DISP-101..DISP-160). Offline, no API key.

Place in tests/. Needs the dataset fixtures copied into fixtures/ (see dataset60/README.md).
"""
import asyncio, glob, json, pathlib, sys
from collections import Counter, defaultdict

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.orchestrator import resolve  # noqa: E402

FX = ROOT / "fixtures"
IDS = [f"DISP-{k}" for k in range(101, 161)]
CATS = ["route_deviation", "no_show_charge", "property_damage", "safety_incident"]


def load(p):
    return json.loads(pathlib.Path(p).read_text())


def run(did, lang="en"):
    async def go():
        return [e async for e in resolve(dispute_id=did, mode="deterministic", lang=lang)]
    return asyncio.run(go())


def final(evs):
    errs = [e for e in evs if e["type"] == "error"]
    assert not errs, errs
    return [e for e in evs if e["type"] == "ruling"][0]["ruling"]


# ------------------------------------------------------------- data integrity
def test_dataset_shape():
    tickets = [load(FX / "disputes" / f"{i}.json") for i in IDS]
    assert len({t["trip_id"] for t in tickets}) == 60
    by = defaultdict(Counter)
    for t in tickets:
        by[t["rider_id"]][t["dispute_type"]] += 1
    assert len(by) == 6
    for rid, c in by.items():
        assert sum(c.values()) == 10, rid
        for cat in CATS:
            assert c[cat] >= 2, (rid, cat)
    assert Counter(t["dispute_type"] for t in tickets) == {c: 15 for c in CATS}


def test_parties_consistent_with_tickets_and_profiles():
    parties = load(FX / "trip_parties.json")
    for i in IDS:
        t = load(FX / "disputes" / f"{i}.json")
        p = parties[t["trip_id"]]
        assert (p["rider_id"], p["driver_id"]) == (t["rider_id"], t["driver_id"])
        trip = load(FX / "trips" / f"{t['trip_id']}.json")
        assert trip["trip_data"]["rider_id"] == t["rider_id"] and trip["trip_data"]["driver_id"] == t["driver_id"]
    for pf in glob.glob(str(FX / "profiles" / "riders" / "*.json")) + glob.glob(str(FX / "profiles" / "drivers" / "*.json")):
        d = load(pf)
        assert d.get("name"), pf          # every profile carries the name the UI shows
    for rf in glob.glob(str(FX / "profiles" / "riders" / "*.json")):
        d = load(rf)
        n_trips = sum(1 for p in parties.values() if p["rider_id"] == d["rider_id"])
        assert d["total_trips"] >= n_trips, (d["rider_id"], d["total_trips"], n_trips)   # no rider has fewer trips than disputed trips


def test_ground_truth_not_in_trip_or_dispute_files():
    for i in IDS:
        t = load(FX / "disputes" / f"{i}.json")
        blob = json.dumps(t) + json.dumps(load(FX / "trips" / f"{t['trip_id']}.json"))
        for banned in ("expected_ruling", "recommended_ruling", "ruling_rationale", "reroute_justified", "must_escalate"):
            assert banned not in blob, (i, banned)


# ------------------------------------------------------------- rulings
@pytest.mark.parametrize("did", IDS)
@pytest.mark.parametrize("lang", ["en", "zh"])
def test_offline_ruling_matches_policy(did, lang):
    e = load(FX / "expected" / f"{did}.json")
    r = final(run(did, lang))
    esc = r["ruling"] == "escalated" or bool(r.get("escalation_required"))
    if e["must_escalate"]:
        assert esc, "a deterministic escalation trigger must reach a human"
    if r["ruling"] == "escalated" and e["ruling"] != "escalated":
        # Only a party with a fraud flag (95% confidence bar, policy 6.3) may escalate a case the policy rules on.
        assert e["fraud_flag_party"], "unexpected escalation on a rider without a fraud flag"
        got = r["recommendation"]                       # the AI's recommendation is kept for the human reviewer
        assert got["ruling"] == e["ruling"]
        assert abs((got["refund_amount"] or 0) - (e["refund_amount"] or 0)) < 0.02
        return
    assert r["ruling"] == e["ruling"]
    if e["refund_amount"] is None:
        assert r["refund_amount"] is None
    else:
        assert abs(r["refund_amount"] - e["refund_amount"]) < 0.02
    if e.get("goodwill_credit"):
        assert abs((r.get("goodwill_credit") or 0) - e["goodwill_credit"]) < 0.02


def test_safety_cases_never_get_an_ai_ruling():
    for did in IDS:
        if load(FX / "expected" / f"{did}.json")["scenario"] in ("reckless_speeding", "harassment_chat", "verbal_abuse", "collision", "distracted_driving", "unsafe_detour_night", "suspected_intoxication"):
            r = final(run(did))
            assert r["ruling"] == "escalated" and r["refund_amount"] is None
