"""Tool layer: each tool reads JSON fixtures and returns structured data.

(原文) 工具实现层：每个工具从 JSON fixtures 读取并返回结构化数据。

这些函数是 agent 真正调用的"工具"。它们不做判断，只返回原始证据——
所有推理交给 agent。故意保持简单直白，便于 demo 时审视调用链。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import FIXTURES_DIR


class ToolError(Exception):
    """工具执行错误，会被 agent 捕获并回传给模型。"""


def _load_json(rel_path: str) -> Any:
    p = FIXTURES_DIR / rel_path
    if not p.exists():
        raise ToolError(f"Data not found: {rel_path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_dispute(dispute_id: str) -> dict:
    return _load_json(f"disputes/{dispute_id}.json")


def _load_trip(trip_id: str) -> dict:
    """整条 trip 文件包含 trip_data/gps_telemetry/chat_logs/app_events/traffic_reference。"""
    return _load_json(f"trips/{trip_id}.json")


# ---------- 8 个对外工具 ----------

def get_trip_data(trip_id: str) -> dict:
    """获取行程基本信息：上下车点、时间、费用、里程/时长（最优 vs 实际）。"""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, **trip.get("trip_data", {})}


def get_gps_telemetry(trip_id: str) -> dict:
    """获取 GPS 轨迹：时间戳、经纬度、速度、状态数组。"""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, "points": trip.get("gps_telemetry", [])}


def get_chat_logs(trip_id: str) -> dict:
    """获取行程内聊天/通话/系统消息记录。"""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, "messages": trip.get("chat_logs", [])}


def get_app_events(trip_id: str) -> dict:
    """获取 App 端系统事件：到达、等待计时、联系尝试、扣费等。"""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, "events": trip.get("app_events", [])}


def get_rider_profile(rider_id: str) -> dict:
    """获取乘客画像：账龄、总单量、评分、争议历史、欺诈标记。"""
    return {"rider_id": rider_id, **_load_json(f"profiles/riders/{rider_id}.json")}


def get_driver_profile(driver_id: str) -> dict:
    """获取司机画像（同乘客画像字段，另含车辆信息）。"""
    return {"driver_id": driver_id, **_load_json(f"profiles/drivers/{driver_id}.json")}


def get_policy(dispute_type: str) -> dict:
    """Return the Ryde policy v2.1 sections that apply to a dispute type, plus the section 6 ruling thresholds."""
    pol = _load_json("policies/policy_v2_1.json")
    secs = pol["sections"].get(dispute_type)
    if secs is None:
        raise ToolError(f"No policy for dispute type: {dispute_type}")
    th = pol["ruling_thresholds"]
    return {
        "dispute_type": dispute_type,
        "policy_version": pol["version"],
        "sections": secs,
        "category_threshold": th["category"].get(dispute_type),
        "monetary_thresholds": th["monetary"],
        "fraud_flag_min_confidence": th["fraud_flag_min_confidence"],
        "confidence_note": th["text_6_3"],
    }


def get_traffic_reference(trip_id: str) -> dict:
    """Third-party traffic reference for route-deviation disputes: incidents on the road segments around the trip,
    plus the system-recommended route. May be empty."""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, "traffic_conditions": trip.get("traffic_conditions", []),
            "recommended_route": trip.get("optimal_route")}


def get_fare_breakdown(trip_id: str) -> dict:
    """Fare breakdown (quote vs actual, per-component) and the surge pricing log, for fare / route disputes."""
    trip = _load_trip(trip_id)
    td = trip.get("trip_data", {}) or {}
    return {"trip_id": trip_id,
            "fares": {k: td[k] for k in ("upfront_quote", "actual_fare", "fare_difference", "estimated_fare",
                                         "fare_charged", "cleaning_fee_charged", "cancellation_fee_charged") if k in td},
            "fare_breakdown": trip.get("fare_breakdown"), "surge_pricing_log": trip.get("surge_pricing_log")}


def get_damage_evidence(trip_id: str) -> dict:
    """Property-damage claim evidence: claim type/amount, photos (when, how captured, linked to trip), repair quote."""
    trip = _load_trip(trip_id)
    return {"trip_id": trip_id, "damage_evidence": trip.get("damage_evidence"),
            "trip_end_time": (trip.get("trip_data") or {}).get("end_time")}


_PREC_ALIAS = {"cancellation_fee": "no_show_charge"}


def search_precedents(dispute_type: str, tags: list | None = None) -> dict:
    """Search past rulings by dispute type; optional fact tags rank the results by overlap."""
    want = set(tags or [])
    out = []
    for p in _load_json("precedents.json"):
        if _PREC_ALIAS.get(p["dispute_type"], p["dispute_type"]) != dispute_type:
            continue
        out.append({**p, "tag_overlap": len(want & set(p.get("tags", [])))})
    out.sort(key=lambda x: -x["tag_overlap"])
    return {"dispute_type": dispute_type, "precedents": out}


# ---------- 争议票据加载（编排器用，非 agent 工具）----------

def load_dispute_ticket(dispute_id: str) -> dict:
    """加载争议工单。这是整个流程的入口数据。"""
    return _load_dispute(dispute_id)


def list_trips() -> list[dict]:
    """列出所有有证据数据的行程（供自由文本提交时选择 trip_id）。"""
    parties = _load_json("trip_parties.json")
    out = []
    for p in sorted((FIXTURES_DIR / "trips").glob("*.json")):
        trip_id = p.stem
        trip = _load_trip(trip_id)
        td = trip.get("trip_data", {}) or {}
        meta = parties.get(trip_id, {}) or {}
        out.append({
            "trip_id": trip_id,
            "route": meta.get("route") or f"{td.get('pickup', '?')} → {td.get('dropoff', '?')}",
            "outcome": meta.get("outcome") or td.get("status", ""),
            "scheduled_time": td.get("scheduled_time"),
            "status": td.get("status"),
            "rider_id": meta.get("rider_id"),
            "driver_id": meta.get("driver_id"),
        })
    return out


def list_place_names() -> list[str]:
    """Every pickup / drop-off place name in the trip fixtures (the gazetteer for story extraction)."""
    names: list[str] = []
    for p in sorted((FIXTURES_DIR / "trips").glob("*.json")):
        td = _load_trip(p.stem).get("trip_data", {}) or {}
        for k in ("pickup_location", "dropoff_location"):
            n = (td.get(k) or {}).get("name")
            if n and n not in names:
                names.append(n)
    return names


def load_rider_trips() -> list[dict]:
    """The rider's recent trips as the platform recorded them, for matching a story to a trip.

    Each item is the trip_data record plus the app events and the GPS peak speed. Platform records only:
    nothing from fixtures/expected.
    """
    out = []
    for p in sorted((FIXTURES_DIR / "trips").glob("*.json")):
        trip = _load_trip(p.stem)
        td = dict(trip.get("trip_data", {}) or {})
        td["trip_id"] = p.stem
        td["app_events"] = trip.get("app_events", [])
        td["gps_max_speed_kmh"] = max([pt.get("speed_kmh", 0) or 0 for pt in trip.get("gps_telemetry", [])], default=None)
        out.append(td)
    return out


def get_trip_parties(trip_id: str) -> dict:
    """按 trip_id 取当事双方 ID。自由文本投诉里乘客不会提供自己的 ID，由系统按行程补齐。"""
    parties = _load_json("trip_parties.json")
    meta = parties.get(trip_id)
    if not meta:
        raise ToolError(f"Unknown trip, no party record: {trip_id}")
    return {"trip_id": trip_id, "rider_id": meta["rider_id"], "driver_id": meta["driver_id"]}


def list_disputes() -> list[dict]:
    """列出所有可用样例争议（供前端下拉）。"""
    out = []
    for p in sorted((FIXTURES_DIR / "disputes").glob("*.json")):
        d = _load_json(f"disputes/{p.name}")
        out.append({
            "dispute_id": d["dispute_id"],
            "trip_id": d["trip_id"],
            "dispute_type": d["dispute_type"],
            "filed_by": d["filed_by"],
            "description": d["description"],
        })
    return out
