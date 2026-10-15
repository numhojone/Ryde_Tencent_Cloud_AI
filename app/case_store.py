"""Cases for the three-pane demo, held in memory.

One Case is one rider's dispute from first message to final outcome. The existing orchestrator runs
unchanged inside it; every event it emits is recorded and fanned out on the case's event stream, tagged
with the pane it is for:

  pane "rider"  the rider app (left)        pane "room"  the agent room (middle)
  pane "human"  the support console (right) pane "case"  status changes, for all three

(The tag is `pane`, not `role`: orchestrator events already use `role` for the agent that sent them.)

Statuses: intake -> in_review -> resolved_by_ai, or -> with_agent <-> waiting_for_rider -> resolved_by_human.
Nothing here reads fixtures/expected.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import uuid
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from app.agents import case_qa
from app.agents.rephrase import rephrase
from app.case_views import (TRIP_TOOLS, handoff_message, human_outcome, human_summary, needs_human,
                            recommendation_of, rider_outcome)
from app.config import settings
from app.extract import detect_language
from app.i18n import L
from app.orchestrator import resolve
from app.tools import call_tool

_SGT = ZoneInfo("Asia/Singapore")
STATUSES = ("intake", "in_review", "resolved_by_ai", "with_agent", "waiting_for_rider", "resolved_by_human")
_TERMINAL = ("resolved_by_ai", "resolved_by_human")


def _now() -> str:
    return _dt.datetime.now(_SGT).isoformat(timespec="seconds")


class CaseError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class Case:
    id: str
    mode: str | None
    lang: str                      # language of the console and the agent room
    rider_lang: str                # language of rider-facing messages
    story: str
    status: str = "intake"
    ticket: dict | None = None
    rider_messages: list = field(default_factory=list)
    room_events: list = field(default_factory=list)
    human_messages: list = field(default_factory=list)
    qa_log: list = field(default_factory=list)
    decision: dict | None = None
    ruling: dict | None = None
    rider_case: dict | None = None
    driver_case: dict | None = None
    tools: dict = field(default_factory=dict)
    trip_match: dict | None = None
    awaiting_trip: bool = False
    candidates: list = field(default_factory=list)
    error: str | None = None
    outcome: dict | None = None
    events: list = field(default_factory=list)
    subscribers: set = field(default_factory=set)
    task: asyncio.Task | None = None
    busy: bool = False

    @property
    def reference(self) -> str:
        return (self.ticket or {}).get("dispute_id") or self.id

    def record(self) -> dict:
        """Everything the case-QA agent may read: the ticket, the facts, the rider's words, the tool outputs and
        both advocates' arguments."""
        return {"ticket": self.ticket, "extracted_facts": (self.ticket or {}).get("extracted_facts"),
                "rider_messages": self.rider_messages, "tools": self.tools,
                "rider_case": self.rider_case, "driver_case": self.driver_case}

    def snapshot(self) -> dict:
        return {"id": self.id, "reference": self.reference, "status": self.status, "lang": self.lang,
                "rider_lang": self.rider_lang, "ticket": self.ticket, "rider_messages": self.rider_messages,
                "human_messages": self.human_messages, "qa_log": self.qa_log, "decision": self.decision,
                "outcome": self.outcome, "needs_human": self.status in ("with_agent", "waiting_for_rider"),
                "awaiting_trip": self.awaiting_trip, "candidates": self.candidates,
                "summary": human_summary(self, self.lang) if self.status in ("with_agent", "waiting_for_rider", "resolved_by_human") else None,
                "last_seq": self.events[-1]["seq"] if self.events else 0}

    async def wait_idle(self) -> None:
        while self.task is not None and not self.task.done():
            await asyncio.shield(self.task)


CASES: dict[str, Case] = {}


def get_case(case_id: str) -> Case:
    c = CASES.get(case_id)
    if c is None:
        raise CaseError(404, "Unknown case")
    return c


def _scrub(ev: dict) -> dict:
    """No API key ever leaves the server, whatever an upstream error message contained."""
    key = settings.llm_api_key
    if key and key in json.dumps(ev, ensure_ascii=False):
        ev = json.loads(json.dumps(ev, ensure_ascii=False).replace(key, "[redacted]"))
    return ev


