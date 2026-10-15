"""Offline tests (no API key). Run: pytest -q"""
import asyncio, json, pathlib, re, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.orchestrator import resolve  # noqa: E402
from app import thresholds  # noqa: E402
from app.agents import analysis as A  # noqa: E402
from app.agents.intake import classify_by_rules, detect_safety  # noqa: E402
from app import safety_net  # noqa: E402

# The official samples and the first synthetic cases (DISP-001 to 006). The 60 dataset cases (DISP-101 to 160) have
# their own, richer comparison in tests/test_dataset60.py.
EXPECTED = {p.stem: json.loads(p.read_text()) for p in sorted((ROOT / "fixtures" / "expected").glob("DISP-00*.json"))}


def run(did, lang="en"):
    async def go():
        evs = []
        async for e in resolve(dispute_id=did, mode="deterministic", lang=lang):
            evs.append(e)
        return evs
    return asyncio.run(go())


def final(evs):
    errs = [e for e in evs if e["type"] == "error"]
    assert not errs, errs
    return [e for e in evs if e["type"] == "ruling"][0]["ruling"]


@pytest.mark.parametrize("did", sorted(EXPECTED))
@pytest.mark.parametrize("lang", ["en", "zh"])
def test_offline_ruling_matches_expected(did, lang):
    r = final(run(did, lang)); e = EXPECTED[did]
    assert r["ruling"] == e["ruling"]
    if e["refund_amount"] is None:
        assert r["refund_amount"] is None
    else:
        assert abs(r["refund_amount"] - e["refund_amount"]) < 0.02


def test_expected_answers_are_not_exposed_to_agents():
    evs = run("DISP-001")
    blob = json.dumps(evs)
    assert "recommended_ruling" not in blob and "fixtures/expected" not in blob


def test_english_output_has_no_chinese():
    for did in EXPECTED:
        txt = json.dumps(run(did, "en"), ensure_ascii=False)
        assert not re.search("[一-鿿]", txt), did


def test_route_over_2km_needs_human_approval():
    r = final(run("DISP-001"))
    assert r["escalation_required"] and r["ruling"] == "partial"
    assert r["policy_path"]["human_approval_only"]


def test_safety_never_ruled_by_ai():
    evs = run("DISP-005")
    r = final(evs)
    assert r["ruling"] == "escalated" and r["refund_amount"] is None and r["case_file"]
    assert not any(e.get("agent") in ("judge", "rider_advocate", "driver_advocate") for e in evs)


def test_thin_evidence_is_blocked_by_safety_net():
    r = final(run("DISP-006"))
    assert r["safety_net"]["triggered"] and r["ruling"] == "escalated"
    assert r["model_assessment"]["ruling"] in ("upheld", "rejected", "partial")


def test_threshold_rules():
    f = {"deviation_km": 1.8}
    assert not thresholds.assess("route_deviation", f, 0.9, [{}])["escalation_required"]
    assert thresholds.assess("route_deviation", f, 0.7, [{}])["escalation_required"]
    assert thresholds.assess("fare_dispute", {"difference": 60}, 0.99, [{}])["escalation_required"]
    assert not thresholds.assess("fare_dispute", {"difference": 4.5}, 0.2, [{}])["escalation_required"]
    assert thresholds.assess("fare_dispute", {"difference": 20}, 0.85, [{}])["required_confidence"] == 0.8
    # 6.3: a fraud flag raises the bar to 95% regardless of value
    t = thresholds.assess("no_show_charge", {}, 0.9, [{"fraud_flags": 1}])
    assert t["escalation_required"] and t["required_confidence"] == 0.95
    assert thresholds.assess("property_damage", {"claim_type": "repair", "claimed_amount": 120}, 0.99, [{}])["escalation_required"]
    assert thresholds.assess("safety_incident", {}, 1.0, [{}])["escalation_required"]


def test_calibration_and_fraud_helpers():
    assert A.calibrate_confidence(1, 1, 1, 1) == 0.97
    assert A.has_fraud_flag({"fraud_flags": 1}) and not A.has_fraud_flag({"fraud_flags": 0})


@pytest.mark.parametrize("text,exp", [
    ("The driver took a long way round and charged me extra", "route_deviation"),
    ("I waited 15 min nobody came but got a cancellation fee", "no_show_charge"),
    ("The fare was 16.50 but the quote was 12, surge never shown", "fare_dispute"),
    ("They charged me a cleaning fee but I never spilled anything", "property_damage"),
    ("He was speeding and I felt unsafe", "safety_incident"),
    ("司机绕路多收钱", "route_deviation"), ("我没有弄脏车却被收清洁费", "property_damage"),
    ("Pemandu tidak datang tetapi saya dikenakan caj pembatalan", "no_show_charge"),
])
def test_intake_rules(text, exp):
    assert classify_by_rules(text, "completed")[0] == exp


def test_safety_flag_overrides_other_signals():
    assert classify_by_rules("Fare was higher than the quote and the driver threatened me")[0] == "safety_incident"
    assert detect_safety("I felt unsafe")


def test_safety_net_rule_a_and_b():
    async def go():
        ruling = {"ruling": "upheld", "refund_amount": 5.0, "confidence_score": 1.0, "reasoning": "x", "evidence_cited": ["a", "A", "b"]}
        return await safety_net.apply(ruling, "TRIP-2026-09945", None, "en", "no_show_charge")
    r = asyncio.run(go())
    assert r["safety_net"]["triggered"]            # only 2 distinct points after de-duplication (Rule A)
    assert r["ruling"] == "escalated" and r["model_assessment"]["ruling"] == "upheld"
