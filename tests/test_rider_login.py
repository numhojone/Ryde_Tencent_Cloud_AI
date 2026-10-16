"""Rider-only demo login, stage-1 trip confirmation on the rider's own dataset rides, and the end-to-end flow."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app import auth  # noqa: E402
from data60 import dataset_trip_ids, evidence, load  # noqa: E402
from app.main import app  # noqa: E402
from app.rider_match import demo_stories, find_trip  # noqa: E402
from app.tools.fixtures import load_rider_trips  # noqa: E402
from session import login, logout  # noqa: E402

DET = {"mode": "deterministic"}
DATA = load()


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


def trips_of(rid, kind=None):
    return [t for t in load_rider_trips(rid) if kind is None or t["ticket_type"] == kind]


# ---------------------------------------------------------------- login: one role, the dataset's six riders

def test_login_page_offers_only_riders(client):
    html = client.get("/").text
    assert "Sign in" in html and 'value="support"' not in html and 'value="driver"' not in html
    js = client.get("/static/login.js").text
    assert "role: 'support'" not in js and "role: 'driver'" not in js and "driverSelect" not in js and 'name="role"' not in html
    accounts = client.get("/api/auth/accounts").json()
    assert set(accounts) == {"riders"}
    assert sorted((a["rider_id"], a["name"]) for a in accounts["riders"]) == sorted(
        (rid, r["name"]) for rid, r in DATA["riders"].items())
    for body in ({"role": "support"}, {"role": "driver", "driver_id": "D-1187"}, {"rider_id": "R-0000"}):
        assert client.post("/api/auth/login", json=body).status_code == 400


def test_role_switch_and_driver_login_endpoints_are_gone(client):
    login(client, "R-3312")
    for method, path in (("post", "/api/session/role"), ("get", "/api/session/toggle"), ("get", "/api/driver/questions"),
                         ("post", "/api/driver/reply"), ("get", "/api/driver/events")):
        assert getattr(client, method)(path, **({"json": {}} if method == "post" else {})).status_code in (404, 405)
    assert "DEMO_ROLE_SWITCH" not in (ROOT / ".env.example").read_text()


def test_login_sets_a_signed_session_with_the_dataset_name(client):
    login(client, "R-3312")
    me = client.get("/api/auth/me").json()
    assert me["rider_id"] == "R-3312" and me["display"] == "Wong Mei Ling (R-3312)" and me["stories"]
    assert auth.verify(client.cookies.get(auth.COOKIE))["rider_id"] == "R-3312"
    cookie = client.post("/api/auth/login", json={"rider_id": "R-3312"}).headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


@pytest.mark.parametrize("method,path", [
    ("get", "/api/auth/me"), ("get", "/api/trips"), ("get", "/api/disputes"), ("get", "/api/cases"),
    ("post", "/api/rider/find-trip"), ("post", "/api/cases"), ("post", "/api/file"), ("post", "/api/resolve/DISP-101"),
    ("get", "/api/cases/CASE-X/events"), ("post", "/api/cases/CASE-X/rider-message"),
    ("post", "/api/cases/CASE-X/human/ask"), ("post", "/api/cases/CASE-X/human/decision"),
    ("get", "/api/driver-view"), ("post", "/api/driver-view/reply"),
])
def test_no_session_gives_401(client, method, path):
    assert getattr(client, method)(path, **({"json": {}} if method == "post" else {})).status_code == 401


def test_tampered_or_forged_cookie_gives_401(client):
    login(client, "R-3312")
    body, mac = client.cookies.get(auth.COOKIE).rsplit(".", 1)
    forged = auth._b64(json.dumps({"role": "rider", "rider_id": "R-4521", "iat": 9999999999}).encode())
    for bad in (f"{forged}.{mac}", f"{body}.{'0' * len(mac)}", "garbage"):
        client.cookies.clear(); client.cookies.set(auth.COOKIE, bad)
        assert client.get("/api/auth/me").status_code == 401
    for role in ({"role": "support"}, {"role": "driver", "driver_id": "D-1187"}):   # validly signed, but no such role
        client.cookies.clear(); client.cookies.set(auth.COOKIE, auth.sign(role))
        assert client.get("/api/trips").status_code == 401


def test_client_supplied_rider_id_is_ignored(client):
    login(client, "R-9001")
    r = client.post("/api/rider/find-trip", json={"story": "Show me all my rides.", "rider_id": "R-3312"}).json()
    assert {c["trip_id"] for c in r["candidates"]} == {t["trip_id"] for t in trips_of("R-9001")}
    trip = trips_of("R-9001", "route_deviation")[0]["trip_id"]
    snap = client.post("/api/cases", json={"story": "long detour", "trip_id": trip, "rider_id": "R-3312", **DET}).json()
    assert snap["rider_id"] == "R-9001"
    assert {t["rider_id"] for t in client.get("/api/trips?rider_id=R-3312").json()["trips"]} == {"R-9001"}


# ---------------------------------------------------------------- stage 1 on the rider's own rides

def test_quick_fill_stories_all_lead_to_a_real_match_for_that_rider():
    n = 0
    for rid in DATA["riders"]:
        for st in demo_stories(rid):
            for lang in ("en", "zh"):
                r = find_trip(st[lang], rid, lang)
                assert r["state"] == st["expect"], (rid, st["key"], lang, r["state"])
                assert {c["trip_id"] for c in r["candidates"]} <= {t["trip_id"] for t in trips_of(rid)}
                if st["expect"] == "confirm":
                    assert r["candidates"][0]["trip_id"] == st["trip_id"]
                n += 1
    assert n >= 6 * 8 * 2


def test_vague_story_gives_a_picker_of_only_that_riders_trips_of_that_type():
    checked = 0
    for rid in DATA["riders"]:
        for kind, story in (("route_deviation", "My driver took a much longer route than usual and I paid more."),
                            ("no_show_charge", "The driver never came and I was still charged a $5 cancellation fee."),
                            ("property_damage", "I was charged a cleaning fee but I never dirtied the car."),
                            ("safety_incident", "My driver was driving dangerously and I felt unsafe.")):
            mine = {t["trip_id"] for t in trips_of(rid, kind)}
            if len(mine) < 2:
                continue
            r = find_trip(story, rid)
            assert r["state"] == "pick" and {c["trip_id"] for c in r["candidates"]} == mine, (rid, kind)
            checked += 1
    assert checked == 24                                   # every rider has 2 or 3 rides of every type


def test_none_clarify_list_and_foreign(client):
    login(client, "R-3312")
    r = client.post("/api/rider/find-trip", json={"story": "Something went wrong with my last ride.", "lang": "zh"}).json()
    assert r["state"] == "clarify" and "？" in r["message"]
    r = client.post("/api/rider/find-trip", json={"story": "Show me all my rides."}).json()
    assert r["state"] == "list" and len(r["candidates"]) == len(trips_of("R-3312")) == 11      # sample trip + 10
    r = client.post("/api/rider/find-trip", json={"story": "The fare was higher than the upfront quote and the surge was never shown."}).json()
    assert r["state"] == "none" and len(r["recent"]) == 11 and not r["candidates"]   # R-3312 has no fare-dispute ride
    for story in ("What happened on Sarah Tan's trip? The driver took a detour.", "TRIP-2026-2020 was a no-show",
                  "Rider R-4521 was charged a cleaning fee", "Look at Daniel's trip, the driver never came"):
        r = client.post("/api/rider/find-trip", json={"story": story}).json()
        assert r["state"] == "foreign" and r["message"] == "I can only look at trips on your account."
        assert not r["candidates"] and not r["recent"]


def test_type_mismatch_asks_before_starting(client):
    login(client, "R-3312")
    cleaning = trips_of("R-3312", "property_damage")[0]["trip_id"]
    story = "My driver took a much longer route than usual and I paid more."
    r = client.post("/api/cases", json={"story": story, "trip_id": cleaning, **DET})
    assert r.status_code == 409 and r.json()["mismatch"]["ticket_label"] == "Property damage / cleaning fee"
    snap = client.post("/api/cases", json={"story": story, "trip_id": cleaning, "confirm_type": True, **DET}).json()
    s = wait_done(client, snap["id"])
    assert s["ticket"]["dispute_type"] == "property_damage" and s["ticket"]["description"] == story


def test_confirmed_trip_reuses_its_dataset_ticket(client):
    login(client, "R-4521")
    t = trips_of("R-4521", "no_show_charge")[0]
    story = "The driver never came and I was still charged a $5 cancellation fee."
    s = wait_done(client, client.post("/api/cases", json={"story": story, "trip_id": t["trip_id"], **DET}).json()["id"])
    tk = DATA["tickets"][t["dispute_id"]]
    assert s["ticket"]["dispute_id"] == tk["dispute_id"] and s["ticket"]["trip_id"] == t["trip_id"]
    assert s["ticket"]["driver_id"] == tk["driver_id"] and s["ticket"]["rider_id"] == "R-4521"
    assert s["ticket"]["description"] == story and "Automated dispute" not in json.dumps(s["ticket"])


# ---------------------------------------------------------------- end to end, all in the rider's own screen

def test_three_pane_flow_end_to_end_after_login(client):
    login(client, "R-9001")
    trip = "TRIP-2026-2052"                                # over 2 km, unjustified: a person must approve
    cid = client.post("/api/cases", json={"story": "The driver took a long detour and charged me more.", "trip_id": trip, **DET}).json()["id"]
    s = wait_done(client, cid)
    assert s["status"] == "with_agent" and s["summary"]["recommendation"]["ruling"] == "upheld"
    assert any(c["id"] == cid and c["needs_human"] for c in client.get("/api/cases").json()["cases"])
    q = client.post(f"/api/cases/{cid}/human/ask", json={"question": "Did the rider have any luggage?"}).json()
    assert q["status"] == "asked_rider"
    client.post(f"/api/cases/{cid}/rider-message", json={"text": "Yes, two suitcases."})
    snap = client.get(f"/api/cases/{cid}").json()
    assert snap["qa_log"][-1]["status"] == "answered_after_reply" and "two suitcases" in snap["qa_log"][-1]["answer"]
    rec = snap["summary"]["recommendation"]["refund_amount"]
    d = client.post(f"/api/cases/{cid}/human/decision", json={"action": "approve", "note": "checked teh records"}).json()
    assert d["card"]["refund_amount"] == rec and client.get(f"/api/cases/{cid}").json()["status"] == "resolved_by_human"
    logout(client)
    assert client.get(f"/api/cases/{cid}").status_code == 401


def test_a_ride_has_one_case_and_choosing_it_again_reopens_it(client):
    login(client, "R-4521")
    trip = trips_of("R-4521", "route_deviation")[0]["trip_id"]
    first = client.post("/api/cases", json={"story": "long detour", "trip_id": trip, **DET}).json()
    again = client.post("/api/cases", json={"story": "long detour again", "trip_id": trip, **DET}).json()
    assert again["existing"] and again["id"] == first["id"] and again["reference"] == first["reference"]
    assert len([c for c in client.get("/api/cases").json()["cases"] if c["trip_id"] in (trip, None)]) == 1


def test_session_cookie_is_secure_behind_https_but_works_on_plain_http(client):
    plain = client.post("/api/auth/login", json={"rider_id": "R-3312"}).headers["set-cookie"].lower()
    assert "secure" not in plain                               # local http: the browser must still send it back
    behind = client.post("/api/auth/login", json={"rider_id": "R-3312"},
                         headers={"X-Forwarded-Proto": "https"}).headers["set-cookie"].lower()
    assert "secure" in behind and "httponly" in behind and "samesite=lax" in behind
    client.cookies.clear()
    client.post("/api/auth/login", json={"rider_id": "R-3312"})       # plain http: the cookie comes back and works
    assert client.get("/api/auth/me").status_code == 200
