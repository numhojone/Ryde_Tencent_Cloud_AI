"""Story in, structured ticket out, trip auto-matched. Offline (no API key). Run: pytest -q"""
import asyncio, json, pathlib, sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app.agents.intake import IntakeAgent, classify_by_rules  # noqa: E402
from app.extract import extract_facts  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestrator import resolve  # noqa: E402
from app.trip_match import match_trip  # noqa: E402
from app.tools.fixtures import load_rider_trips  # noqa: E402

TRIPS = load_rider_trips()
SAMPLE_FIELDS = set().union(*(set(json.loads(p.read_text())) for p in (ROOT / "fixtures" / "disputes").glob("DISP-*.json"))) - {"_source"}


def run_story(text, trip_id=None, lang="en"):
    async def go():
        return [e async for e in resolve(None, mode="deterministic", draft={"trip_id": trip_id, "complaint": text}, lang=lang)]
    evs = asyncio.run(go())
    assert not [e for e in evs if e["type"] == "error"], evs
    return evs


def of(evs, kind):
    return [e for e in evs if e["type"] == kind]


def auto_match(text):
    cat, signals = classify_by_rules(text)
    return match_trip(text, extract_facts(text), TRIPS, category=cat if signals else None)


STORIES = [
    # route deviation
    ("en", "The driver took a long detour from Orchard Central to Changi Airport and I was overcharged.", "TRIP-2026-09871"),
    ("singlish", "Uncle drive from Orchard Central to Changi Airport go round and round sia, kena overcharge.", "TRIP-2026-09871"),
    ("ta", "ஓட்டுநர் Orchard Central இலிருந்து Changi Airport வரை நீண்ட வழியில் சென்றார், அதிக கட்டணம்.", "TRIP-2026-09871"),
    ("zh", "司机从Orchard Central到樟宜机场绕了一大圈，多收了我钱", "TRIP-2026-09871"),
    # no-show
    ("en", "I was at Tiong Bahru Plaza on time but the driver never came and I got a $5 cancellation fee.", "TRIP-2026-09945"),
    ("singlish", "Driver never turn up at Tiong Bahru Plaza leh, I wait so long still kena charge $5 cancel fee.", "TRIP-2026-09945"),
    ("ms", "Saya tunggu di Tiong Bahru Plaza tetapi pemandu tidak datang, dan saya dikenakan caj pembatalan $5.", "TRIP-2026-09945"),
    ("ta", "நான் Tiong Bahru Plaza இல் காத்திருந்தேன், ஓட்டுநர் வரவில்லை, ஆனாலும் $5 ரத்து கட்டணம் வசூலிக்கப்பட்டது.", "TRIP-2026-09945"),
    ("zh", "我在中峇鲁广场等了很久司机没来，还扣了5元取消费", "TRIP-2026-09945"),
    # fare
    ("en", "The final fare was $16.50 but the upfront quote was $12.00. Nobody told me the price had gone up.", "TRIP-2026-10023"),
    ("singlish", "Wah the app quote me $12.00 then end up charge $16.50, never tell me surge one leh.", "TRIP-2026-10023"),
    ("zh", "预付报价是12元，最后收了16.50元，没人告诉我加价", "TRIP-2026-10023"),
    # cleaning fee
    ("en", "I was charged a S$35 cleaning fee but I did not spill or dirty anything in the car.", "TRIP-2026-10201"),
    ("ms", "Saya dikenakan yuran pembersihan $35 tetapi kereta tidak kotor.", "TRIP-2026-10201"),
    ("zh", "我没有弄脏车，却被收了35元清洁费", "TRIP-2026-10201"),
    # safety
    ("en", "The driver was speeding over 100 km/h on the expressway and ran a red light. I felt unsafe.", "TRIP-2026-10305"),
    ("ms", "Pemandu memandu laju lebih 100 km/j dan langgar lampu merah, saya rasa tak selamat.", "TRIP-2026-10305"),
    ("zh", "司机超速开到100多公里每小时，还闯红灯，我很害怕", "TRIP-2026-10305"),
]


@pytest.mark.parametrize("lang,text,trip", STORIES, ids=[f"{s[0]}-{s[2][-5:]}-{i}" for i, s in enumerate(STORIES)])
def test_auto_match_picks_the_right_trip(lang, text, trip):
    m = auto_match(text)
    assert m["trip_id"] == trip, m["candidates"]
    assert m["confidence"] > 0 and m["reasons"]


