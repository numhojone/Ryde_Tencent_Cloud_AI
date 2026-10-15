"""Strict rider scoping, exhaustively: for every one of the 6 riders and every trip that is not theirs, every route
(chat story, picker / case creation, trip endpoints, tools, case-QA / console / driver view) fails with 404 or the
"only your account" reply. Plus: what a (mocked) LLM is sent contains only the signed-in rider's data."""
import asyncio
import json
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from data60 import dataset_trip_ids, evidence, load  # noqa: E402
from app.main import app  # noqa: E402
from app.rider_match import find_trip  # noqa: E402
from app.tools import call_tool  # noqa: E402
from app.tools.fixtures import load_rider_trips, rider_scope  # noqa: E402
from session import login  # noqa: E402

DATA = load()
RIDERS = sorted(DATA["riders"])
TRIPS = sorted(DATA["trips"])
TRIP_TOOLS = ("get_trip_data", "get_gps_telemetry", "get_chat_logs", "get_app_events", "get_traffic_reference",
              "get_fare_breakdown", "get_damage_evidence")
ONLY = "I can only look at trips on your account."
COUNTS: dict[str, int] = {}


def foreign(rid):
    return [t for t in TRIPS if DATA["trips"][t]["rider_id"] != rid]


def count(key, n=1):
    COUNTS[key] = COUNTS.get(key, 0) + n


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def cases(client):
    """One escalated case per rider, opened by that rider (on a route deviation over 2 km or a safety ride)."""
    out = {}
    for rid in RIDERS:
        login(client, rid)
        trip = next(t["trip_id"] for t in load_rider_trips(rid) if t["ticket_type"] == "safety_incident")
        cid = client.post("/api/cases", json={"story": "My driver was driving dangerously and I felt unsafe.",
                                              "trip_id": trip, "mode": "deterministic"}).json()["id"]
        for _ in range(400):
            if client.get(f"/api/cases/{cid}").json()["status"] not in ("intake", "in_review"):
                break
        out[rid] = cid
    return out


@pytest.mark.parametrize("rid", RIDERS)
def test_chat_story_never_matches_another_riders_trip(rid):
    for tid in foreign(rid):
        rec = evidence()[tid]["trip_data"]
        for story in (f"Please check {tid}, the driver took a detour.",
                      f"{DATA['riders'][DATA['trips'][tid]['rider_id']]['name']}'s trip from "
                      f"{rec['pickup_location']['name']} was a mess."):
            r = find_trip(story, rid)
            assert r["state"] == "foreign" and r["message"] == ONLY and not r["candidates"] and not r["recent"]
            count("chat story (trip id or other rider named)")
    # the rider's own list holds only their rides
    r = find_trip("Show me all my rides.", rid)
    assert {c["trip_id"] for c in r["candidates"]} == {t for t in TRIPS if DATA["trips"][t]["rider_id"] == rid}


@pytest.mark.parametrize("rid", RIDERS)
def test_story_with_another_riders_places_and_date_still_only_matches_own_rides(rid):
    mine = {t for t in TRIPS if DATA["trips"][t]["rider_id"] == rid}
    for tid in foreign(rid):
        rec = evidence()[tid]["trip_data"]
        when = rec.get("start_time") or rec.get("scheduled_time")
        story = (f"On {int(when[8:10])} Sep the driver took a long detour from {rec['pickup_location']['name']} "
                 f"to {rec['dropoff_location']['name']}.")
        r = find_trip(story, rid)
        assert {c["trip_id"] for c in r["candidates"] + r["recent"]} <= mine
        count("chat story (other rider's places and date)")


@pytest.mark.parametrize("rid", RIDERS)
def test_trip_endpoints_refuse_every_foreign_trip(client, rid):
    login(client, rid)
    for tid in foreign(rid):
        assert client.post("/api/cases", json={"story": "detour", "trip_id": tid, "mode": "deterministic"}).status_code == 404
        assert client.post("/api/file", json={"complaint": "detour", "trip_id": tid, "mode": "deterministic"}).status_code == 404
        did = DATA["trips"][tid]["dispute_id"]
        assert client.post(f"/api/resolve/{did}", params={"mode": "deterministic"}).status_code == 404
        count("picker / case creation", 1); count("trip endpoints (/api/file, /api/resolve)", 2)
    assert {t["rider_id"] for t in client.get("/api/trips").json()["trips"]} == {rid}
    assert {d["dispute_id"] for d in client.get("/api/disputes").json()["disputes"]} >= {
        t["dispute_id"] for t in DATA["trips"].values() if t["rider_id"] == rid}
    assert all(d["dispute_id"] not in {t["dispute_id"] for t in DATA["trips"].values() if t["rider_id"] != rid}
               for d in client.get("/api/disputes").json()["disputes"])


@pytest.mark.parametrize("rid", RIDERS)
def test_tools_refuse_every_foreign_trip_like_a_missing_one(rid):
    with rider_scope(rid):
        for tid in foreign(rid):
            for tool in TRIP_TOOLS:
                r, missing = call_tool(tool, {"trip_id": tid}), call_tool(tool, {"trip_id": "TRIP-2026-0000"})
                assert not r["ok"] and r["error"].replace(tid, "X") == missing["error"].replace("TRIP-2026-0000", "X")
                count("tools")
        for other in RIDERS:
            if other != rid:
                assert not call_tool("get_rider_profile", {"rider_id": other})["ok"]
                count("tools (other rider's profile)")


