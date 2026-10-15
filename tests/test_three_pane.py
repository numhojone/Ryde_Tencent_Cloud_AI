"""Three-pane demo: cases, the three event panes, the rephrase and case-QA agents, human decisions. Offline."""
import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app import case_store as CS  # noqa: E402
from app.agents import case_qa  # noqa: E402
from app.agents.rephrase import RephraseAgent, fix_text, rephrase  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.tools import call_tool  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from session import login  # noqa: E402

ROUTE = ("The driver took a much longer route from Orchard Central to Changi Airport T3. The fare was $35 when I "
         "usually pay $28, and he never told me about any change.")
FARE = "The fare was $16.50 but the upfront quote at Bugis Junction was $12.00. Nobody told me the price had gone up."
SAFETY = "The driver was speeding over 100 km/h and shouted at me when I asked him to slow down. I felt really unsafe."
VAGUE = "Something went wrong with my last ride and I want my money back."


def run(coro):
    return asyncio.run(coro)


async def started(story, **kw):
    c = await CS.start_case(story, mode="deterministic", **kw)
    await c.wait_idle()
    return c


def statuses(c):
    return [e["status"] for e in c.events if e["type"] == "case_status"]


def panes(c, pane):
    return [e for e in c.events if e["pane"] == pane]


# ---------------------------------------------------------------- lifecycle

def test_escalated_case_full_lifecycle():
    async def go():
        c = await started(ROUTE)
        assert c.status == "with_agent"
        q = await CS.human_ask(c, "Did the rider have any luggage?")
        assert q["status"] == "asked_rider" and c.status == "waiting_for_rider"
        await CS.rider_message(c, "Yes, two suitcases in the boot.")
        assert c.status == "with_agent"
        await CS.human_decision(c, "approve")
        return c
    c = run(go())
    assert statuses(c) == ["intake", "in_review", "with_agent", "waiting_for_rider", "with_agent", "resolved_by_human"]


def test_ai_resolved_case_lifecycle_and_card():
    c = run(started(FARE))
    assert statuses(c) == ["intake", "in_review", "resolved_by_ai"]
    card = [e for e in panes(c, "rider") if e["type"] == "outcome"][0]["card"]
    assert card["decision"] == "refund" and card["refund_amount"] == 4.5 and card["decided_by"] == "ai"
    assert "3.3" in card["policy_section"] and card["reference"].startswith("DISP-")
    # plain language for the rider: no confidence, no internal enums
    blob = json.dumps(card).lower()
    assert "confidence" not in blob and "upheld" not in blob and "escalat" not in blob


def test_every_event_carries_a_pane_and_room_gets_the_pipeline():
    c = run(started(ROUTE))
    assert all(e["pane"] in ("rider", "room", "human", "case") for e in c.events)
    room_types = {e["type"] for e in panes(c, "room")}
    assert {"complaint_received", "trip_matched", "ticket_filed", "ruling", "safety_net", "done"} <= room_types
    rider_types = {e["type"] for e in panes(c, "rider")}
    assert {"rider_message", "assistant_message", "handoff"} <= rider_types
    assert "ruling" not in rider_types and "tool_call" not in rider_types
    handoff = [e for e in panes(c, "rider") if e["type"] == "handoff"][0]
    assert "passed to a Ryde support agent" in handoff["text"] and c.reference in handoff["text"]
    assert "$" not in handoff["text"]                       # no amount is promised while a person reviews it


def test_only_escalated_cases_reach_the_human_console():
    ai = run(started(FARE))
    esc = run(started(ROUTE))
    assert not panes(ai, "human")
    assert [e["type"] for e in panes(esc, "human")][:1] == ["case_escalated"]
    listed = {x["id"]: x for x in CS.list_cases()}
    assert listed[esc.id]["needs_human"] and not listed[ai.id]["needs_human"]


def test_ambiguous_story_waits_for_trip_then_runs():
    async def go():
        c = await started(VAGUE)
        assert c.status == "intake" and c.awaiting_trip and c.ticket is None
        choice = [e for e in panes(c, "rider") if e["type"] == "trip_choice"][0]
        assert len(choice["candidates"]) == 3
        await CS.rider_message(c, "That one", trip_id="TRIP-2026-10023")
        await c.wait_idle()
        return c
    c = run(go())
    assert c.ticket["trip_id"] == "TRIP-2026-10023" and c.status in ("resolved_by_ai", "with_agent")


# ---------------------------------------------------------------- rephrase agent