def test_auto_match_end_to_end_emits_trip_matched_and_rules():
    evs = run_story("The final fare was $16.50 but the upfront quote was $12.00. Nobody told me the price had gone up.")
    tm = of(evs, "trip_matched")[0]
    assert tm["trip_id"] == "TRIP-2026-10023" and tm["route"] and tm["candidates"]
    ticket = of(evs, "ticket_filed")[0]["ticket"]
    assert ticket["trip_id"] == "TRIP-2026-10023" and ticket["dispute_type"] == "fare_dispute"
    assert {c["status"] for c in ticket["claim_check"]} == {"consistent"}
    r = of(evs, "ruling")[0]["ruling"]
    assert r["ruling"] == "upheld" and abs(r["refund_amount"] - 4.5) < 0.02


@pytest.mark.parametrize("text", [
    "Something went wrong with my last ride and I want my money back.",
    "I am not happy with the driver.",
])
def test_ambiguous_story_is_unresolved_and_never_ruled(text):
    evs = run_story(text)
    un = of(evs, "trip_unresolved")
    assert un and un[0]["message"] and len(un[0]["candidates"]) == 3
    assert not of(evs, "trip_matched") and not of(evs, "ticket_filed") and not of(evs, "ruling")
    assert evs[-1]["type"] == "done"
    assert not any(e.get("agent") in ("rider_advocate", "driver_advocate", "judge") for e in evs)


def test_two_equally_likely_trips_are_not_guessed():
    # Every no-show trip in the (unscoped) pool charged S$5 and the story names no place: do not pick one.
    m = auto_match("The app charged me a S$5 cancellation fee but I never saw any car.")
    assert m["trip_id"] is None
    assert {c["trip_id"] for c in m["candidates"][:3]} == {"TRIP-2026-09945", "TRIP-2026-10410", "TRIP-2026-30201"}


def test_explicit_trip_id_bypasses_matching():
    # The story names another trip's places; the given trip_id still wins and no matching runs.
    evs = run_story("I was at Tiong Bahru Plaza and the driver never came.", trip_id="TRIP-2026-10410")
    assert not of(evs, "trip_matched") and not of(evs, "trip_unresolved")
    assert of(evs, "ticket_filed")[0]["ticket"]["trip_id"] == "TRIP-2026-10410"
    assert of(evs, "ruling")


def test_cancelled_trip_cannot_be_a_route_deviation():
    t = next(x for x in TRIPS if x["trip_id"] == "TRIP-2026-09945")
    m = match_trip("The driver took a detour and overcharged me at Tiong Bahru Plaza", {}, [t], category="route_deviation")
    assert m["candidates"][0]["score"] < 3 and m["trip_id"] is None


@pytest.mark.parametrize("text", [
    "The fare was $16.50 but the quote was $12.00, and the driver threatened me.",
    "司机超速开到100多公里每小时，还闯红灯，我很害怕",
])
def test_safety_indicators_force_safety_case_file(text):
    evs = run_story(text)
    ticket = of(evs, "ticket_filed")[0]["ticket"]
    assert ticket["dispute_type"] == "safety_incident"
    assert of(evs, "triage_result")[0]["dispute_type"] == "safety_incident"
    assert ticket["extracted_facts"]["safety_indicators"]
    r = of(evs, "ruling")[0]["ruling"]
    assert r["ruling"] == "escalated" and r["refund_amount"] is None and r["case_file"]
    assert not any(e.get("agent") in ("judge", "rider_advocate", "driver_advocate") for e in evs)


def test_ticket_has_official_fields_and_verbatim_description():
    text = "The driver took a long detour  from Orchard Central to Changi Airport T3 and charged me $35, i usually pay $28 !!"
    evs = run_story(text)
    t = of(evs, "ticket_filed")[0]["ticket"]
    assert SAMPLE_FIELDS <= set(t), SAMPLE_FIELDS - set(t)
    assert t["description"] == text
    assert t["status"] == "open" and t["filed_by"] == "rider"
    assert {"extracted_facts", "missing_info", "claim_check"} <= set(t)
    f = t["extracted_facts"]
    assert f["pickup_place"] == "Orchard Central" and f["dropoff_place"] == "Changi Airport T3"
    assert f["charged_amount"] == 35.0 and f["quoted_amount"] == 28.0
    assert t["requested_amount"] == 7.0


