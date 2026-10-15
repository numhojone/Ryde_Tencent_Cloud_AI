"""What each pane is shown about a case, built from the recorded case only.

- rider_outcome(): the outcome card for the rider, in plain language: decision, amount, one-line reason,
  policy section. No confidence scores, no agent names, no internal enums in the text.
- human_summary(): the consolidated summary card for the support console.
- needs_human(): whether a ruling has to wait for a person.

Facts are recomputed from the platform records the tools returned (app/agents/cases.compute_facts),
never from fixtures/expected.
"""
from __future__ import annotations

from app.agents import cases as C
from app.agents.base import _truncate
from app.agents.intake import type_label
from app.i18n import CUR, L

TRIP_TOOLS = ("get_trip_data", "get_gps_telemetry", "get_chat_logs", "get_app_events", "get_traffic_reference",
              "get_fare_breakdown", "get_damage_evidence")


def needs_human(ruling: dict | None) -> bool:
    if not isinstance(ruling, dict):
        return True
    return ruling.get("ruling") == "escalated" or bool(ruling.get("escalation_required"))


def facts_for(dtype: str, tools: dict) -> dict:
    if dtype not in C.RULABLE:
        return {}
    try:
        return C.compute_facts(dtype, tools)
    except Exception:  # noqa: BLE001
        return {}


def money(v) -> str:
    return f"{CUR}{float(v):.2f}"


# ---------------------------------------------------------------- rider outcome

def _reason(dtype: str, f: dict, lg: str) -> tuple[str, str]:
    """(one-line plain reason, policy section) for an AI ruling."""
    o = f.get("outcome")
    if dtype == "route_deviation":
        return {
            "within_tolerance": (L(lg, "The extra distance was within the 1 km the policy allows, so the fare stands.",
                                       "多出的距离在政策允许的 1 公里以内，车费维持不变。"), "1.3"),
            "justified_and_informed": (L(lg, "The detour was caused by traffic and your driver told you about it, so the fare stands.",
                                             "绕行是交通状况造成的，且司机已告知您，车费维持不变。"), "1.3"),
            "justified_not_informed": (L(lg, "The detour was caused by traffic, but your driver did not tell you, so the extra distance fare is refunded.",
                                             "绕行是交通状况造成的，但司机没有告知您，因此退还多出里程的车费。"), "1.3"),
            "unjustified": (L(lg, "Your driver took a longer route without a traffic reason, so the extra distance fare is refunded.",
                                  "司机在没有交通原因的情况下走了更远的路线，因此退还多出里程的车费。"), "1.3"),
        }.get(o, (L(lg, "We checked the route against the trip records.", "我们已对照行程记录核查路线。"), "1.3"))
    if dtype == "no_show_charge":
        return {
            "driver_no_show": (L(lg, "Our records show the driver did not reach your pickup point in time, so the fee is refunded.",
                                     "记录显示司机没有按时到达上车点，因此退还该费用。"), "2.4"),
            "cancelled_before_free_wait_ended": (L(lg, "The trip was cancelled before the free 5-minute wait was over, so the fee is refunded.",
                                                       "行程在 5 分钟免费等待结束前被取消，因此退还该费用。"), "2.1"),
            "contact_obligation_not_met": (L(lg, "The driver did not both message and call you before cancelling, so the fee is refunded.",
                                                 "司机取消前没有同时给您发消息和打电话，因此退还该费用。"), "2.3"),
            "fee_valid": (L(lg, "The driver arrived on time, waited the free 5 minutes and tried to message and call you, so the fee stands.",
                                "司机按时到达、等满 5 分钟免费等待时间，并尝试发消息和致电您，因此该费用维持。"), "2.2"),
        }.get(o, (L(lg, "We checked the pickup records.", "我们已核查上车记录。"), "2.1"))
    if dtype == "fare_dispute":
        return {
            "surge_increase_not_notified": (L(lg, "The price went up after your quote and you were not told, so the difference is refunded.",
                                                  "报价后价格上涨而您没有收到通知，因此退还差额。"), "3.3"),
            "surge_increase_notified": (L(lg, "You were told about the higher price before pickup and went ahead, so the fare stands.",
                                              "上车前您已收到涨价通知并继续行程，因此车费维持不变。"), "3.3"),
        }.get(o, (L(lg, "Your fare matches the pricing records, so it stands.", "您的车费与计价记录一致，维持不变。"), "3.1"))
    if dtype == "property_damage":
        if f.get("claim_valid"):
            return (L(lg, "The driver's cleaning claim is backed by photos taken in the app right after your trip, so the fee stands.",
                          "司机的清洁索赔有行程结束后在 App 内拍摄的照片支持，因此该费用维持。"), "4.2")
        return (L(lg, "The cleaning fee was not backed by valid in-app photos, so it is refunded.",
                      "清洁费没有有效的 App 内照片支持，因此予以退还。"), "4.4")
    return (L(lg, "A Ryde support agent reviewed your case.", "Ryde 客服已审核您的案件。"), "")