def test_rephrase_fixes_typos_and_keeps_meaning():
    r = run(rephrase("did teh drvier call ur phone b4 cancelling", purpose="qa", mode="deterministic"))
    assert r["rephrased"] == "Did the driver call your phone before cancelling?"
    assert r["changed"] and not r["used_model"]
    clean = run(rephrase("Did the driver call the rider?", mode="deterministic"))
    assert clean["rephrased"] == clean["original"] and not clean["changed"]
    assert fix_text("check R-4521 history pls") == "Check R-4521 history please."     # ids are not "typos"


def test_rider_bound_question_is_polite_and_second_person():
    r = run(rephrase("was the rider at the lobby at 8:45", purpose="rider", mode="deterministic"))
    assert r["rephrased"].startswith("Hello, this is Ryde Support.") and "Were you at the lobby at 8:45?" in r["rephrased"]
    zh = run(rephrase("乘客有没有带行李", purpose="rider", mode="deterministic", rider_lang="zh"))
    assert zh["rephrased"].startswith("您好") and "您有没有带行李？" in zh["rephrased"]


def test_rephrase_skips_the_model_when_text_is_clean(monkeypatch):
    async def boom(self, ctx):
        raise AssertionError("model must not be called for clean text")
    monkeypatch.setattr(RephraseAgent, "run", boom)
    r = run(rephrase("Did the driver call the rider?", purpose="qa", mode="llm"))
    assert r["rephrased"] == "Did the driver call the rider?" and not r["used_model"]


# ---------------------------------------------------------------- case-QA agent

def test_case_qa_answers_from_the_record_with_citations():
    async def go():
        c = await started(ROUTE)
        return await CS.human_ask(c, "Was there traffic on the PIE?")
    q = run(go())
    assert q["status"] == "answered" and q["found"]
    assert "Traffic reference" in q["citations"] and "TC-001" in q["answer"]


def test_case_qa_not_in_record_goes_to_the_rider_and_reply_answers_it():
    async def go():
        c = await started(ROUTE)
        q = await CS.human_ask(c, "Did the rider have any luggage?")
        assert not q["found"] and "not mentioned by the rider" in q["answer"]
        sent = [e for e in panes(c, "rider") if e["type"] == "support_message"]
        assert sent and sent[-1]["sender"] == "Ryde Support" and "Did you have any luggage?" in sent[-1]["text"]
        assert c.status == "waiting_for_rider"
        await CS.rider_message(c, "Yes, I had two big suitcases.")
        return c, q
    c, q = run(go())
    assert q["status"] == "answered_after_reply" and "two big suitcases" in q["answer"]
    assert any(s.startswith("Rider message") for s in q["citations"])
    summary = [e for e in panes(c, "human") if e["type"] == "summary"][-1]["summary"]
    assert summary["rider_replies"][-1]["text"] == "Yes, I had two big suitcases."


def test_case_qa_does_not_call_the_model_when_nothing_is_retrieved(monkeypatch):
    async def boom(self, ctx):
        raise AssertionError("no snippets: the model must not be called")
    monkeypatch.setattr(case_qa.CaseQAAgent, "run", boom)
    c = run(started(ROUTE))
    res = run(case_qa.answer(c.record(), "Did the rider have any luggage?", mode="llm"))
    assert not res["found"] and res["snippets"] == [] and not res["used_model"]


def test_case_qa_rejects_model_citations_outside_the_snippets(monkeypatch):
    from app.agents.base import AgentResult

    async def fake(self, ctx):
        return AgentResult("case_qa", "case_qa", case_qa.QAOut(answer="Yes.", citations=["Wikipedia"], found=True), None)
    monkeypatch.setattr(case_qa.CaseQAAgent, "run", fake)
    c = run(started(ROUTE))
    res = run(case_qa.answer(c.record(), "Was there traffic on the PIE?", mode="llm"))
    assert res["found"] and not res["used_model"] and "Wikipedia" not in res["citations"]


# ---------------------------------------------------------------- human decisions

def test_human_decision_resolves_and_tells_the_rider():
    async def go():
        c = await started(ROUTE)
        out = await CS.human_decision(c, "adjust", 5.0, "teh driver did not tell u about the detour")
        return c, out
    c, out = run(go())
    assert c.status == "resolved_by_human" and out["card"]["refund_amount"] == 5.0
    card = [e for e in panes(c, "rider") if e["type"] == "outcome"][-1]["card"]
    assert card["decided_by"] == "human" and "The driver did not tell you about the detour." in card["note"]
    assert c.human_messages[-1]["original"] == "teh driver did not tell u about the detour"   # rephrased before sending


