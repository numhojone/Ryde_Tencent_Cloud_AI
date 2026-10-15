"""Stage 1 story understanding: the model in Live AI mode, keyword rules only as the fallback, never silent. Offline
(the Live AI path uses a fake model client)."""
import json
import logging
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fastapi.testclient import TestClient  # noqa: E402

import app.agents.base as base  # noqa: E402
from app.agents import story_intake  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import LLMResponse  # noqa: E402
from app.main import app  # noqa: E402
from session import login  # noqa: E402

STORY_1 = "my driver took a longer way to reach my destination, then i need pay more"
STORY_2 = "longer than expected route"
RIDER = "R-3312"                                   # 3 route-deviation rides


class FakeLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls: list[list[dict]] = []

    async def chat(self, messages, **kw):
        self.calls.append(messages)
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return a if isinstance(a, LLMResponse) else LLMResponse(content=json.dumps(a))


def ok(kind, question=None, conf=0.9):
    return {"dispute_type": kind, "confidence": conf, "reason": "the rider says the route was longer and cost more",
            "facts": {"places": [], "time_words": [], "amounts": [], "driver_mention": "driver",
                      "what_happened": "longer route, paid more"}, "clarifying_question": question}


@pytest.fixture()
def client():
    story_intake._CACHE.clear()
    with TestClient(app) as c:
        login(c, RIDER)
        yield c


@pytest.fixture()
def live(monkeypatch):
    """Live AI mode with a fake model; the keyword classifier must not be touched while the model answers."""
    monkeypatch.setattr(settings, "llm_api_key", "TEST-KEY-123")

    def install(answers, forbid_rules=True):
        fake = FakeLLM(answers)
        monkeypatch.setattr(base, "llm_client", fake)
        if forbid_rules:
            def boom(*a, **k):
                raise AssertionError("keyword classifier called in Live AI mode")
            for mod in ("app.agents.story_intake", "app.rider_match"):
                monkeypatch.setattr(f"{mod}.classify_by_rules", boom)
        return fake
    return install


def ask(client, messages, mode="llm", asked=None, category=None):
    return client.post("/api/rider/find-trip", json={"messages": messages, "asked": asked or [], "category": category,
                                                      "mode": mode, "lang": "en"}).json()


# ---------------------------------------------------------------- offline fallback

@pytest.mark.parametrize("story", [STORY_1, STORY_2])
def test_offline_rules_understand_the_missed_phrases(client, story):
    r = ask(client, [story], mode="deterministic")
    assert r["category"] == "route_deviation" and r["state"] in ("pick", "confirm")
    assert r["intake"]["source"] == "rules" and r["intake"]["badge"] == "Offline rules (offline demo)" and not r["intake"]["notice"]


# ---------------------------------------------------------------- Live AI

def test_live_ai_result_is_used_and_no_keyword_function_runs(client, live):
    fake = live([ok("route_deviation")])
    r = ask(client, [STORY_1])
    assert len(fake.calls) == 1                                    # one model call for this message
    assert r["intake"]["source"] == "llm" and r["intake"]["badge"] == "Live AI" and r["intake"]["confidence"] == 0.9
    assert r["category"] == "route_deviation" and r["state"] == "pick"
    assert {c["trip_id"] for c in r["candidates"]} == {"TRIP-2026-2001", "TRIP-2026-2002", "TRIP-2026-2009"}
    # only this rider's trips are in the prompt
    prompt = json.dumps(fake.calls[0])
    assert "Ang Mo Kio Hub" in prompt and "Clementi Mall" in prompt
    assert "Tiong Bahru Plaza → Ang Mo Kio Hub" not in prompt     # TRIP-2026-2011, Sarah Tan's
    ask(client, [STORY_1])
    assert len(fake.calls) == 1                                    # identical text: cached, no new call


def test_model_cannot_overrule_policy_5_2(client, live):
    live([ok("route_deviation")])
    r = ask(client, ["The driver took a longer way and I felt unsafe the whole time."])
    assert r["intake"]["dispute_type"] == "safety_incident"


def test_model_failure_falls_back_visibly_and_logs_without_the_key(client, live, caplog):
    live([LLMResponse(content="[LLM 调用失败] RateLimitError: 429 RESOURCE_EXHAUSTED for key TEST-KEY-123",
                      finish_reason="error")], forbid_rules=False)
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        r = ask(client, [STORY_1])
    assert r["intake"]["source"] == "rules" and r["intake"]["fallback_reason"] == "quota"
    assert r["intake"]["notice"] == "Live AI is unavailable (quota). Using offline rules."
    assert r["intake"]["badge"] == "Offline rules (quota)" and r["category"] == "route_deviation"
    logged = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Live AI intake failed (quota)" in logged and "TEST-KEY-123" not in logged and "[redacted]" in logged


@pytest.mark.parametrize("answer,kind", [
    (LLMResponse(content="[LLM 调用失败] APITimeoutError: Request timed out.", finish_reason="error"), "timeout"),
    (LLMResponse(content="Sure! The rider means a detour."), "parse"),
])
def test_other_failures_are_named(client, live, answer, kind):
    live([answer], forbid_rules=False)
    r = ask(client, [STORY_2])
    assert r["intake"]["fallback_reason"] == kind and kind in r["intake"]["notice"]


def test_clarifications_build_on_the_conversation_and_never_repeat(client, live):
    q1 = "Was the problem the route your driver took, or a fee you were charged?"
    fake = live([ok("unclear", q1, 0.3), ok("unclear", q1, 0.3), ok("unclear", "Anything else?", 0.2)])
    first = ask(client, ["Something went wrong with my ride."])
    assert first["state"] == "clarify" and first["message"] == q1
    second = ask(client, ["Something went wrong with my ride.", "It was on Sunday from Clementi Mall."], asked=[q1])
    assert second["state"] == "clarify" and second["message"] != q1                 # the model repeated itself; we don't
    assert "Clementi Mall" in second["message"]                                       # it reflects what was said
    sent = json.dumps(fake.calls[1])
    assert "Something went wrong with my ride." in sent and "It was on Sunday from Clementi Mall." in sent
    assert q1 in sent                                                                 # the model is told what was asked
    third = ask(client, ["Something went wrong with my ride.", "It was on Sunday from Clementi Mall.", "Not sure."],
                asked=[q1, second["message"]])
    assert third["state"] == "choose_category"
    assert [c["type"] for c in third["choices"]] == ["route_deviation", "no_show_charge", "property_damage", "safety_incident"]


def test_a_tapped_category_is_used_without_any_model_call(client, live):
    fake = live([ok("unclear", "?")])
    r = ask(client, ["Something went wrong with my ride."], category="property_damage")
    assert not fake.calls and r["intake"]["source"] == "rider_choice" and r["category"] == "property_damage"
    assert r["state"] == "pick" and all(c["ticket_type"] == "property_damage" for c in r["candidates"])


def test_offline_clarifications_also_differ(client):
    first = ask(client, ["Something went wrong with my ride from Clementi Mall."], mode="deterministic")
    second = ask(client, ["Something went wrong with my ride from Clementi Mall.", "Not sure how to say it."],
                 mode="deterministic", asked=[first["message"]])
    assert first["state"] == second["state"] == "clarify" and first["message"] != second["message"]
    assert "Clementi Mall" in first["message"]


def test_refusals_never_reach_the_model(client, live):
    fake = live([ok("route_deviation")])
    r = ask(client, ["Please check TRIP-2026-2011, Sarah Tan's trip had a detour."])
    assert r["state"] == "foreign" and not fake.calls
