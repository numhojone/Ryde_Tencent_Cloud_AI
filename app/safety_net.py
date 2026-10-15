"""Safety net: a deterministic check that runs after the judge.

Rules (either one forces `escalated`):
  A. fewer than MIN_EVIDENCE_POINTS distinct items in the judge's evidence_cited;
  B. any evidence source (GPS / chat / app events) is empty or near-empty for the trip.
The model's own verdict is kept in `model_assessment`. Neither rule looks at the confidence score.

(原文) 安全网：在法官裁决之后追加一道确定性校验。

设计原则：
  * 法官（LLM）负责判断，安全网只负责"证据够不够"这一件事——它不重新判案，
    也不改结论，只在证据基础不牢时把案件拦下来交人工。
  * 规则是纯确定性的，与模型无关：任何一次运行、任何模型，同样的输入必然同样的结果。
  * 触发时保留模型原本的裁决与置信度，放在 `model_assessment` 字段里，
    这样 demo 能同时展示"模型的独立判断"和"安全网的覆盖"。

规则（满足任一即覆盖为 escalated）：
  1. 法官 evidence_cited 里去重后的数据点少于 MIN_EVIDENCE_POINTS 条；
  2. 该行程的任一证据源（gps_telemetry / chat_logs / app_events）为空或近空。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from app.i18n import L, CUR
from app.tools import summarize_for_log, call_tool

# 证据点下限：法官引用少于这么多条独立数据点，视为论证基础不足。
MIN_EVIDENCE_POINTS = 3

# 各证据源的"近空"阈值：低于该数量即视为空/近空。
# 阈值按"能否支撑结论"来定，而不是随便拍：
#   gps_telemetry < 3  → 连"是否到达过上车点"都无法判断
#   chat_logs     < 2  → 无法构成一次完整沟通（联系尝试要靠它举证）
#   app_events    < 2  → 无法还原计费/等待时间线
def _n(key):
    return lambda r: len((r or {}).get(key, []) or [])


def _present(path):
    def f(r):
        cur = r or {}
        for k in path:
            cur = (cur or {}).get(k) if isinstance(cur, dict) else None
        return len(cur) if isinstance(cur, (list, dict)) and cur else 0
    return f


# (tool, label, counter, minimum) per dispute type. The minimum is what is needed to support the conclusion:
#   route: GPS (was the route actually driven) + chat (was the rider told)
#   no-show: GPS (did the driver arrive) + chat (contact) + events (timeline)
#   fare: surge log (when did the multiplier change, was the rider notified) + chat
#   property: damage evidence record with at least one photo + chat
SOURCE_SPECS = {
    "route_deviation": [("get_gps_telemetry", "gps_telemetry", _n("points"), 3), ("get_chat_logs", "chat_logs", _n("messages"), 2)],
    "no_show_charge": [("get_gps_telemetry", "gps_telemetry", _n("points"), 3), ("get_chat_logs", "chat_logs", _n("messages"), 2), ("get_app_events", "app_events", _n("events"), 2)],
    "fare_dispute": [("get_fare_breakdown", "surge_log", _present(["surge_pricing_log"]), 1), ("get_chat_logs", "chat_logs", _n("messages"), 1)],
    "property_damage": [("get_damage_evidence", "damage_photos", _present(["damage_evidence", "photos"]), 1), ("get_chat_logs", "chat_logs", _n("messages"), 1)],
}

EventEmitter = Callable[[dict], Awaitable[None]]


def _distinct_evidence(evidence_cited: Any) -> list[str]:
    """把 evidence_cited 归一化成去重后的非空字符串列表。"""
    if not isinstance(evidence_cited, list):
        return []
    out, seen = [], set()
    for item in evidence_cited:
        if item is None:
            continue
        s = str(item).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


async def _noop(_ev: dict) -> None:
    return None


async def inspect(trip_id: str, emit: Optional[EventEmitter] = None, dtype: str = "no_show_charge") -> dict:
    """Re-fetch the evidence sources this dispute type depends on and count them.

    Deliberately calls the tools again instead of reusing what the judge fetched: the safety net is an
    independent check, and the calls are visible in the event stream.
    """
    emit = emit or _noop
    sources: dict[str, dict] = {}
    for tool_name, label, counter, threshold in SOURCE_SPECS.get(dtype, SOURCE_SPECS["no_show_charge"]):
        await emit({"type": "tool_call", "role": "safety_net", "tool": tool_name, "args": {"trip_id": trip_id},
                    "summary": summarize_for_log(tool_name, {"trip_id": trip_id})})
        res = call_tool(tool_name, {"trip_id": trip_id})
        count, error = (counter(res["result"]), None) if res["ok"] else (0, res.get("error"))
        near_empty = count < threshold
        await emit({"type": "tool_result", "role": "safety_net", "tool": tool_name, "ok": res["ok"],
                    "result": {label: count, "near_empty": near_empty}})
        sources[label] = {"tool": tool_name, "count": count, "threshold": threshold, "near_empty": near_empty, "error": error}
    return sources


async def apply(
    ruling: dict,
    trip_id: str,
    emit: Optional[EventEmitter] = None,
    lang: str = "en",
    dtype: str = "no_show_charge",
) -> dict:
    """Run the safety net over the judge's ruling; return the final (possibly overridden) ruling."""
    emit = emit or _noop

    if not isinstance(ruling, dict):
        return ruling

    await emit({"type": "phase", "phase": "safety_net",
                "message": L(lang, "Safety net: checking whether the evidence behind the ruling is sufficient (deterministic rules, independent of the model)",
                                   "安全网校验：核验裁决的证据基础是否充分（确定性规则，与模型无关）")})

    evidence = _distinct_evidence(ruling.get("evidence_cited"))
    sources = await inspect(trip_id, emit, dtype)

    already_escalated = ruling.get("ruling") == "escalated"
    reasons: list[str] = []
    if len(evidence) < MIN_EVIDENCE_POINTS:
        reasons.append(L(lang,
            f"The ruling cites only {len(evidence)} distinct data point(s), below the minimum of {MIN_EVIDENCE_POINTS}",
            f"裁决仅引用 {len(evidence)} 条独立数据点，低于下限 {MIN_EVIDENCE_POINTS} 条"))
    for label, info in sources.items():
        if info["near_empty"]:
            detail = L(lang, f"only {info['count']} (minimum {info['threshold']})",
                             f"仅 {info['count']} 条（下限 {info['threshold']} 条）")
            if info["error"]:
                detail += L(lang, f"; tool returned an error: {info['error']}", f"，工具返回错误：{info['error']}")
            reasons.append(L(lang, f"Evidence source {label} is empty or near-empty: {detail}",
                                   f"证据源 {label} 为空或近空：{detail}"))

    model_assessment = {
        "ruling": ruling.get("ruling"),
        "refund_amount": ruling.get("refund_amount"),
        "confidence_score": ruling.get("confidence_score"),
        "reasoning": ruling.get("reasoning"),
        "evidence_cited": list(ruling.get("evidence_cited") or []),
        "escalation_required": bool(ruling.get("escalation_required", False)),
    }
    check = {
        "distinct_evidence_points": len(evidence),
        "min_evidence_points": MIN_EVIDENCE_POINTS,
        "evidence_sources": sources,
    }

    final = dict(ruling)
    final["model_assessment"] = model_assessment
    final["safety_net"] = {"triggered": bool(reasons), "reasons": reasons, "checks": check}

    await emit({"type": "safety_net", "role": "safety_net",
                "triggered": bool(reasons), "reasons": reasons, "checks": check})

    if already_escalated and reasons:
        final["safety_net"]["note"] = L(lang, "Already escalated by the policy thresholds; the evidence gaps are added to the case file.", "已因政策阈值升级人工；证据缺口一并记入案件材料。")
        return final

    if not reasons:
        await emit({"type": "thinking", "role": "safety_net",
                    "content": L(lang,
                        f"Evidence base is sufficient ({len(evidence)} distinct data points, all three evidence sources pass); keeping the model's ruling {ruling.get('ruling')}.",
                        f"证据基础充分（{len(evidence)} 条独立数据点，三个证据源均达标），维持模型裁决 {ruling.get('ruling')}。")})
        return final

    # ---- triggered: override ----
    sep = "; " if lang == "en" else "；"
    reasons_text = sep.join(reasons)
    ma = model_assessment
    refund_part = ""
    if ma["refund_amount"] is not None:
        refund_part = L(lang, f", proposed refund {CUR}{ma['refund_amount']}", f"，拟退款 {CUR}{ma['refund_amount']}")
    final["ruling"] = "escalated"
    final["escalation_required"] = True
    # A blocked case gets no automatic payout; the amount is left to a human.
    final["refund_amount"] = None
    final["goodwill_credit"] = None
    final["reasoning"] = L(lang,
        f"[Safety net override] The evidence base is insufficient, so this case is forced to human review and the model's automatic ruling is not adopted. "
        f"Trigger: {reasons_text}. "
        f"The model's own assessment was {ma['ruling']} (confidence {ma['confidence_score']}); its full reasoning is in the model_assessment field.",
        f"【安全网覆盖】证据基础不足，已强制升级人工复核，不采纳模型的自动裁决。"
        f"触发原因：{reasons_text}。"
        f"模型原本的判断是 {ma['ruling']}（置信度 {ma['confidence_score']}），完整理由见 model_assessment 字段。")
    final["escalation_summary"] = L(lang,
        f"Escalated by the safety net: {reasons_text}. "
        f"The model independently ruled {ma['ruling']} (confidence {ma['confidence_score']}{refund_part}), "
        f"but because the evidence base is insufficient it is not executed automatically and goes to human review. "
        f"Model reasoning: {ma['reasoning']}",
        f"安全网覆盖升级：{reasons_text}。"
        f"模型独立裁决为 {ma['ruling']}（置信度 {ma['confidence_score']}{refund_part}），"
        f"但因证据基础不足不予自动执行，转人工复核。"
        f"模型理由：{ma['reasoning']}")
    await emit({"type": "thinking", "role": "safety_net",
                "content": L(lang,
                    f"Override triggered: {reasons_text} -> ruling set to escalated; the model's original ruling {ma['ruling']} (conf {ma['confidence_score']}) is kept in model_assessment.",
                    f"触发覆盖：{reasons_text} → ruling 改为 escalated，模型原始裁决 {ma['ruling']} (conf {ma['confidence_score']}) 保留在 model_assessment。")})
    return final