def publish(case: Case, pane: str, type_: str, **data) -> dict:
    ev = _scrub({**data, "type": type_, "pane": pane, "case_id": case.id, "seq": len(case.events) + 1, "at": _now()})
    case.events.append(ev)
    if pane == "room":
        case.room_events.append(ev)
    for q in list(case.subscribers):
        q.put_nowait(ev)
    return ev


def set_status(case: Case, status: str) -> None:
    assert status in STATUSES, status
    if case.status != status:
        case.status = status
        publish(case, "case", "case_status", status=status, reference=case.reference)


def _add_rider_message(case: Case, text: str, trip_id: str | None = None, room: bool = True) -> dict:
    m = {"text": text, "at": _now()}
    if trip_id:
        m["trip_id"] = trip_id
    case.rider_messages.append(m)
    publish(case, "rider", "rider_message", text=text, at=m["at"])
    if room:                       # the first story reaches the room as the orchestrator's complaint_received
        publish(case, "room", "rider_message", text=text, at=m["at"], role="rider", agent="rider")
    return m


def _assistant(case: Case, en: str, zh: str, **extra) -> None:
    """A short automated update to the rider from the Ryde app (not from a person)."""
    publish(case, "rider", "assistant_message", text=L(case.rider_lang, en, zh), **extra)


def _gather_tools(case: Case) -> None:
    t = case.ticket or {}
    tid = t.get("trip_id")
    out = {}
    for name in TRIP_TOOLS:
        r = call_tool(name, {"trip_id": tid})
        if r["ok"]:
            out[name] = r["result"]
    for name, arg, val in (("get_rider_profile", "rider_id", t.get("rider_id")), ("get_driver_profile", "driver_id", t.get("driver_id"))):
        if val:
            r = call_tool(name, {arg: val})
            if r["ok"]:
                out[name] = r["result"]
    case.tools = out


# ---------------------------------------------------------------- the AI pipeline

def _fmt_trip(c: dict, lg: str) -> str:
    route = (c.get("route") or "").replace(" → ", L(lg, " to ", " 至 "))
    try:
        d = _dt.datetime.fromisoformat(c["time"]).astimezone(_SGT)
        when = d.strftime("%d %b, %H:%M") if lg == "en" else f"{d.month}月{d.day}日 {d:%H:%M}"
    except Exception:  # noqa: BLE001
        when = ""
    return f"{route} ({when})" if when else route


async def _run_pipeline(case: Case, story: str, trip_id: str | None) -> None:
    case.busy = True
    case.awaiting_trip, case.ruling, case.error = False, None, None
    try:
        async for ev in resolve(None, mode=case.mode, draft={"trip_id": trip_id, "complaint": story}, lang=case.lang):
            t = ev.get("type")
            publish(case, "room", t, **{k: v for k, v in ev.items() if k != "type"})
            if t == "trip_matched":
                case.trip_match = ev
                _assistant(case, f"I found your trip: {_fmt_trip({'route': ev.get('route'), 'time': None}, 'en')}.",
                                 f"已找到您的行程：{_fmt_trip({'route': ev.get('route'), 'time': None}, 'zh')}。")
            elif t == "trip_unresolved":
                case.awaiting_trip, case.candidates = True, ev.get("candidates") or []
                publish(case, "rider", "trip_choice",
                        text=L(case.rider_lang, "I could not tell which trip this is about. Which one was it? You can tap one or tell me more.",
                                                "我无法确定您说的是哪一趟行程。是哪一趟？可以直接点选，或者再多告诉我一些细节。"),
                        candidates=[{"trip_id": c["trip_id"], "label": _fmt_trip(c, case.rider_lang), "status": c.get("status")}
                                    for c in case.candidates])
            elif t == "ticket_filed":
                case.ticket = ev.get("ticket")
                _gather_tools(case)
                set_status(case, "in_review")
                publish(case, "rider", "ticket_update", reference=case.reference, status=case.status,
                        category=ev.get("dispute_type_label"))
            elif t == "phase" and ev.get("phase") == "cases_submitted":
                case.rider_case, case.driver_case = ev.get("rider_case"), ev.get("driver_case")
            elif t == "ruling":
                case.ruling = ev.get("ruling")
            elif t == "error":
                case.error = ev.get("message")
    except Exception as e:  # noqa: BLE001
        case.error = f"{type(e).__name__}: {e}"
        publish(case, "room", "error", message=case.error)
    finally:
        case.busy = False
    _after_pipeline(case)