def _title(kind: str, lg: str) -> str:
    return {"refund": L(lg, "Refund approved", "已批准退款"),
            "partial_refund": L(lg, "Partial refund approved", "已批准部分退款"),
            "no_refund": L(lg, "No refund this time", "本次不予退款")}[kind]


def rider_outcome(ruling: dict, dtype: str, tools: dict, reference: str, lg: str) -> dict:
    """Outcome card for a ruling the AI was allowed to make on its own."""
    f = facts_for(dtype, tools)
    label = ruling.get("ruling")
    amt = ruling.get("refund_amount") or 0.0
    kind = "no_refund" if (label == "rejected" or not amt) else ("partial_refund" if label == "partial" else "refund")
    reason, sec = _reason(dtype, f, lg)
    return {"decision": kind, "title": _title(kind, lg), "refund_amount": round(float(amt), 2) if kind != "no_refund" else None,
            "goodwill_credit": ruling.get("goodwill_credit") or None, "reason": reason,
            "policy_section": L(lg, f"Ryde Dispute Resolution Policy, section {sec}", f"Ryde 争议处理政策第 {sec} 条") if sec else None,
            "reference": reference, "decided_by": "ai"}


def human_outcome(action: str, amount: float | None, note: str | None, recommendation: dict | None,
                  dtype: str, tools: dict, reference: str, lg: str) -> dict:
    """Outcome card after the support agent decided."""
    if action == "approve" and recommendation:
        card = rider_outcome(recommendation, dtype, tools, reference, lg)
    else:
        amt = round(float(amount or 0.0), 2) if action == "adjust" else 0.0
        kind = "refund" if amt > 0 else "no_refund"
        card = {"decision": kind, "title": _title(kind, lg), "refund_amount": amt if amt > 0 else None, "goodwill_credit": None,
                "reason": L(lg, "A Ryde support agent reviewed your case and the trip records.", "Ryde 客服已审核您的案件和行程记录。"),
                "policy_section": None, "reference": reference}
    card["decided_by"] = "human"
    if note:
        card["note"] = note
    return card


def handoff_message(reference: str, lg: str) -> str:
    return L(lg, f"Your case has been passed to a Ryde support agent. They will be in touch with you shortly. Reference: {reference}.",
                 f"您的案件已转交 Ryde 客服专员处理，他们会尽快与您联系。参考编号：{reference}。")


# ---------------------------------------------------------------- human summary

def recommendation_of(ruling: dict | None) -> dict | None:
    """The AI's recommended ruling for an escalated case, or None (safety incidents have none)."""
    if not isinstance(ruling, dict) or ruling.get("case_file"):
        return None
    if ruling.get("recommendation"):
        return dict(ruling["recommendation"])
    ma = ruling.get("model_assessment") or {}
    if ruling.get("ruling") == "escalated" and ma.get("ruling") in ("upheld", "rejected", "partial"):
        return {"ruling": ma["ruling"], "refund_amount": ma.get("refund_amount")}
    if ruling.get("ruling") in ("upheld", "rejected", "partial"):
        return {"ruling": ruling["ruling"], "refund_amount": ruling.get("refund_amount"),
                "goodwill_credit": ruling.get("goodwill_credit")}
    return None


def escalation_reasons(ruling: dict | None, lg: str) -> list[str]:
    if not isinstance(ruling, dict):
        return [L(lg, "The automated review did not finish; a person has to review the case.", "自动审核未完成，需要人工审核。")]
    out: list[str] = []
    pp = ruling.get("policy_path") or {}
    if ruling.get("case_file"):
        out.append(L(lg, "Safety incident: the AI may not rule or recommend (policy 5.1 / 5.2).", "安全事件：AI 不得裁决或提出建议（政策 5.1 / 5.2）。"))
    else:
        out += list(pp.get("reasons") or [])
        if pp.get("fraud_flag") and not any("95" in r for r in out):
            out.append(L(lg, "A party has a fraud flag, so the confidence bar is 95% (6.3).", "当事人有欺诈标记，置信度门槛为 95%（6.3）。"))
    sn = ruling.get("safety_net") or {}
    if sn.get("triggered"):
        out += [L(lg, "Safety net: ", "安全网：") + r for r in sn.get("reasons") or []]
    return out or [L(lg, "Human approval required by policy section 6.", "政策第 6 节要求人工批准。")]


