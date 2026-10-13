"""Deterministic analysis helpers: extract key facts from raw tool output.

(原文) 确定性分析辅助：从工具返回的原始数据中提取关键事实。

这些纯函数被 advocate 与 judge 共用——judge 自行调用工具拿到数据后，
用同一套数学来"独立核验"advocate 的主张（而不是另搞一套口径）。
LLM 模式下模型自行推理，但这些函数仍用于 deterministic 回退。
"""
from __future__ import annotations

import math
from typing import Any

from app.i18n import L


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间距离（米）。"""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_ts(s: str) -> float:
    """把 ISO 时间转 epoch 秒（用 fromisoformat 处理 +08:00）。"""
    from datetime import datetime
    try:
        return datetime.fromisoformat(s).timestamp()
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------- 路线偏差 ----------------

def route_deviation_facts(trip_data: dict, policy: dict, traffic: dict | None, lang: str = "en") -> dict:
    dist = trip_data.get("distance", {})
    actual_km = float(dist.get("actual_km", 0))
    optimal_km = float(dist.get("optimal_km", 0))
    fare = trip_data.get("fare_breakdown", {})
    base_fare = float(fare.get("base_fare", 0))
    per_km = float(policy.get("per_km_rate", fare.get("per_km_rate", 0)))
    fare_charged = float(trip_data.get("fare_charged", 0))
    tolerance = float(policy.get("max_tolerated_deviation_pct", 15.0))

    deviation_pct = (actual_km - optimal_km) / optimal_km * 100 if optimal_km else 0.0
    tolerated_km = optimal_km * (1 + tolerance / 100)
    overcharged_km = max(0.0, actual_km - tolerated_km)
    optimal_fare = base_fare + optimal_km * per_km

    # 交通是否让绕行合理：实际路线（含拥堵）时长 <= 最优路线（含拥堵）时长
    traffic_justified = False
    traffic_note = L(lang, "No third-party traffic data", "无第三方交通数据")
    if traffic:
        opt = traffic.get("optimal_route", {})
        act = traffic.get("actual_route_taken", {})
        opt_t = opt.get("est_duration_min_with_traffic")
        act_t = act.get("est_duration_min_with_traffic")
        if opt_t is not None and act_t is not None:
            traffic_justified = act_t <= opt_t
            traffic_note = L(lang,
                f"Optimal route with traffic {opt_t} min vs route taken with traffic {act_t} min; "
                + ("the detour saved time, so it is treated as justified" if traffic_justified
                   else "the detour did not save time, so it is not justified"),
                f"最优路线含拥堵 {opt_t}min vs 实际路线含拥堵 {act_t}min，"
                f"绕行{'节省时间视为合理' if traffic_justified else '未节省时间，不合理'}")

    # 退费：合理则 0，否则 overcharged_km * per_km
    refund = 0.0 if traffic_justified else round(overcharged_km * per_km, 2)

    return {
        "actual_km": actual_km,
        "optimal_km": optimal_km,
        "deviation_pct": round(deviation_pct, 1),
        "tolerance_pct": tolerance,
        "tolerated_km": round(tolerated_km, 2),
        "overcharged_km": round(overcharged_km, 2),
        "fare_charged": fare_charged,
        "optimal_fare": round(optimal_fare, 2),
        "per_km_rate": per_km,
        "base_fare": base_fare,
        "traffic_justified": traffic_justified,
        "traffic_note": traffic_note,
        "policy_refund": refund,
    }


# ---------------- 爽约取消费 ----------------

def no_show_facts(trip_data: dict, gps: dict, events: dict, chats: dict, policy: dict) -> dict:
    pickup = trip_data.get("pickup", {})
    plat, plng = float(pickup.get("lat", 0)), float(pickup.get("lng", 0))
    proximity_m = float(policy.get("gps_arrival_proximity_m", 100))
    free_wait = float(policy.get("free_wait_time_min", 5))
    min_contacts = int(policy.get("min_contact_attempts", 1))
    # The fee actually charged on the trip wins; the policy value is only a fallback.
    fee = float(trip_data.get("cancellation_fee_charged") or policy.get("no_show_fee", 0))

    points = gps.get("points", [])
    # 在上车点附近且停车的点
    near = [p for p in points if haversine_m(plat, plng, p.get("lat", 0), p.get("lng", 0)) <= proximity_m]
    arrived = any(p.get("speed_kmh", 99) == 0 for p in near)
    # 停留时长：从首个 near 速度0 点 到 离开
    dwell_min = 0.0
    if near:
        stopped = [p for p in near if p.get("speed_kmh", 99) == 0]
        if len(stopped) >= 2:
            dwell_min = (_parse_ts(stopped[-1]["timestamp"]) - _parse_ts(stopped[0]["timestamp"])) / 60.0

    # 联系尝试：app_events 的 contact_attempt + chat 的 call
    ev_list = events.get("events", [])
    contact_events = [e for e in ev_list if e.get("event_type") == "contact_attempt"]
    chat_calls = [m for m in chats.get("messages", []) if m.get("type") == "call"]
    contact_attempts = len(contact_events) + len(chat_calls)

    conditions = {
        "driver_arrived_proximity": arrived,
        "dwell_past_free_window": dwell_min >= free_wait,
        "contact_attempted": contact_attempts >= min_contacts,
    }
    all_met = all(conditions.values())
    # 任一不满足 -> 全额退费；全满足 -> 取消费有效（退 0）
    refund = 0.0 if all_met else fee

    return {
        "pickup_proximity_m": proximity_m,
        "near_points": len(near),
        "driver_arrived": arrived,
        "dwell_min": round(dwell_min, 1),
        "free_wait_min": free_wait,
        "contact_attempts": contact_attempts,
        "min_contact_attempts": min_contacts,
        "conditions_met": conditions,
        "all_conditions_met": all_met,
        "no_show_fee": fee,
        "policy_refund": refund,
    }
