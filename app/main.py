"""RydeResolve FastAPI service.

Endpoints:
- GET  /                          web UI
- GET  /api/health                mode / provider / model
- GET  /api/disputes, /api/trips  sample disputes and trips
- GET  /api/file/stream           free-text complaint (+ optional trip; else auto-matched) -> SSE event stream
- POST /api/file                  same, synchronous (tests / integration)
- GET  /api/resolve/{id}/stream   SSE for a preset dispute
- POST /api/resolve/{id}          synchronous run of a preset dispute
- Demo login: GET /api/auth/accounts, POST /api/auth/login | logout, GET /api/auth/me. Every data endpoint needs the
  signed session cookie (401 otherwise); the rider_id always comes from the session. Console endpoints need the
  support role (403 for riders). POST /api/rider/find-trip: stage 1, which of the rider's trips the story is about.
- Three-pane demo (one in-memory Case per rider dispute, see app/case_store.py):
  POST /api/cases, GET /api/cases, GET /api/cases/{id}, GET /api/cases/{id}/events (SSE, every event tagged with `pane`),
  POST /api/cases/{id}/rider-message, POST /api/cases/{id}/human/rephrase | ask | decision

All run endpoints accept `lang=en|zh` (default en) for the language of human-readable output.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app import auth as A
from app import case_store as CS
from app.rider_match import find_trip, owns_trip
from app.config import settings, STATIC_DIR
from app.i18n import norm_lang, L
from app.orchestrator import resolve
from app.tools.fixtures import list_disputes, list_trips, rider_scope

app = FastAPI(title="RydeResolve", version="0.1.0",
              description="Multi-agent autonomous dispute resolution for ride-hailing; Tencent Cloud AI CAN DO IT Hackathon 2026")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_mode": settings.effective_mode,
        "llm_provider": settings.llm_provider if settings.effective_mode == "llm" else None,
        "model": settings.llm_model if settings.effective_mode == "llm" else None,
        "hunyuan_model": settings.llm_model,  # legacy field name, kept for older front-ends
        "has_api_key": settings.has_api_key,
        "escalation_threshold": settings.escalation_threshold,
    }


# ---- demo login ----
@app.get("/api/auth/accounts")
async def auth_accounts():
    """Demo accounts for the login screen. Demo only: no password."""
    return {"riders": A.accounts(), "drivers": A.driver_accounts(), "support": {"role": "support"}}


@app.post("/api/auth/login")
async def auth_login(payload: dict):
    """Sign in as a demo rider ({"rider_id": ...}), driver ({"role": "driver", "driver_id": ...}) or the support agent."""
    if payload.get("role") == "support":
        sess = {"role": "support"}
    elif payload.get("role") == "driver":
        did = (payload.get("driver_id") or "").strip()
        if did not in {a["driver_id"] for a in A.driver_accounts()}:
            raise HTTPException(status_code=400, detail="Unknown demo account")
        sess = {"role": "driver", "driver_id": did}
    else:
        rid = (payload.get("rider_id") or "").strip()
        if rid not in {a["rider_id"] for a in A.accounts()}:
            raise HTTPException(status_code=400, detail="Unknown demo account")
        sess = {"role": "rider", "rider_id": rid}
    return _set_session(JSONResponse({"ok": True, **sess}), sess)


@app.post("/api/auth/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(A.COOKIE, path="/")
    return resp


def _set_session(resp, sess: dict):
    resp.set_cookie(A.COOKIE, A.sign(A.cookie_payload(sess)), max_age=A.MAX_AGE, httponly=True, samesite="lax", path="/")
    return resp


@app.get("/api/auth/me")
async def auth_me(sess: dict = Depends(A.any_session)):
    if sess["role"] == "support":
        return {"role": "support", "rider_id": None, "name": None, "stories": []}
    if sess["role"] == "driver":
        names = {a["driver_id"]: a["name"] for a in A.driver_accounts()}
        return {"role": "driver", "driver_id": sess["driver_id"], "name": names.get(sess["driver_id"]), "stories": [],
                "home": {"rider_id": sess["home"]["rider_id"]} if sess.get("home") else None}
    names = {a["rider_id"]: a["name"] for a in A.accounts()}
    return {"role": "rider", "rider_id": sess["rider_id"], "name": names.get(sess["rider_id"]),
            "stories": A.stories_for(sess["rider_id"])}


# ---- demo Rider | Driver toggle ----
def _rider_open_case(rider_id: str) -> "CS.Case | None":
    mine = [c for c in CS.CASES.values() if c.rider_id == rider_id and c.ticket]
    return mine[-1] if mine else None


@app.get("/api/session/toggle")
async def session_toggle(sess: dict = Depends(A.any_session)):
    """State of the Rider | Driver toggle: who each side is and how many questions wait on each side.
    Counts only; the driver's details are not shown on the rider side."""
    if sess["role"] == "support":
        raise HTTPException(status_code=403, detail="Not for support agents")
    rider_id = sess["rider_id"] if sess["role"] == "rider" else (sess.get("home") or {}).get("rider_id")
    names = {a["rider_id"]: a["name"] for a in A.accounts()}
    rider = None
    if rider_id:
        pend = sum(c.pending()["rider"] for c in CS.CASES.values() if c.rider_id == rider_id)
        rider = {"id": rider_id, "name": names.get(rider_id), "pending": pend}
    driver = None
    if sess["role"] == "driver":
        did = sess["driver_id"]
        driver = {"id": did, "pending": sum(1 for q in CS.driver_questions(did) if q["status"] == "waiting")}
    else:
        c = _rider_open_case(rider_id)
        if c and c.driver_id:
            driver = {"id": None, "case_id": c.id, "pending": c.pending()["driver"]}
    # the demo driver list (the same public list as the login page) is only for the picker when there is no case
    return {"role": sess["role"], "can_switch": A.role_switch_allowed(), "rider": rider, "driver": driver,
            "drivers": A.driver_accounts() if A.role_switch_allowed() and not driver else []}