def test_facts_are_never_invented():
    f = extract_facts("I am not happy with the driver.")
    for k in ("quoted_amount", "charged_amount", "claimed_difference", "fee_type", "pickup_place", "dropoff_place"):
        assert f[k] is None, k
    assert f["time_mentions"] == [] and f["safety_indicators"] == []


def test_claim_check_flags_a_discrepancy_and_does_not_change_the_ruling():
    honest = run_story("The final fare was $16.50 but the upfront quote was $12.00.", trip_id="TRIP-2026-10023")
    inflated = run_story("The final fare was $20.00 but the upfront quote was $12.00.", trip_id="TRIP-2026-10023")
    cc = {c["claim"]: c for c in of(inflated, "ticket_filed")[0]["ticket"]["claim_check"]}
    assert cc["charged_amount"]["status"] == "discrepancy" and cc["charged_amount"]["record_value"] == 16.5
    assert cc["quoted_amount"]["status"] == "consistent"
    a, b = of(honest, "ruling")[0]["ruling"], of(inflated, "ruling")[0]["ruling"]
    assert (a["ruling"], a["refund_amount"]) == (b["ruling"], b["refund_amount"])
    # the agents that rule never see claim_check
    assert "claim_check" not in json.dumps([e for e in inflated if e.get("agent") in ("judge", "rider_advocate", "driver_advocate")])


def test_llm_output_is_grounded_and_malformed_facts_fall_back_to_rules():
    ia = IntakeAgent(lambda e: None, mode="deterministic")
    text = "The final fare was $16.50 but the upfront quote was $12.00."
    ctx = {"draft": {"complaint": text, "trip_id": "TRIP-2026-10023"}}
    invented = ia._fill_defaults({"dispute_type": "fare_dispute", "requested_amount": 99,
                                  "extracted_facts": {"quoted_amount": 12.0, "charged_amount": 99.0, "pickup_place": "Bugis Junction"}}, ctx)
    f = invented["extracted_facts"]
    assert f["quoted_amount"] == 12.0 and f["charged_amount"] == 16.5 and f["pickup_place"] is None
    assert invented["requested_amount"] == 4.5
    malformed = ia._fill_defaults({"dispute_type": "fare_dispute", "extracted_facts": {"quoted_amount": "twelve"}}, ctx)
    assert malformed["extracted_facts"]["quoted_amount"] == 12.0 and malformed["extracted_facts"]["charged_amount"] == 16.5


def test_api_trip_id_optional_and_unresolved_has_no_ruling():
    from session import login
    c = login(TestClient(app), "R-3312")             # matching is scoped to the signed-in rider's trips
    r = c.post("/api/file", json={"complaint": "I want my money back.", "mode": "deterministic"}).json()
    assert r["status"] == "trip_unresolved" and r["ruling"] is None and r["candidates"]
    r = c.post("/api/file", json={"complaint": "I was charged a S$35 cleaning fee but I never spilled anything.",
                                  "trip_id": "auto", "mode": "deterministic"}).json()
    assert r["trip_match"]["trip_id"] == "TRIP-2026-10201" and r["filed_ticket"]["dispute_type"] == "property_damage"
    assert r["ruling"]["ruling"] == "upheld"
    # another rider's trip is refused; its owner can file against it
    assert c.post("/api/file", json={"complaint": "The driver took a long way round.", "trip_id": "TRIP-2026-09871",
                                     "mode": "deterministic"}).status_code == 403
    login(c, "R-4521")
    r = c.post("/api/file", json={"complaint": "The driver took a long way round.", "trip_id": "TRIP-2026-09871",
                                  "mode": "deterministic"}).json()
    assert r["ticket"]["trip_id"] == "TRIP-2026-09871" and r["trip_match"] is None
    with c.stream("GET", "/api/file/stream", params={"complaint": "I want my money back.", "mode": "deterministic"}) as s:
        body = "".join(s.iter_text())
    kinds = [json.loads(line[6:])["type"] for line in body.splitlines() if line.startswith("data: ")]
    assert "trip_unresolved" in kinds and kinds[-1] == "done" and "ruling" not in kinds


def test_ground_truth_never_in_story_events():
    evs = run_story("Driver took a long detour from Orchard Central to Changi Airport T3 and overcharged me.")
    blob = json.dumps(evs)
    assert "recommended_ruling" not in blob and "fixtures/expected" not in blob and "case_metadata" not in blob