def test_decision_validation_and_request_info():
    async def go():
        c = await started(ROUTE)
        with pytest.raises(CS.CaseError):
            await CS.human_decision(c, "adjust", 5.0, None)              # adjust needs a note
        with pytest.raises(CS.CaseError):
            await CS.human_decision(c, "request_info")                   # request needs a note
        await CS.human_decision(c, "request_info", note="please send a photo of ur receipt")
        assert c.status == "waiting_for_rider"
        await CS.rider_message(c, "Here is the receipt number 4411.")
        assert c.status == "with_agent" and c.qa_log[-1]["status"] == "answered_after_reply"
        await CS.human_decision(c, "reject")
        with pytest.raises(CS.CaseError):
            await CS.human_decision(c, "approve")                        # already resolved
        return c
    c = run(go())
    assert c.status == "resolved_by_human" and c.outcome["decision"] == "no_refund"


def test_ai_resolved_case_cannot_be_decided_by_a_human():
    c = run(started(FARE))
    with pytest.raises(CS.CaseError):
        run(CS.human_decision(c, "reject"))
    with pytest.raises(CS.CaseError):
        run(CS.human_ask(c, "Was the rider notified?"))


# ---------------------------------------------------------------- safety and leakage

def test_safety_incident_never_gets_an_ai_ruling():
    c = run(started(SAFETY))
    assert c.status == "with_agent" and c.ticket["dispute_type"] == "safety_incident"
    assert c.ruling["ruling"] == "escalated" and c.ruling["refund_amount"] is None and c.ruling["case_file"]["interim_measures"]
    s = [e for e in panes(c, "human") if e["type"] == "case_escalated"][0]["summary"]
    assert s["recommendation"] is None and s["case_file"]
    assert not any(e.get("agent") in ("judge", "rider_advocate", "driver_advocate") for e in panes(c, "room"))
    with pytest.raises(CS.CaseError):
        run(CS.human_decision(c, "approve"))                             # nothing to approve: the human decides


def test_no_ground_truth_reaches_any_pane_or_tool():
    rationales = [json.loads(p.read_text())["rationale"] for p in (ROOT / "fixtures" / "expected").glob("*.json")]
    async def go():
        cs = [await started(s) for s in (ROUTE, FARE, SAFETY)]
        await CS.human_ask(cs[0], "Was there traffic on the PIE?")
        return cs
    blob = json.dumps([c.events for c in run(go())], ensure_ascii=False)
    assert "fixtures/expected" not in blob and "recommended_ruling" not in blob
    assert not any(r[:60] in blob for r in rationales)
    for bad in ("../expected/DISP-001", "../../fixtures/expected/DISP-001"):
        assert not call_tool("get_trip_data", {"trip_id": bad})["ok"]
        assert not call_tool("get_rider_profile", {"rider_id": bad})["ok"]


def test_api_key_never_appears_in_events(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", "SECRET-KEY-123")
    c = CS.Case(id="CASE-T", mode="deterministic", lang="en", rider_lang="en", story="x")
    ev = CS.publish(c, "room", "error", message="upstream said: bad key SECRET-KEY-123")
    assert "SECRET-KEY-123" not in json.dumps(ev) and "[redacted]" in ev["message"]


# ---------------------------------------------------------------- HTTP API

def test_http_endpoints():
    with TestClient(app) as client:
        assert "Sign in" in client.get("/").text                        # no session: the login screen
        assert client.get("/classic", follow_redirects=False).status_code == 303
        login(client, "R-9001")
        assert client.get("/").status_code == 200 and "Three-pane" in client.get("/").text
        assert "Multi-agent dispute resolution" in client.get("/classic").text
        assert client.post("/api/cases", json={"story": "  ", "trip_id": "TRIP-2026-10023"}).status_code == 400
        assert client.post("/api/cases", json={"story": FARE}).status_code == 400          # trip not confirmed yet
        assert client.get("/api/cases/CASE-NOPE").status_code == 404
        snap = client.post("/api/cases", json={"story": FARE, "trip_id": "TRIP-2026-10023", "mode": "deterministic"}).json()
        cid = snap["id"]
        for _ in range(200):
            s = client.get(f"/api/cases/{cid}").json()
            if s["status"] == "resolved_by_ai":
                break
            client.get("/api/health")
        assert s["status"] == "resolved_by_ai" and s["outcome"]["refund_amount"] == 4.5
        assert "qa_log" not in s and "summary" not in s                 # console data is not sent to riders
        # a rider never reaches the console endpoints
        assert client.post(f"/api/cases/{cid}/human/decision", json={"action": "reject"}).status_code == 403
        assert client.post(f"/api/cases/{cid}/human/rephrase", json={"text": "wat time"}).status_code == 403
        login(client, support=True)
        # an AI-resolved case was never handed to a person, so the support agent does not see it
        assert client.get(f"/api/cases/{cid}").status_code == 404
        r = client.post(f"/api/cases/{cid}/human/decision", json={"action": "reject"})
        assert r.status_code == 404