@app.post("/api/session/role")
async def session_role(payload: dict, sess: dict = Depends(A.any_session)):
    """Demo only (DEMO_ROLE_SWITCH): switch between the rider and the driver of the rider's case. The rider session is
    kept inside the driver session, so switching back needs no new login."""
    if not A.role_switch_allowed():
        raise HTTPException(status_code=403, detail="Role switching is off (DEMO_ROLE_SWITCH)")
    if sess["role"] == "support":
        raise HTTPException(status_code=403, detail="Not for support agents")
    home = sess if sess["role"] == "rider" else sess.get("home")
    want = payload.get("role")
    if want == "rider":
        if not home:
            raise HTTPException(status_code=403, detail="This session has no rider to switch back to")
        new = {"role": "rider", "rider_id": home["rider_id"]}
    elif want == "driver":
        cid = (payload.get("case_id") or "").strip()
        if cid:
            case = CS.CASES.get(cid)
            if not case or not home or case.rider_id != home["rider_id"] or not case.driver_id:
                raise HTTPException(status_code=404, detail="Unknown case")
            did = case.driver_id
        else:
            did = (payload.get("driver_id") or "").strip()
            if did not in {a["driver_id"] for a in A.driver_accounts()}:
                raise HTTPException(status_code=400, detail="Unknown demo account")
        new = {"role": "driver", "driver_id": did, "home": home}
    else:
        raise HTTPException(status_code=400, detail="role must be rider or driver")
    return _set_session(JSONResponse({"ok": True, "role": new["role"]}), new)


# ---- driver: receive questions from support, reply ----
@app.get("/api/driver/questions")
async def driver_questions(sess: dict = Depends(A.driver_session)):
    """Questions from support on cases whose trip this driver drove. Nothing else about the case."""
    return {"questions": CS.driver_questions(sess["driver_id"])}


@app.post("/api/driver/reply")
async def driver_reply(payload: dict, sess: dict = Depends(A.driver_session)):
    return await _call(CS.driver_reply(sess["driver_id"], payload.get("text") or "", payload.get("question_id")))


@app.get("/api/driver/events")
async def driver_events(sess: dict = Depends(A.driver_session)):
    """SSE for this driver only: support typing, new questions, reply acknowledgements."""
    did = sess["driver_id"]
    q: asyncio.Queue = asyncio.Queue()
    CS.DRIVER_SUBS.setdefault(did, set()).add(q)

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            CS.DRIVER_SUBS.get(did, set()).discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/disputes")
async def get_disputes(sess: dict = Depends(A.session)):
    with rider_scope(sess["rider_id"]):
        return {"disputes": list_disputes()}


