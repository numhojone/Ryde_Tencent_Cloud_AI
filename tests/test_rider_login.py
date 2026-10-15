"""Demo login, rider scoping and stage-1 trip confirmation. Offline (deterministic mode)."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app import auth  # noqa: E402
from app.main import app  # noqa: E402
from app.rider_match import find_trip  # noqa: E402
from app.tools import call_tool  # noqa: E402
from app.tools.fixtures import load_rider_trips, rider_scope  # noqa: E402
from session import login, logout  # noqa: E402

DET = {"mode": "deterministic"}
TRIP_TOOLS = ("get_trip_data", "get_gps_telemetry", "get_chat_logs", "get_app_events", "get_traffic_reference",
              "get_fare_breakdown", "get_damage_evidence")


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def wait_done(client, cid):
    for _ in range(400):
        s = client.get(f"/api/cases/{cid}").json()
        if s["status"] not in ("intake", "in_review"):
            return s
        client.get("/api/health")
    raise AssertionError("case did not finish")


# ---------------------------------------------------------------- login

def test_login_sets_a_signed_session(client):
    login(client, "R-4521")
    me = client.get("/api/auth/me").json()
    assert me["role"] == "rider" and me["rider_id"] == "R-4521" and me["name"] == "Sarah Tan" and me["stories"]
    raw = client.cookies.get(auth.COOKIE)
    assert auth.verify(raw)["rider_id"] == "R-4521"
    r = client.post("/api/auth/login", json={"rider_id": "R-4521"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize("method,path", [
    ("get", "/api/auth/me"), ("get", "/api/trips"), ("get", "/api/disputes"), ("get", "/api/cases"),
    ("post", "/api/rider/find-trip"), ("post", "/api/cases"), ("post", "/api/file"), ("post", "/api/resolve/DISP-001"),
    ("get", "/api/cases/CASE-X/events"), ("post", "/api/cases/CASE-X/rider-message"),
    ("post", "/api/cases/CASE-X/human/ask"), ("post", "/api/cases/CASE-X/human/decision"),
])
def test_no_session_gives_401(client, method, path):
    r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert r.status_code == 401


def test_tampered_or_forged_cookie_gives_401(client):
    login(client, "R-4521")
    good = client.cookies.get(auth.COOKIE)
    body, mac = good.rsplit(".", 1)
    forged_body = auth._b64(json.dumps({"role": "rider", "rider_id": "R-7823", "iat": 9999999999}).encode())
    for bad in (f"{forged_body}.{mac}", f"{body}.{'0' * len(mac)}", "garbage", f"{body}."):
        client.cookies.clear()
        client.cookies.set(auth.COOKIE, bad)
        assert client.get("/api/auth/me").status_code == 401
    client.cookies.clear()
    client.cookies.set(auth.COOKIE, auth.sign({"role": "admin"}))          # validly signed, unknown role
    assert client.get("/api/trips").status_code == 401


def test_client_supplied_rider_id_is_ignored(client):
    login(client, "R-9001")
    # the body names another rider: ignored, the session decides
    r = client.post("/api/rider/find-trip", json={"story": "The driver took a long detour.", "rider_id": "R-4521"}).json()
    assert r["state"] == "none"                                            # R-9001 has no route deviation
    assert client.post("/api/cases", json={"story": "x", "trip_id": "TRIP-2026-09871", "rider_id": "R-4521", **DET}).status_code == 403
    snap = client.post("/api/cases", json={"story": "I was charged $16.50 but the quote was $12.00.", "trip_id": "TRIP-2026-10023",
                                           "rider_id": "R-4521", **DET}).json()
    assert snap["rider_id"] == "R-9001"
    trips = client.get("/api/trips?rider_id=R-4521").json()["trips"]
    assert trips and {t["rider_id"] for t in trips} == {"R-9001"}


def test_console_endpoints_need_the_support_role(client):
    login(client, "R-4521")
    snap = client.post("/api/cases", json={"story": "The driver took a long detour to Changi Airport T3.",
                                           "trip_id": "TRIP-2026-09871", **DET}).json()
    cid = snap["id"]
    assert wait_done(client, cid)["status"] == "with_agent"
    for path, body in (("ask", {"question": "Was there traffic?"}), ("rephrase", {"text": "hi"}), ("decision", {"action": "reject"})):
        assert client.post(f"/api/cases/{cid}/human/{path}", json=body).status_code == 403
    login(client, support=True)
    assert client.post(f"/api/cases/{cid}/human/rephrase", json={"text": "was there trafic"}).status_code == 200
    r = client.post(f"/api/cases/{cid}/human/ask", json={"question": "Was there traffic on the PIE?"})
    assert r.status_code == 200 and r.json()["status"] == "answered"
    assert client.post("/api/cases", json={"story": "x", "trip_id": "TRIP-2026-09871"}).status_code == 403   # support files nothing


# ---------------------------------------------------------------- isolation

def test_a_rider_cannot_read_another_riders_trips_through_any_tool():
    other = "TRIP-2026-09871"                                               # R-4521's trip
    with rider_scope("R-9001"):
        for tool in TRIP_TOOLS:
            mine = call_tool(tool, {"trip_id": "TRIP-2026-10023"})
            theirs = call_tool(tool, {"trip_id": other})
            missing = call_tool(tool, {"trip_id": "TRIP-2026-00000"})
            assert mine["ok"] and not theirs["ok"]
            # another rider's trip looks exactly like a trip that does not exist
            assert theirs["error"].replace(other, "X") == missing["error"].replace("TRIP-2026-00000", "X")
        assert not call_tool("get_rider_profile", {"rider_id": "R-4521"})["ok"]
        assert call_tool("get_rider_profile", {"rider_id": "R-9001"})["ok"]
        assert not call_tool("get_driver_profile", {"driver_id": "D-1187"})["ok"]   # drives only for other riders
        assert {t["rider_id"] for t in load_rider_trips()} == {"R-9001"}


def test_a_rider_cannot_read_another_riders_data_through_endpoints(client):
    login(client, "R-9001")
    assert {t["trip_id"] for t in client.get("/api/trips").json()["trips"]} == {t["trip_id"] for t in load_rider_trips("R-9001")}
    assert [d["dispute_id"] for d in client.get("/api/disputes").json()["disputes"]] == ["DISP-003"]
    assert client.post("/api/resolve/DISP-001", params=DET).status_code == 404
    assert client.get("/api/resolve/DISP-001/stream").status_code == 404
    assert client.post("/api/file", json={"complaint": "long detour", "trip_id": "TRIP-2026-09871", **DET}).status_code == 403


def test_a_story_naming_another_riders_route_does_not_match_their_trip(client):
    story = "The driver took a long detour from Orchard Central to Changi Airport T3 and overcharged me."
    assert find_trip(story, "R-9001")["state"] == "none"
    assert find_trip(story, "R-4521")["candidates"][0]["trip_id"] == "TRIP-2026-09871"
    login(client, "R-9001")
    r = client.post("/api/file", json={"complaint": story, **DET}).json()
    assert r.get("status") == "trip_unresolved" or r["filed_ticket"]["trip_id"] != "TRIP-2026-09871"
    assert all(c["trip_id"] != "TRIP-2026-09871" for c in r.get("candidates", []))


def test_another_riders_case_is_invisible(client):
    login(client, "R-4521")
    cid = client.post("/api/cases", json={"story": "The driver took a long detour to Changi Airport T3.",
                                          "trip_id": "TRIP-2026-09871", **DET}).json()["id"]
    wait_done(client, cid)
    login(client, "R-9001")
    assert client.get(f"/api/cases/{cid}").status_code == 404
    assert client.get(f"/api/cases/{cid}/events").status_code == 404
    assert client.post(f"/api/cases/{cid}/rider-message", json={"text": "hi"}).status_code == 404
    assert client.post(f"/api/cases/{cid}/human/ask", json={"question": "Did the rider have luggage?"}).status_code == 403
    assert cid not in {c["id"] for c in client.get("/api/cases").json()["cases"]}
    login(client, support=True)                                             # escalated: support may read it
    assert client.get(f"/api/cases/{cid}").json()["summary"]["who"]["rider"]["id"] == "R-4521"


# ---------------------------------------------------------------- stage 1 matching

def test_one_clear_match_gives_the_confirm_prompt(client):
    login(client, "R-4521")
    r = client.post("/api/rider/find-trip", json={"story": "The driver took a long detour on the way to Changi Airport T3 and never told me."}).json()
    assert r["state"] == "confirm" and r["category"] == "route_deviation"
    c = r["candidates"][0]
    assert c["trip_id"] == "TRIP-2026-09871" and c["pickup"] == "Orchard Central" and c["fare"] == 35.0 and c["time"]


def test_two_similar_trips_give_a_picker_with_only_this_riders_trips(client):
    login(client, "R-7823")
    r = client.post("/api/rider/find-trip", json={"story": "The driver never came and I was still charged a $5 cancellation fee."}).json()
    assert r["state"] == "pick"
    ids = {c["trip_id"] for c in r["candidates"]}
    assert ids == {"TRIP-2026-09945", "TRIP-2026-30201"}                    # TRIP-2026-10410 (R-7001) is never offered
    assert all(c["status"] == "cancelled" and c["why"] for c in r["candidates"])
    login(client, "R-4521")
    r = client.post("/api/rider/find-trip", json={"story": "My driver took a much longer route than usual and I paid more."}).json()
    assert r["state"] == "pick" and {c["trip_id"] for c in r["candidates"]} == {"TRIP-2026-09871", "TRIP-2026-30101"}


def test_zero_matches_gives_the_no_match_message(client):
    login(client, "R-9001")
    r = client.post("/api/rider/find-trip", json={"story": "The driver never showed up and I got a $5 cancellation fee."}).json()
    assert r["state"] == "none" and not r["candidates"] and "couldn't find" in r["message"]
    assert r["recent"] and {c["trip_id"] for c in r["recent"]} <= {t["trip_id"] for t in load_rider_trips("R-9001")}


def test_unclear_category_gives_a_clarifying_question(client):
    login(client, "R-5120")
    r = client.post("/api/rider/find-trip", json={"story": "Something went wrong with my last ride.", "lang": "zh"}).json()
    assert r["state"] == "clarify" and r["category"] is None and not r["candidates"] and "？" in r["message"]
    r = client.post("/api/rider/find-trip", json={"story": "Something went wrong with my last ride.\nThe driver was speeding over 100 km/h."}).json()
    assert r["state"] == "confirm" and r["candidates"][0]["trip_id"] == "TRIP-2026-10305"


def test_picking_a_trip_starts_the_case_and_the_ruling_follows(client):
    login(client, "R-7823")
    story = "The driver never came and I was still charged a $5 cancellation fee."
    snap = client.post("/api/cases", json={"story": story, "trip_id": "TRIP-2026-30201", **DET}).json()
    s = wait_done(client, snap["id"])
    # driver messaged once but never called (2.3): fee refunded by the AI
    assert s["status"] == "resolved_by_ai" and s["ticket"]["trip_id"] == "TRIP-2026-30201"
    assert s["outcome"]["refund_amount"] == 5.0 and "2.3" in s["outcome"]["policy_section"]


def test_three_pane_flow_end_to_end_after_login(client):
    login(client, "R-4521")
    cid = client.post("/api/cases", json={"story": "The driver took a long detour on the way to Changi Airport T3 and never told me.",
                                          "trip_id": "TRIP-2026-09871", **DET}).json()["id"]
    assert wait_done(client, cid)["status"] == "with_agent"
    login(client, support=True)
    queue = client.get("/api/cases").json()["cases"]
    assert any(c["id"] == cid and c["needs_human"] for c in queue)
    q = client.post(f"/api/cases/{cid}/human/ask", json={"question": "Did the rider have any luggage?"}).json()
    assert q["status"] == "asked_rider"
    login(client, "R-4521")
    assert client.get(f"/api/cases/{cid}").json()["status"] == "waiting_for_rider"
    client.post(f"/api/cases/{cid}/rider-message", json={"text": "Yes, two suitcases."})
    login(client, support=True)
    snap = client.get(f"/api/cases/{cid}").json()
    assert snap["qa_log"][-1]["status"] == "answered_after_reply" and "two suitcases" in snap["qa_log"][-1]["answer"]
    assert client.post(f"/api/cases/{cid}/human/decision", json={"action": "approve", "note": "checked teh records"}).status_code == 200
    login(client, "R-4521")
    s = client.get(f"/api/cases/{cid}").json()
    assert s["status"] == "resolved_by_human" and s["outcome"]["refund_amount"] == 3.44 and s["outcome"]["decided_by"] == "human"
    logout(client)
    assert client.get(f"/api/cases/{cid}").status_code == 401


def test_synthetic_data_is_labelled_and_official_files_untouched():
    data = json.loads((ROOT / "fixtures" / "trips_synthetic.json").read_text())
    assert data["_source"] == "Synthetic" and all(t["_source"] == "Synthetic" for t in data["trips"])
    assert json.loads((ROOT / "fixtures" / "demo_accounts.json").read_text())["_source"] == "Synthetic"
    from collections import Counter
    counts = Counter(t["rider_id"] for t in load_rider_trips())
    assert all(3 <= n <= 6 for n in counts.values()) and len(counts) == 6
