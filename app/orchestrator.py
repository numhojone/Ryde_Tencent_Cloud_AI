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

    # ---------- 阶段三：安全网（确定性证据完备性校验）----------
    # 无论模型给出多高的置信度，只要证据基础不牢就拦下升级人工。
    ruling = await apply_safety_net(ruling, ticket["trip_id"], emit, lang)

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