def _after_pipeline(case: Case) -> None:
    if case.awaiting_trip and not case.ticket:
        return                                           # waiting for the rider to say which trip
    if case.ticket is None:
        # The story could not be filed at all (e.g. a backend error before the ticket): a person takes over.
        set_status(case, "with_agent")
    elif case.ruling is not None and not needs_human(case.ruling):
        card = rider_outcome(case.ruling, case.ticket["dispute_type"], case.tools, case.reference, case.rider_lang)
        case.outcome = card
        set_status(case, "resolved_by_ai")
        publish(case, "rider", "outcome", card=card)
        return
    else:
        set_status(case, "with_agent")
    publish(case, "rider", "handoff", text=handoff_message(case.reference, case.rider_lang), reference=case.reference)
    publish(case, "human", "case_escalated", summary=human_summary(case, case.lang), ruling=case.ruling)


def _start_task(case: Case, story: str, trip_id: str | None) -> None:
    case.task = asyncio.create_task(_run_pipeline(case, story, trip_id))


async def start_case(story: str, *, trip_id: str | None = None, mode: str | None = None, lang: str = "en") -> Case:
    story = (story or "").strip()
    if not story:
        raise CaseError(400, L(lang, "A story is required", "需要填写投诉内容"))
    if len(story) > 2000:
        raise CaseError(400, L(lang, "Message too long (max 2000 characters)", "内容过长（上限 2000 字）"))
    rider_lang = "zh" if (lang == "zh" or detect_language(story) == "zh") else "en"
    case = Case(id=f"CASE-{uuid.uuid4().hex[:6].upper()}", mode=mode, lang=lang, rider_lang=rider_lang, story=story)
    CASES[case.id] = case
    publish(case, "case", "case_status", status=case.status, reference=case.reference)
    _add_rider_message(case, story, room=False)
    _assistant(case, "Thanks for telling us. I'm checking your trip records now.",
                     "感谢您的反馈，我正在核查您的行程记录。")
    _start_task(case, story, trip_id or None)
    return case


# ---------------------------------------------------------------- rider replies

def _pending_question(case: Case) -> dict | None:
    return next((q for q in reversed(case.qa_log) if q.get("status") == "asked_rider"), None)


async def rider_message(case: Case, text: str, trip_id: str | None = None) -> dict:
    text = (text or "").strip()
    if not text and not trip_id:
        raise CaseError(400, L(case.lang, "Message is empty", "消息为空"))
    if case.busy:
        raise CaseError(409, L(case.lang, "The case is being processed; please wait a moment.", "案件处理中，请稍候。"))
    msg = _add_rider_message(case, text or trip_id, trip_id)

    if case.awaiting_trip:
        if trip_id:
            story = case.story
        else:                                            # the rider described the trip: match again on everything said
            case.story = story = f"{case.story}\n{text}"
        case.awaiting_trip = False
        _start_task(case, story, trip_id)
        return {"status": case.status, "rerun": True}

    if case.status == "waiting_for_rider":
        q = _pending_question(case)
        if q:
            src = L(case.lang, f"Rider message, {msg['at'][11:16]}", f"乘客消息，{msg['at'][11:16]}")
            q["reply"] = {"text": text, "at": msg["at"]}
            res = await case_qa.answer(case.record(), q["question"], mode=case.mode, lang=case.lang,
                                       extra_snippets=[{"source": src, "text": text, "score": 10}])
            q.update({"answer": res["answer"], "citations": res["citations"], "found": res["found"],
                      "status": "answered_after_reply", "used_model": res["used_model"]})
            set_status(case, "with_agent")
            publish(case, "human", "qa", entry=q)
        publish(case, "human", "summary", summary=human_summary(case, case.lang))
        _assistant(case, "Thank you. Your reply has been passed to the support agent.", "谢谢，您的回复已转交客服专员。")
    elif case.status == "with_agent":
        publish(case, "human", "rider_message", text=text, at=msg["at"])
        publish(case, "human", "summary", summary=human_summary(case, case.lang))
    return {"status": case.status, "rerun": False}


# ---------------------------------------------------------------- the support agent

def _require_human(case: Case) -> None:
    if case.status not in ("with_agent", "waiting_for_rider"):
        raise CaseError(409, L(case.lang, "This case is not waiting for a support agent.", "该案件当前不需要客服处理。"))