@pytest.mark.parametrize("rid", RIDERS)
def test_case_endpoints_refuse_every_foreign_case(client, cases, rid):
    login(client, rid)
    for owner, cid in cases.items():
        if owner == rid:
            assert client.get(f"/api/cases/{cid}").status_code == 200
            continue
        for method, path, body in (("get", f"/api/cases/{cid}", None), ("get", f"/api/cases/{cid}/events", None),
                                   ("post", f"/api/cases/{cid}/rider-message", {"text": "hi"}),
                                   ("post", f"/api/cases/{cid}/human/ask", {"question": "Did the driver call?"}),
                                   ("post", f"/api/cases/{cid}/human/route", {"question": "Did the driver call?"}),
                                   ("post", f"/api/cases/{cid}/human/rephrase", {"text": "hi"}),
                                   ("post", f"/api/cases/{cid}/human/decision", {"action": "reject"}),
                                   ("post", "/api/driver-view/reply", {"case_id": cid, "text": "hi"})):
            r = getattr(client, method)(path, **({"json": body} if body else {}))
            assert r.status_code == 404, (rid, path, r.status_code)
            count("case-QA / console / driver view / case endpoints")
        assert cid not in {c["id"] for c in client.get("/api/cases").json()["cases"]}
        assert cid not in {c["case_id"] for c in client.get("/api/driver-view").json()["cases"]}


# ---------------------------------------------------------------- what reaches a model

class FakeLLM:
    """Stands in for the OpenAI-compatible client: records every prompt, asks for tools on the rider's own trip and on
    another rider's trip (to prove the tools refuse it), then returns a minimal valid answer per agent."""

    def __init__(self, own_trip, foreign_trip, foreign_rider):
        self.own, self.foreign, self.foreign_rider = own_trip, foreign_trip, foreign_rider
        self.prompts: list[list[dict]] = []

    async def chat(self, messages, tools=None, **kw):
        from app.llm import LLMResponse, ToolCall
        self.prompts.append([dict(m) for m in messages])
        sysmsg = messages[0]["content"]
        if tools and not any(m.get("role") == "tool" for m in messages):
            calls = [ToolCall(id="c1", name="get_trip_data", arguments={"trip_id": self.own}),
                     ToolCall(id="c2", name="get_trip_data", arguments={"trip_id": self.foreign}),
                     ToolCall(id="c3", name="get_rider_profile", arguments={"rider_id": self.foreign_rider})]
            return LLMResponse(content=None, tool_calls=calls)
        if "INTAKE" in sysmsg:
            out = {"dispute_type": "route_deviation", "classification_confidence": 0.9, "classification_reasoning": "detour",
                   "normalized_claim": "Longer route", "detected_signals": ["detour"]}
        elif "ADVOCATE" in sysmsg:
            side = "rider" if "RIDER ADVOCATE" in sysmsg else "driver"
            out = {"agent": f"{side}_advocate", "side": side, "claim": "c", "requested_outcome": "o", "reasoning": "r"}
        elif "JUDGE" in sysmsg:
            out = {"dispute_id": "X", "ruling": "partial", "refund_amount": 1.0, "confidence_score": 0.9, "reasoning": "r",
                   "evidence_cited": ["a", "b", "c"]}
        else:
            out = {"text": "ok", "answer": "ok", "citations": [], "found": True}
        return LLMResponse(content=json.dumps(out))


def _text(prompts):
    """Everything sent to the model except the model's own tool-call arguments."""
    return json.dumps([[{k: v for k, v in m.items() if k != "tool_calls"} for m in p] for p in prompts], ensure_ascii=False)


@pytest.mark.parametrize("rid", RIDERS)
def test_llm_prompts_hold_only_the_signed_in_riders_trips(client, monkeypatch, rid):
    import app.agents.base as base
    from app.config import settings
    mine = [t for t in load_rider_trips(rid) if t["ticket_type"] == "route_deviation"][0]
    other_tid = foreign(rid)[0]
    other_rider = DATA["trips"][other_tid]["rider_id"]
    fake = FakeLLM(mine["trip_id"], other_tid, other_rider)
    monkeypatch.setattr(base, "llm_client", fake)
    monkeypatch.setattr(settings, "llm_api_key", settings.llm_api_key or "test-key")
    login(client, rid)
    cid = client.post("/api/cases", json={"story": "The driver took a long detour and charged me more.",
                                          "trip_id": mine["trip_id"], "mode": "llm"}).json()["id"]
    for _ in range(600):
        if client.get(f"/api/cases/{cid}").json()["status"] not in ("intake", "in_review"):
            break
    assert fake.prompts, "the model was never called"
    text = _text(fake.prompts)
    # no other rider's trip ids beyond the refused request, no other rider's names, records or tickets
    ids = set(re.findall(r"TRIP-2026-\d{4,5}", text))
    assert ids <= {mine["trip_id"], other_tid}
    assert f"Data not found: trips/{other_tid}.json" in text                  # the only trace of the foreign trip
    assert text.count(other_tid) == text.count(f"Data not found: trips/{other_tid}.json")
    foreign_rec = evidence()[other_tid]["trip_data"]
    assert (foreign_rec.get("start_time") or foreign_rec["scheduled_time"]) not in text
    for r in RIDERS:
        if r != rid:
            assert DATA["riders"][r]["name"] not in text
            for t in foreign(rid):
                assert DATA["trips"][t]["dispute_id"] not in text
    count("LLM prompts inspected", len(fake.prompts))


def test_report_isolation_counts():
    """Prints how many isolation checks ran (pytest -s shows it)."""
    total = sum(v for k, v in COUNTS.items() if not k.startswith("LLM"))
    print("\nisolation checks:", json.dumps(COUNTS, indent=1), "\ntotal refusals checked:", total)
    assert total > 0