def _profile_line(p: dict | None, lg: str) -> str | None:
    if not p:
        return None
    dh = p.get("dispute_history") or {}
    ff = p.get("fraud_flags") or 0
    return L(lg, f"{p.get('total_trips')} trips, rating {p.get('avg_rating')}, {dh.get('total_disputes', 0)} past disputes"
                 + (f", fraud flag {ff}" if ff else ""),
                 f"{p.get('total_trips')} 单，评分 {p.get('avg_rating')}，历史争议 {dh.get('total_disputes', 0)} 次"
                 + (f"，欺诈标记 {ff}" if ff else ""))


def human_summary(case, lg: str) -> dict:
    """The consolidated, scannable summary for the support console."""
    t = case.ticket or {}
    tools = case.tools or {}
    td = tools.get("get_trip_data") or {}
    dtype = t.get("dispute_type")
    f = facts_for(dtype, tools) if dtype else {}
    ruling = case.ruling if isinstance(case.ruling, dict) else {}
    rec = recommendation_of(ruling)

    key_facts = C.evidence_lines(dtype, f, lg) if f else []
    if dtype == "safety_incident" and ruling.get("case_file"):
        key_facts = list(ruling["case_file"].get("facts") or [])[1:]       # the first fact is the rider's own words

    found, missing = [], []
    sn = (ruling.get("safety_net") or {}).get("checks", {}).get("evidence_sources") or {}
    for label, info in sn.items():
        (missing if info.get("near_empty") else found).append(f"{label}: {info.get('count')}")
    if not sn:
        counts = {"gps_telemetry": len((tools.get("get_gps_telemetry") or {}).get("points") or []),
                  "chat_logs": len((tools.get("get_chat_logs") or {}).get("messages") or []),
                  "app_events": len((tools.get("get_app_events") or {}).get("events") or [])}
        for k, v in counts.items():
            (found if v else missing).append(f"{k}: {v}")
    missing += [L(lg, "Not in story: ", "描述中缺少：") + m for m in (t.get("missing_info") or [])]

    replies = [m for m in case.rider_messages[1:]]
    return {
        "reference": case.reference,
        "case_id": case.id,
        "dispute_id": t.get("dispute_id"),
        "status": case.status,
        "who": {
            "rider": {"id": t.get("rider_id"), "line": _profile_line(tools.get("get_rider_profile"), lg)},
            "driver": {"id": t.get("driver_id"), "line": _profile_line(tools.get("get_driver_profile"), lg)},
        },
        "trip": {"id": t.get("trip_id"),
                 "route": f"{(td.get('pickup_location') or {}).get('name', '?')} → {(td.get('dropoff_location') or {}).get('name', '?')}",
                 "time": td.get("start_time") or td.get("scheduled_time"), "status": td.get("status")},
        "category": {"type": dtype, "label": type_label(dtype, lg) if dtype else None},
        "claim": {"story": case.rider_messages[0]["text"] if case.rider_messages else t.get("description"),
                  "requested_amount": t.get("requested_amount"), "requested_resolution": t.get("requested_resolution")},
        "key_facts": key_facts,
        "evidence_found": found,
        "evidence_missing": missing,
        "advocates": {"rider": (case.rider_case or {}).get("claim"), "driver": (case.driver_case or {}).get("claim")},
        "recommendation": rec,
        "escalation_reasons": escalation_reasons(ruling, lg) if case.ruling is not None or case.status != "in_review" else [],
        "policy_clause": (ruling.get("policy_path") or {}).get("clause"),
        "case_file": ruling.get("case_file"),
        "rider_replies": replies,
        "driver_replies": list(getattr(case, "driver_messages", []) or []),
        "pending": case.pending() if hasattr(case, "pending") else {"rider": 0, "driver": 0},
        # the platform records behind the evidence chips (long lists shortened, as in the agent room)
        "evidence": {k: _truncate(v) for k, v in tools.items()
                     if v and not (k == "get_damage_evidence" and not v.get("damage_evidence"))
                     and not (k == "get_traffic_reference" and not v.get("traffic_conditions"))},
    }