@app.get("/api/trips")
async def get_trips(sess: dict = Depends(A.session)):
    """Trips a complaint can be filed against: the signed-in rider's own (all of them for support)."""
    with rider_scope(sess["rider_id"]):
        return {"trips": list_trips()}


@app.post("/api/rider/find-trip")
async def rider_find_trip(payload: dict, sess: dict = Depends(A.rider_session)):
    """Stage 1: which of the signed-in rider's trips is this story about? No case is created here."""
    lang = norm_lang(payload.get("lang"))
    story = (payload.get("story") or "").strip()
    if not story:
        raise HTTPException(status_code=400, detail=L(lang, "Tell us what happened first", "请先描述发生了什么"))
    if len(story) > 2000:
        raise HTTPException(status_code=400, detail=L(lang, "Message too long (max 2000 characters)", "内容过长（上限 2000 字）"))
    return find_trip(story, sess["rider_id"], lang)


def _norm_draft(trip_id: str | None, complaint: str | None, lang: str = "en") -> dict | None:
    """Validate and normalise a free-text complaint draft.

    trip_id is optional: empty or "auto" means match the story to one of the rider's recent trips.
    """
    if not complaint or not complaint.strip():
        return None
    tid = (trip_id or "").strip()
    if tid.lower() == "auto":
        tid = ""
    text = complaint.strip()
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail=L(lang, "Complaint too long (max 2000 characters)", "投诉内容过长（上限 2000 字）"))
    return {"trip_id": tid or None, "complaint": text}


@app.get("/api/file/stream")
async def file_stream(complaint: str, trip_id: str | None = None, mode: str | None = None, lang: str | None = None,
                      sess: dict = Depends(A.session)):
    """Free-text complaint + SSE stream.

    The rider supplies only their own words, and optionally a trip (omitted / "auto": matched from the story);
    the intake agent decides the dispute type.
    """
    lang = norm_lang(lang)
    draft = _norm_draft(trip_id, complaint, lang)
    if draft is None:
        raise HTTPException(status_code=400, detail=L(lang, "complaint text is required", "缺少 complaint 投诉原文"))
    _check_trip(sess, draft.get("trip_id"), lang)
    m = _norm_mode(mode)

    async def event_gen():
        try:
            async for ev in resolve(None, mode=m, draft=draft, lang=lang, rider_id=sess["rider_id"]):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _check_trip(sess: dict, trip_id: str | None, lang: str) -> None:
    """A rider may only file against their own trip (rider_id from the session, never from the request)."""
    if trip_id and sess["role"] == "rider" and not owns_trip(sess["rider_id"], trip_id):
        raise HTTPException(status_code=403, detail=L(lang, "That trip is not in your account.", "该行程不在您的账户中。"))


@app.post("/api/file")
async def file_sync(payload: dict, sess: dict = Depends(A.session)):
    """Free-text complaint, synchronous: returns the ruling and all events (tests / integration)."""
    lang = norm_lang(payload.get("lang"))
    draft = _norm_draft(payload.get("trip_id"), payload.get("complaint"), lang)
    if draft is None:
        raise HTTPException(status_code=400, detail=L(lang, "complaint text is required", "缺少 complaint 投诉原文"))
    _check_trip(sess, draft.get("trip_id"), lang)
    events: list[dict] = []
    ruling = None
    async for ev in resolve(None, mode=_norm_mode(payload.get("mode")), draft=draft, lang=lang, rider_id=sess["rider_id"]):
        events.append(ev)
        if ev.get("type") == "ruling":
            ruling = ev.get("ruling")
    unresolved = next((e for e in events if e.get("type") == "trip_unresolved"), None)
    if unresolved:
        # No trip could be matched to the story: nothing is ruled, the rider picks a trip and re-submits.
        return {"status": "trip_unresolved", "message": unresolved.get("message"),
                "candidates": unresolved.get("candidates", []), "ruling": None, "events": events}
    if ruling is None:
        raise HTTPException(status_code=500, detail=L(lang, "No ruling produced", "未产生裁决"))
    err = next((e for e in events if e.get("type") == "error"), None)
    if err:
        raise HTTPException(status_code=502, detail=err.get("message"))
    # The free-text path emits two intake phases (before / after filing); take the one carrying the ticket
    ticket = next((e.get("ticket") for e in events
                   if e.get("type") == "phase" and e.get("phase") == "intake" and e.get("ticket")), None)
    triage = next((e for e in events if e.get("type") == "triage_result"), None)
    filed = next((e.get("ticket") for e in events if e.get("type") == "ticket_filed"), None)
    matched = next((e for e in events if e.get("type") == "trip_matched"), None)
    return {
        "dispute_id": ruling.get("dispute_id"),
        "triage": {k: v for k, v in (triage or {}).items() if k != "type"},
        "ticket": ticket,
        "filed_ticket": filed,
        "trip_match": {k: v for k, v in matched.items() if k != "type"} if matched else None,
        "ruling": ruling,
        "events": events,
    }


