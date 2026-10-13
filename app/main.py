"""RydeResolve FastAPI service.

Endpoints:
- GET  /                          web UI
- GET  /api/health                mode / provider / model
- GET  /api/disputes, /api/trips  sample disputes and trips
- GET  /api/file/stream           free-text complaint + trip -> SSE event stream (main demo path)
- POST /api/file                  same, synchronous (tests / integration)
- GET  /api/resolve/{id}/stream   SSE for a preset dispute
- POST /api/resolve/{id}          synchronous run of a preset dispute

All run endpoints accept `lang=en|zh` (default en) for the language of human-readable output.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import settings, STATIC_DIR
from app.i18n import norm_lang, L
from app.orchestrator import resolve
from app.tools.fixtures import list_disputes, list_trips

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


@app.get("/api/disputes")
async def get_disputes():
    return {"disputes": list_disputes()}


@app.get("/api/trips")
async def get_trips():
    """Trips a complaint can be filed against (evidence must come from a real trip)."""
    return {"trips": list_trips()}


def _norm_draft(trip_id: str | None, complaint: str | None, lang: str = "en") -> dict | None:
    """Validate and normalise a free-text complaint draft."""
    if not complaint or not complaint.strip():
        return None
    tid = (trip_id or "").strip()
    if not tid:
        raise HTTPException(status_code=400, detail=L(lang, "trip_id is required: evidence must come from a real trip", "缺少 trip_id：证据必须来自一条真实行程"))
    text = complaint.strip()
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail=L(lang, "Complaint too long (max 2000 characters)", "投诉内容过长（上限 2000 字）"))
    return {"trip_id": tid, "complaint": text}


@app.get("/api/file/stream")
async def file_stream(trip_id: str, complaint: str, mode: str | None = None, lang: str | None = None):
    """Free-text complaint + SSE stream.

    The rider supplies only their own words + a trip; the intake agent decides the dispute type.
    """
    lang = norm_lang(lang)
    draft = _norm_draft(trip_id, complaint, lang)
    m = _norm_mode(mode)

    async def event_gen():
        try:
            async for ev in resolve(None, mode=m, draft=draft, lang=lang):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/file")
async def file_sync(payload: dict):
    """Free-text complaint, synchronous: returns the ruling and all events (tests / integration)."""
    lang = norm_lang(payload.get("lang"))
    draft = _norm_draft(payload.get("trip_id"), payload.get("complaint"), lang)
    if draft is None:
        raise HTTPException(status_code=400, detail=L(lang, "complaint text is required", "缺少 complaint 投诉原文"))
    events: list[dict] = []
    ruling = None
    async for ev in resolve(None, mode=_norm_mode(payload.get("mode")), draft=draft, lang=lang):
        events.append(ev)
        if ev.get("type") == "ruling":
            ruling = ev.get("ruling")
    if ruling is None:
        raise HTTPException(status_code=500, detail=L(lang, "No ruling produced", "未产生裁决"))
    err = next((e for e in events if e.get("type") == "error"), None)
    if err:
        raise HTTPException(status_code=502, detail=err.get("message"))
    # The free-text path emits two intake phases (before / after filing); take the one carrying the ticket
    ticket = next((e.get("ticket") for e in events
                   if e.get("type") == "phase" and e.get("phase") == "intake" and e.get("ticket")), None)
    triage = next((e for e in events if e.get("type") == "triage_result"), None)
    return {
        "dispute_id": ruling.get("dispute_id"),
        "triage": {k: v for k, v in (triage or {}).items() if k != "type"},
        "ticket": ticket,
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


@app.get("/api/resolve/{dispute_id}/stream")
async def resolve_stream(dispute_id: str, mode: str | None = None, lang: str | None = None):
    """SSE stream; each event is pushed as `data: <json>`.

    ?mode=llm forces the real LLM; ?mode=deterministic forces the scripted fallback; default follows .env.
    """
    m = _norm_mode(mode)
    lang = norm_lang(lang)

    async def event_gen():
        try:
            async for ev in resolve(dispute_id, mode=m, lang=lang):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/resolve/{dispute_id}")
async def resolve_sync(dispute_id: str, mode: str | None = None, lang: str | None = None):
    """Run the whole flow synchronously; return the final ruling and all events."""
    lang = norm_lang(lang)
    events: list[dict] = []
    ruling = None
    async for ev in resolve(dispute_id, mode=_norm_mode(mode), lang=lang):
        events.append(ev)
        if ev.get("type") == "ruling":
            ruling = ev.get("ruling")
    if ruling is None:
        raise HTTPException(status_code=500, detail=L(lang, "No ruling produced", "未产生裁决"))
    return {"dispute_id": dispute_id, "ruling": ruling, "events": events}


# ---- static front-end ----
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"message": "Front-end not found; use /api/disputes and /api/resolve/{id}/stream"})


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
