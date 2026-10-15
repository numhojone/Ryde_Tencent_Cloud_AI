"""Ground truth (fixtures/expected) and the story key (fixtures/stories) never reach a tool, an event, the UI or a prompt.
Extends the sample-case leakage test to the 60 dataset tickets. Offline."""
import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orchestrator import resolve  # noqa: E402
from app.tools import call_tool  # noqa: E402
from app.tools.fixtures import rider_scope  # noqa: E402
from data60 import dataset_trip_ids, load  # noqa: E402
from session import login  # noqa: E402

FX = ROOT / "fixtures"
EXPECTED = {p.stem: json.loads(p.read_text()) for p in sorted((FX / "expected").glob("DISP-1*.json"))}
# words that only exist in the ground-truth and story-key files
MARKERS = ("must_escalate", "fraud_flag_party", "computed from Policy v2.1 and the scenario", "expected_dispute_id",
           "expected_trip_id", "same_category_trips_for_this_rider", "expect_picker", "refuse_not_on_this_account")


def _clean(blob: str, did: str) -> None:
    for m in MARKERS:
        assert m not in blob, (did, m)
    e = EXPECTED[did]
    assert e["rationale"] not in blob, did
    assert f'"scenario": "{e["scenario"]}"' not in blob, did


def test_expected_and_story_files_exist_for_the_new_cases():
    assert len(EXPECTED) == 60 and (FX / "stories" / "stories.json").exists()


@pytest.mark.parametrize("path", ["../expected/DISP-101", "../expected/DISP-160", "../stories/stories",
                                  "../../fixtures/expected/DISP-130"])
def test_no_tool_can_read_ground_truth_or_the_story_key(path):
    for tool, arg in (("get_trip_data", "trip_id"), ("get_chat_logs", "trip_id"), ("get_damage_evidence", "trip_id"),
                      ("get_rider_profile", "rider_id"), ("get_driver_profile", "driver_id"), ("get_policy", "dispute_type")):
        r = call_tool(tool, {arg: path})
        assert not r["ok"], (tool, path)
    with rider_scope("R-3312"):
        assert not call_tool("get_trip_data", {"trip_id": path})["ok"]


@pytest.mark.parametrize("did", sorted(EXPECTED))
def test_no_event_of_a_new_case_holds_ground_truth(did):
    async def go():
        return [e async for e in resolve(did, mode="deterministic")]
    blob = json.dumps(asyncio.run(go()), ensure_ascii=False)
    _clean(blob, did)


def test_no_api_response_in_a_rider_session_holds_ground_truth():
    data = load()
    with TestClient(app) as c:
        for rid in data["riders"]:
            login(c, rid)
            mine = [t for t in dataset_trip_ids() if data["trips"][t]["rider_id"] == rid]
            blobs = [c.get("/api/auth/me").text, c.get("/api/trips").text, c.get("/api/disputes").text,
                     c.post("/api/rider/find-trip", json={"story": "Show me all my rides."}).text]
            tid = mine[0]
            snap = c.post("/api/cases", json={"story": "Something happened on this ride.", "trip_id": tid,
                                              "mode": "deterministic", "confirm_type": True}).json()
            for _ in range(400):
                s = c.get(f"/api/cases/{snap['id']}")
                if s.json()["status"] not in ("intake", "in_review"):
                    break
            blobs += [s.text, c.get("/api/driver-view").text, c.get("/api/cases").text]
            blob = "\n".join(blobs)
            for t in mine:
                _clean(blob, data["trips"][t]["dispute_id"])