def _norm_mode(mode: str | None) -> str | None:
    """Normalise the query parameter to llm / deterministic / None (follow global setting)."""
    if not mode:
        return None
    m = mode.strip().lower()
    if m in ("llm", "real", "gemini", "hunyuan"):
        return "llm"
    if m in ("deterministic", "det", "fallback", "offline", "scripted"):
        return "deterministic"
    return None


def _check_dispute(sess: dict, dispute_id: str) -> None:
    with rider_scope(sess["rider_id"]):
        if dispute_id not in {d["dispute_id"] for d in list_disputes()}:
            raise HTTPException(status_code=404, detail="Dispute not found")


@app.get("/api/resolve/{dispute_id}/stream")
async def resolve_stream(dispute_id: str, mode: str | None = None, lang: str | None = None,
                         sess: dict = Depends(A.session)):
    """SSE stream; each event is pushed as `data: <json>`.

    ?mode=llm forces the real LLM; ?mode=deterministic forces the scripted fallback; default follows .env.
    """
    _check_dispute(sess, dispute_id)
    m = _norm_mode(mode)
    lang = norm_lang(lang)

    async def event_gen():
        try:
            async for ev in resolve(dispute_id, mode=m, lang=lang, rider_id=sess["rider_id"]):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/resolve/{dispute_id}")
async def resolve_sync(dispute_id: str, mode: str | None = None, lang: str | None = None,
                       sess: dict = Depends(A.session)):
    """Run the whole flow synchronously; return the final ruling and all events."""
    _check_dispute(sess, dispute_id)
    lang = norm_lang(lang)
    events: list[dict] = []
    ruling = None
    async for ev in resolve(dispute_id, mode=_norm_mode(mode), lang=lang, rider_id=sess["rider_id"]):
        events.append(ev)
        if ev.get("type") == "ruling":
            ruling = ev.get("ruling")
    if ruling is None:
        raise HTTPException(status_code=500, detail=L(lang, "No ruling produced", "未产生裁决"))
    return {"dispute_id": dispute_id, "ruling": ruling, "events": events}


# ---- three-pane demo: cases ----
def _case_or_404(case_id: str, sess: dict) -> "CS.Case":
    """The case, if this session may see it. Someone else's case looks exactly like a missing one."""
    try:
        case = CS.get_case(case_id)
    except CS.CaseError as e:
        raise HTTPException(status_code=e.status, detail=e.message)
    if not CS.can_view(case, sess):
        raise HTTPException(status_code=404, detail="Unknown case")
    return case


async def _call(coro):
    try:
        return await coro
    except CS.CaseError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.post("/api/cases")
async def create_case(payload: dict, sess: dict = Depends(A.rider_session)):
    """Start a case once the rider has confirmed a trip (stage 1). The trip must be one of the signed-in rider's;
    any rider_id in the body is ignored."""
    lang = norm_lang(payload.get("lang"))
    tid = (payload.get("trip_id") or "").strip()
    if not tid or tid.lower() == "auto":
        raise HTTPException(status_code=400, detail=L(lang, "Confirm the trip first", "请先确认行程"))
    _check_trip(sess, tid, lang)
    case = await _call(CS.start_case(payload.get("story") or payload.get("complaint") or "", trip_id=tid,
                                     mode=_norm_mode(payload.get("mode")), lang=lang, rider_id=sess["rider_id"]))
    return case.snapshot()


@app.get("/api/cases")
async def cases_list(sess: dict = Depends(A.session)):
    """A rider's own cases; for the support agent, every case that was handed to a person."""
    return {"cases": CS.list_cases(sess)}


