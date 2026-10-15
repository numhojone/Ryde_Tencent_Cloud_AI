"""Orchestrator: dispute in -> two advocates build cases in parallel -> judge verifies independently -> safety net.

resolve() 是异步生成器，逐条 yield 事件，供 SSE 实时推送。
全程工具调用与智能体推理都通过事件暴露，便于 demo 可见。
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncGenerator

from app.agents.driver_advocate import DriverAdvocate
from app.agents.intake import IntakeAgent, type_label
from app.agents.judge import Judge
from app.agents.rider_advocate import RiderAdvocate
from app.config import settings
from app.i18n import L, norm_lang
from app.safety_net import apply as apply_safety_net
from app.tools.fixtures import get_trip_parties, load_dispute_ticket
from app.tools import call_tool, summarize_for_log


_SENTINEL = object()


async def _triage_draft(draft: dict, emit, mode: str | None, lang: str = "en") -> dict:
    """把乘客自由文本投诉转成一张正式工单。

    关键：description 保留乘客原话，不做任何改写 —— 下游三个智能体读到的就是用户敲进去的那句话。
    """
    await emit({"type": "phase", "phase": "intake",
                "message": L(lang, "Intake: reading the rider's complaint and working out the dispute type", "受理乘客提交的投诉，智能体解读争议类型")})
    await emit({"type": "complaint_received", "trip_id": draft["trip_id"],
                "complaint": draft["complaint"]})

    ia = IntakeAgent(emit, mode=mode, lang=lang)
    res = await ia.run({"draft": draft})
    triage = res.output.model_dump() if res.output else None
    if not triage:
        raise RuntimeError(L(lang, "The intake agent produced no classification", "受理分类智能体未产出分类结果"))

    parties = get_trip_parties(draft["trip_id"])
    import datetime as _dt
    import uuid as _uuid
    dispute_id = f"DISP-{_uuid.uuid4().hex[:6].upper()}"
    ticket = {
        "dispute_id": dispute_id,
        "trip_id": draft["trip_id"],
        "filed_by": "rider",
        "rider_id": parties["rider_id"],
        "driver_id": parties["driver_id"],
        "dispute_type": triage["dispute_type"],
        # 乘客原话，一字不改地交给下游
        "description": draft["complaint"],
        "filed_at": _dt.datetime.now().astimezone().isoformat(),
        "requested_resolution": triage.get("requested_resolution"),
        "requested_amount": triage.get("requested_amount"),
        "source": "free_text",
        "triage": triage,
    }
    await emit({
        "type": "triage_result",
        "dispute_id": dispute_id,
        "dispute_type": ticket["dispute_type"],
        "dispute_type_label": type_label(ticket["dispute_type"], lang),
        "classification_confidence": triage["classification_confidence"],
        "classification_reasoning": triage["classification_reasoning"],
        "normalized_claim": triage["normalized_claim"],
        "detected_signals": triage.get("detected_signals", []),
        "requested_amount": triage.get("requested_amount"),
        "complaint": draft["complaint"],
    })
    return ticket


async def _safety_case_file(ticket: dict, emit, lang: str) -> dict:
    """Policy section 5: AI may gather evidence and prepare a case file, but may not rule, assign fault or recommend a resolution."""
    await emit({"type": "phase", "phase": "safety_intake",
                "message": L(lang, "Safety indicators found (policy 5.2): the AI will only gather evidence and prepare a case file; it cannot rule",
                                   "发现安全指标（政策 5.2）：AI 只收集证据并整理案件材料，不得裁决")})
    tid = ticket["trip_id"]
    calls = [("get_trip_data", {"trip_id": tid}), ("get_gps_telemetry", {"trip_id": tid}), ("get_chat_logs", {"trip_id": tid}),
             ("get_app_events", {"trip_id": tid}), ("get_rider_profile", {"rider_id": ticket["rider_id"]}),
             ("get_driver_profile", {"driver_id": ticket["driver_id"]}), ("get_policy", {"dispute_type": "safety_incident"})]
    g: dict = {}
    for name, args in calls:
        await emit({"type": "tool_call", "role": "safety_case", "agent": "safety_case", "tool": name, "args": args, "summary": summarize_for_log(name, args)})
        res = call_tool(name, args)
        if res["ok"]:
            g[name] = res["result"]
        await emit({"type": "tool_result", "role": "safety_case", "agent": "safety_case", "tool": name, "ok": res["ok"],
                    "result": {k: (v if not isinstance(v, list) else f"{len(v)} items") for k, v in (res.get("result") or {}).items()} if res["ok"] else res})
    pts = (g.get("get_gps_telemetry") or {}).get("points", [])
    max_speed = max([p.get("speed_kmh", 0) for p in pts], default=0)
    msgs = (g.get("get_chat_logs") or {}).get("messages", [])
    events = (g.get("get_app_events") or {}).get("events", [])
    facts = [
        L(lang, f"Rider's account (verbatim): {ticket['description']}", f"乘客陈述（原话）：{ticket['description']}"),
        L(lang, f"GPS: {len(pts)} points, maximum recorded speed {max_speed} km/h", f"GPS：{len(pts)} 个点，记录到的最高车速 {max_speed} 公里/小时"),
        L(lang, f"Chat log: {len(msgs)} message(s)", f"聊天记录：{len(msgs)} 条"),
        L(lang, f"App events: {len(events)} ({', '.join(e.get('event_type', '?') for e in events[:6])})", f"App 事件：{len(events)} 条（{', '.join(e.get('event_type', '?') for e in events[:6])}）"),
    ]
    interim = [
        L(lang, "Temporarily suspend the accused driver's account and block new trip acceptance pending review (policy 5.3).", "审核期间暂停被指控司机的账号并禁止接新单（政策 5.3）。"),
        L(lang, "Lifted automatically if the human reviewer finds no violation (policy 5.3).", "若人工审核认定无违规，则自动解除（政策 5.3）。"),
    ]
    summary = L(lang, "Safety incident: escalated to human review under policy 5.1/5.2. The AI has not determined fault or recommended a resolution. "
                      "Case file and suggested interim measures (5.3) are attached for the reviewer.",
                      "安全事件：依政策 5.1/5.2 升级人工复核。AI 未判定责任，也未建议处理方案。案件材料与建议的临时措施（5.3）已附上。")
    return {"dispute_id": ticket["dispute_id"], "ruling": "escalated", "refund_amount": None, "confidence_score": 1.0,
            "reasoning": summary, "evidence_cited": facts, "escalation_required": True, "escalation_summary": summary,
            "policy_clauses": ["5.1", "5.2", "5.3"],
            "policy_path": {"path": "human_review", "required_confidence": None, "fraud_flag": False, "clause": "5.2", "reasons": [summary], "human_approval_only": False},
            "case_file": {"facts": facts, "interim_measures": interim, "requested_refund": ticket.get("requested_amount")}}


async def _run_flow(dispute_id: str, emit, mode: str | None = None,
                    draft: dict | None = None, lang: str = "en") -> None:
    if draft is not None:
        ticket = await _triage_draft(draft, emit, mode, lang)
    else:
        ticket = load_dispute_ticket(dispute_id)
    t0 = time.time()

    await emit({
        "type": "phase", "phase": "intake",
        "message": (
            L(lang, f"Intake: dispute {ticket['dispute_id']} ({ticket['dispute_type']})",
                    f"受理争议 {ticket['dispute_id']}（{ticket['dispute_type']}）")
            if draft is None else
            L(lang, f"Ticket {ticket['dispute_id']} filed: {type_label(ticket['dispute_type'], lang)}",
                    f"工单 {ticket['dispute_id']} 已建档：{type_label(ticket['dispute_type'], lang)}")
        ),
        "ticket": {
            "dispute_id": ticket["dispute_id"], "trip_id": ticket["trip_id"],
            "filed_by": ticket["filed_by"], "dispute_type": ticket["dispute_type"],
            "description": ticket["description"], "requested_amount": ticket.get("requested_amount"),
        },
    })

    # ---------- Safety incidents never go to the advocates or the judge ----------
    if ticket["dispute_type"] == "safety_incident":
        ruling = await _safety_case_file(ticket, emit, lang)
        await emit({"type": "ruling", "ruling": ruling, "elapsed_ms": round((time.time() - t0) * 1000)})
        await emit({"type": "done"})
        return

    # ---------- 阶段一：两位 advocate 并行 ----------
    await emit({"type": "phase", "phase": "advocates", "message": L(lang, "Rider and driver advocates gather evidence and build their cases in parallel", "乘客方与司机方辩护智能体并行取证、构建案件")})
    ctx = {"ticket": ticket}
    ra = RiderAdvocate(emit, mode=mode, lang=lang)
    da = DriverAdvocate(emit, mode=mode, lang=lang)
    rc, dc = await asyncio.gather(ra.run(ctx), da.run(ctx))

    rider_case = rc.output.model_dump() if rc.output else None
    driver_case = dc.output.model_dump() if dc.output else None
    await emit({"type": "phase", "phase": "cases_submitted",
                "message": L(lang, "Both cases submitted to the judge", "双方案件已提交法官"), "rider_case": rider_case, "driver_case": driver_case})

    # ---------- 阶段二：法官独立核验 ----------
    await emit({"type": "phase", "phase": "judge", "message": L(lang, "Judge independently calls the tools to verify the evidence and rule", "法官独立调用工具核验证据并裁决")})
    jctx = {"ticket": ticket, "cases": [rider_case or {}, driver_case or {}]}
    judge = Judge(emit, mode=mode, lang=lang)
    jr = await judge.run(jctx)

    ruling = jr.output.model_dump() if hasattr(jr.output, "model_dump") else jr.output
    if judge._mode() == "llm" and isinstance(ruling, dict):
        ruling = judge.post_process_llm(ruling, ticket, judge._gathered)

    # ---------- 阶段三：安全网（确定性证据完备性校验）----------
    # 无论模型给出多高的置信度，只要证据基础不牢就拦下升级人工。
    ruling = await apply_safety_net(ruling, ticket["trip_id"], emit, lang, ticket["dispute_type"])

    await emit({"type": "ruling", "ruling": ruling, "elapsed_ms": round((time.time() - t0) * 1000)})
    await emit({"type": "done"})


async def resolve(dispute_id: str | None = None, mode: str | None = None,
                  draft: dict | None = None, lang: str = "en") -> AsyncGenerator[dict, None]:
    """异步生成器：逐条产出事件，供 SSE 推送。

    mode:  None（跟随全局 .env） / "llm"（真实 LLM） / "deterministic"（确定性回退）。
    draft: {"trip_id": ..., "complaint": "乘客原话"} —— 给了就走自由文本受理路径，
           dispute_id 由系统生成；不给则按 dispute_id 读取预置 fixture 工单。
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await queue.put(ev)

    async def flow() -> None:
        try:
            await _run_flow(dispute_id, emit, mode=mode, draft=draft, lang=norm_lang(lang))
        except Exception as e:  # noqa: BLE001
            import traceback
            await queue.put({"type": "error", "message": f"{type(e).__name__}: {e}",
                             "trace": traceback.format_exc()})
        finally:
            await queue.put(_SENTINEL)

    task = asyncio.create_task(flow())
    while True:
        ev = await queue.get()
        if ev is _SENTINEL:
            break
        yield ev
    await task