async def human_rephrase(case: Case, text: str, purpose: str = "qa") -> dict:
    if not (text or "").strip():
        raise CaseError(400, L(case.lang, "Text is empty", "内容为空"))
    if purpose not in ("qa", "rider", "note"):
        raise CaseError(400, "purpose must be qa, rider or note")
    return await rephrase(text, purpose=purpose, mode=case.mode, lang=case.lang, rider_lang=case.rider_lang)


async def _send_to_rider(case: Case, text: str, purpose: str, original: str) -> dict:
    """Everything a person sends to the rider goes through the rephrase agent first."""
    r = await rephrase(text, purpose=purpose, mode=case.mode, lang=case.lang, rider_lang=case.rider_lang)
    m = {"text": r["rephrased"], "original": original, "at": _now(), "kind": purpose}
    case.human_messages.append(m)
    if purpose != "note":          # a decision note reaches the rider on the outcome card itself
        publish(case, "rider", "support_message", text=m["text"], at=m["at"], sender="Ryde Support")
    return m


async def human_ask(case: Case, question: str, original: str | None = None) -> dict:
    _require_human(case)
    question = (question or "").strip()
    if not question:
        raise CaseError(400, L(case.lang, "Question is empty", "问题为空"))
    entry = {"id": f"Q{len(case.qa_log) + 1}", "original": (original or question).strip(), "question": question,
             "at": _now(), "status": "answering"}
    case.qa_log.append(entry)
    publish(case, "human", "qa", entry=dict(entry))
    res = await case_qa.answer(case.record(), question, mode=case.mode, lang=case.lang)
    entry.update({"answer": res["answer"], "citations": res["citations"], "found": res["found"],
                  "used_model": res["used_model"]})
    if res["found"]:
        entry["status"] = "answered"
    else:
        sent = await _send_to_rider(case, question, "rider", question)
        entry.update({"status": "asked_rider", "sent_to_rider": sent["text"]})
        set_status(case, "waiting_for_rider")
    publish(case, "human", "qa", entry=dict(entry))
    return entry


async def human_decision(case: Case, action: str, amount: float | None = None, note: str | None = None) -> dict:
    _require_human(case)
    note = (note or "").strip() or None
    rec = recommendation_of(case.ruling)
    if action not in ("approve", "adjust", "reject", "request_info"):
        raise CaseError(400, "action must be approve, adjust, reject or request_info")
    if action == "approve" and not rec:
        raise CaseError(400, L(case.lang, "There is no AI recommendation to approve for this case.", "该案件没有可批准的 AI 建议。"))
    if action == "adjust":
        if amount is None or not isinstance(amount, (int, float)) or amount < 0:
            raise CaseError(400, L(case.lang, "Adjust needs an amount of 0 or more.", "调整金额需为 0 或以上。"))
        if not note:
            raise CaseError(400, L(case.lang, "Adjust needs a note explaining the amount.", "调整金额需要填写说明。"))
    if action == "request_info":
        if not note:
            raise CaseError(400, L(case.lang, "Write what you need from the rider.", "请写明需要乘客提供什么。"))
        sent = await _send_to_rider(case, note, "rider", note)
        entry = {"id": f"Q{len(case.qa_log) + 1}", "original": note, "question": note, "at": _now(), "status": "asked_rider",
                 "kind": "info_request", "answer": None, "citations": [], "found": False, "sent_to_rider": sent["text"]}
        case.qa_log.append(entry)
        set_status(case, "waiting_for_rider")
        publish(case, "human", "qa", entry=dict(entry))
        return {"status": case.status, "entry": entry}

    sent_note = (await _send_to_rider(case, note, "note", note))["text"] if note else None
    dtype = (case.ticket or {}).get("dispute_type")
    card = human_outcome(action, amount, sent_note, rec, dtype, case.tools, case.reference, case.rider_lang)
    case.decision = {"action": action, "amount": amount if action == "adjust" else (rec or {}).get("refund_amount") if action == "approve" else 0.0,
                     "note": note, "note_sent": sent_note, "recommendation": rec, "at": _now()}
    case.outcome = card
    set_status(case, "resolved_by_human")
    publish(case, "human", "decision", decision=case.decision)
    publish(case, "rider", "outcome", card=card)
    return {"status": case.status, "decision": case.decision, "card": card}


def list_cases() -> list[dict]:
    return [{"id": c.id, "reference": c.reference, "status": c.status,
             "needs_human": c.status in ("with_agent", "waiting_for_rider"),
             "dispute_type": (c.ticket or {}).get("dispute_type")} for c in CASES.values()]