@app.get("/api/cases/{case_id}")
async def case_get(case_id: str, sess: dict = Depends(A.session)):
    snap = _case_or_404(case_id, sess).snapshot()
    if sess["role"] == "rider":                 # the console's view of the case is for support agents only
        for k in ("summary", "qa_log", "human_messages"):
            snap.pop(k, None)
    return snap


@app.get("/api/cases/{case_id}/events")
async def case_events(case_id: str, after: int = 0, sess: dict = Depends(A.session)):
    """SSE: every event of the case (history after `after`, then live). Each carries `pane`: rider | room | human | case."""
    case = _case_or_404(case_id, sess)
    q: asyncio.Queue = asyncio.Queue()
    case.subscribers.add(q)
    # riders never receive the console's events, nor what was asked of the driver
    hidden = ("human", "driver") if sess["role"] == "rider" else ()
    backlog = [e for e in case.events if e["seq"] > after and e["pane"] not in hidden]

    async def gen():
        last = after
        try:
            for ev in backlog:
                last = ev["seq"]
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if ev["seq"] <= last or ev["pane"] in hidden:
                    continue
                last = ev["seq"]
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        finally:
            case.subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/cases/{case_id}/rider-message")
async def case_rider_message(case_id: str, payload: dict, sess: dict = Depends(A.rider_session)):
    case = _case_or_404(case_id, sess)
    return await _call(CS.rider_message(case, payload.get("text") or "", payload.get("trip_id")))


@app.post("/api/cases/{case_id}/human/rephrase")
async def case_rephrase(case_id: str, payload: dict, sess: dict = Depends(A.support_session)):
    case = _case_or_404(case_id, sess)
    return await _call(CS.human_rephrase(case, payload.get("text") or "", payload.get("purpose") or "qa"))


@app.post("/api/cases/{case_id}/human/route")
async def case_route(case_id: str, payload: dict, sess: dict = Depends(A.support_session)):
    """Who a question would go to if the record cannot answer it (Auto), shown before anything is sent."""
    case = _case_or_404(case_id, sess)
    return await _call(CS.human_route(case, payload.get("question") or ""))


@app.post("/api/cases/{case_id}/human/ask")
async def case_ask(case_id: str, payload: dict, sess: dict = Depends(A.support_session)):
    case = _case_or_404(case_id, sess)
    return await _call(CS.human_ask(case, payload.get("question") or "", payload.get("original"),
                                    (payload.get("recipient") or "auto").strip().lower(), payload.get("party_text")))


@app.post("/api/cases/{case_id}/human/decision")
async def case_decision(case_id: str, payload: dict, sess: dict = Depends(A.support_session)):
    case = _case_or_404(case_id, sess)
    amt = payload.get("amount")
    try:
        amt = float(amt) if amt not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="amount must be a number")
    return await _call(CS.human_decision(case, payload.get("action") or "", amt, payload.get("note")))


# ---- static front-end ----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _page(name: str):
    p = STATIC_DIR / name
    if p.exists():
        # "/" is the login page or the app depending on the session: never let the browser reuse a cached copy
        return FileResponse(str(p), headers={"Cache-Control": "no-store"})
    return JSONResponse({"message": "Front-end not found; use /api/disputes and /api/resolve/{id}/stream"})


@app.get("/")
async def index(request: Request):
    """Signed in: the three-pane demo. Otherwise: the demo login screen."""
    return _page("three.html" if A.verify(request.cookies.get(A.COOKIE)) else "login.html")


@app.get("/classic")
async def classic(request: Request):
    """The original single group-chat UI (needs a session too)."""
    if not A.verify(request.cookies.get(A.COOKIE)):
        return RedirectResponse("/", status_code=303)
    return _page("index.html")


def main():
    import uvicorn
    print("=" * 60)
    print(" RydeResolve: multi-agent dispute resolution")
    print(f"  LLM mode: {settings.effective_mode}"
          + (f" ({settings.llm_provider} {settings.llm_model})" if settings.effective_mode == "llm"
             else " (deterministic fallback, no API key needed)"))
    print(f"  Escalation threshold: confidence < {settings.escalation_threshold} -> human review")
    print(f"  Open: http://localhost:{settings.port}")
    print("=" * 60)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
