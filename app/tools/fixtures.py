"""Tool layer: each tool reads JSON fixtures and returns structured data.

(原文) 工具实现层：每个工具从 JSON fixtures 读取并返回结构化数据。

这些函数是 agent 真正调用的"工具"。它们不做判断，只返回原始证据——
所有推理交给 agent。故意保持简单直白，便于 demo 时审视调用链。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from app.config import FIXTURES_DIR


class ToolError(Exception):
    """工具执行错误，会被 agent 捕获并回传给模型。"""


# Directories a tool may read. fixtures/expected (ground truth) is never one of them.
_READABLE = ("disputes", "trips", "profiles", "policies")
_READABLE_FILES = ("precedents.json", "trip_parties.json", "trips_synthetic.json", "demo_accounts.json")

# ---------- rider scoping ----------
# The rider whose data the current request / case may read. None = unrestricted (support agent, internal code).
# Every lookup that returns trip data checks it, and another rider's trip looks exactly like a missing one,
# so its existence is not leaked.
_SCOPE: ContextVar[str | None] = ContextVar("rr_rider_scope", default=None)


def current_scope() -> str | None:
    return _SCOPE.get()


@contextmanager
def rider_scope(rider_id: str | None):
    token = _SCOPE.set(rider_id)
    try:
        yield
    finally:
        _SCOPE.reset(token)


def set_scope(rider_id: str | None) -> None:
    """For a context created with contextvars.copy_context() (a new task): bind it to a rider."""
    _SCOPE.set(rider_id)


def _load_json(rel_path: str) -> Any:
    p = (FIXTURES_DIR / rel_path).resolve()
    rel = p.relative_to(FIXTURES_DIR.resolve()) if p.is_relative_to(FIXTURES_DIR.resolve()) else None
    if rel is None or not (rel.parts[0] in _READABLE or str(rel) in _READABLE_FILES):
        # An id such as "../expected/DISP-001" must not reach the ground truth
        raise ToolError(f"Data not found: {rel_path}")
    if not p.exists():
        raise ToolError(f"Data not found: {rel_path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_dispute(dispute_id: str) -> dict:
    d = _load_json(f"disputes/{dispute_id}.json")
    scope = current_scope()
    if scope and d.get("rider_id") != scope:
        raise ToolError(f"Data not found: disputes/{dispute_id}.json")
    return d


def _synthetic_trips() -> dict[str, dict]:
    """Extra demo trips (fixtures/trips_synthetic.json, all synthetic), keyed by trip_id."""
    p = FIXTURES_DIR / "trips_synthetic.json"
    if not p.exists():
        return {}
    return {t["trip_id"]: t for t in _load_json("trips_synthetic.json").get("trips", [])}


def all_trip_ids() -> list[str]:
    ids = [p.stem for p in sorted((FIXTURES_DIR / "trips").glob("*.json"))]
    return ids + [t for t in _synthetic_trips() if t not in ids]


def _raw_trip(trip_id: str) -> dict:
    syn = _synthetic_trips()
    if "/" not in trip_id and "\\" not in trip_id and trip_id in syn and not (FIXTURES_DIR / "trips" / f"{trip_id}.json").exists():
        return syn[trip_id]
    return _load_json(f"trips/{trip_id}.json")


def trip_owner(trip: dict, trip_id: str | None = None) -> str | None:
    td = trip.get("trip_data") or {}
    if td.get("rider_id"):
        return td["rider_id"]
    try:
        return (_load_json("trip_parties.json").get(trip_id or trip.get("trip_id")) or {}).get("rider_id")
    except ToolError:
        return None


def _load_trip(trip_id: str) -> dict:
    """整条 trip 文件包含 trip_data/gps_telemetry/chat_logs/app_events/traffic_reference。

    Rider-scoped: another rider's trip raises the same "not found" as a missing trip.
    """
    trip = _raw_trip(trip_id)
    scope = current_scope()
    if scope and trip_owner(trip, trip_id) != scope:
        raise ToolError(f"Data not found: trips/{trip_id}.json")
    return trip


def _scoped_driver_ids(rider_id: str) -> set[str]:
    out = set()
    for tid in all_trip_ids():
        t = _raw_trip(tid)
        if trip_owner(t, tid) == rider_id:
            out.add((t.get("trip_data") or {}).get("driver_id") or get_trip_parties(tid, _check=False).get("driver_id"))
    return out


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
    scope = current_scope()
    if scope and rider_id != scope:
        raise ToolError(f"Data not found: profiles/riders/{rider_id}.json")
    return {"rider_id": rider_id, **_load_json(f"profiles/riders/{rider_id}.json")}


def get_driver_profile(driver_id: str) -> dict:
    """获取司机画像（同乘客画像字段，另含车辆信息）。Rider-scoped: only drivers of the rider's own trips."""
    scope = current_scope()
    if scope and driver_id not in _scoped_driver_ids(scope):
        raise ToolError(f"Data not found: profiles/drivers/{driver_id}.json")
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


def _route(td: dict) -> str:
    return f"{(td.get('pickup_location') or {}).get('name', '?')} → {(td.get('dropoff_location') or {}).get('name', '?')}"


def list_trips() -> list[dict]:
    """Trips a complaint can be filed against (scoped to the current rider when there is one)."""
    parties = _load_json("trip_parties.json")
    out = []
    for trip_id in all_trip_ids():
        try:
            trip = _load_trip(trip_id)
        except ToolError:
            continue
        td = trip.get("trip_data", {}) or {}
        meta = parties.get(trip_id, {}) or {}
        out.append({
            "trip_id": trip_id,
            "route": meta.get("route") or _route(td),
            "outcome": meta.get("outcome") or td.get("status", ""),
            "scheduled_time": td.get("scheduled_time") or td.get("start_time"),
            "status": td.get("status"),
            "rider_id": meta.get("rider_id") or td.get("rider_id"),
            "driver_id": meta.get("driver_id") or td.get("driver_id"),
            "synthetic": str(trip.get("_source", "")).lower().startswith("synthetic"),
        })
    return out


def list_place_names() -> list[str]:
    """Every pickup / drop-off place name in the trip data (the gazetteer for story extraction).

    Place names are public places, so this list is not rider-scoped.
    """
    names: list[str] = []
    for tid in all_trip_ids():
        td = _raw_trip(tid).get("trip_data", {}) or {}
        for k in ("pickup_location", "dropoff_location"):
            n = (td.get(k) or {}).get("name")
            if n and n not in names:
                names.append(n)
    return names


def _driver_name(trip: dict) -> str | None:
    td = trip.get("trip_data") or {}
    if td.get("driver_name"):
        return td["driver_name"]
    return next((m.get("sender_name") for m in trip.get("chat_logs", []) if m.get("sender") == "driver" and m.get("sender_name")), None)


def load_rider_trips(rider_id: str | None = None) -> list[dict]:
    """The rider's recent trips as the platform recorded them, for matching a story to a trip.

    Only the current scope's (or the given rider's) trips. Each item is the trip_data record plus the app
    events, the GPS peak speed and the driver's name. Platform records only: nothing from fixtures/expected.
    """
    rid = rider_id or current_scope()
    out = []
    for tid in all_trip_ids():
        try:
            trip = _load_trip(tid)
        except ToolError:
            continue
        if rid and trip_owner(trip, tid) != rid:
            continue
        td = dict(trip.get("trip_data", {}) or {})
        td["trip_id"] = tid
        td["app_events"] = trip.get("app_events", [])
        td["gps_max_speed_kmh"] = max([pt.get("speed_kmh", 0) or 0 for pt in trip.get("gps_telemetry", [])], default=None)
        td["driver_name"] = _driver_name(trip)
        td["rider_id"] = td.get("rider_id") or trip_owner(trip, tid)
        td["has_damage_claim"] = bool(trip.get("damage_evidence"))
        out.append(td)
    return out


def get_trip_parties(trip_id: str, _check: bool = True) -> dict:
    """按 trip_id 取当事双方 ID。自由文本投诉里乘客不会提供自己的 ID，由系统按行程补齐。"""
    trip = _load_trip(trip_id) if _check else _raw_trip(trip_id)
    meta = _load_json("trip_parties.json").get(trip_id) or {}
    td = trip.get("trip_data") or {}
    rider, driver = meta.get("rider_id") or td.get("rider_id"), meta.get("driver_id") or td.get("driver_id")
    if not rider or not driver:
        raise ToolError(f"Unknown trip, no party record: {trip_id}")
    return {"trip_id": trip_id, "rider_id": rider, "driver_id": driver}


def list_disputes() -> list[dict]:
    """Preset tickets for the dropdown (scoped to the current rider when there is one)."""
    out = []
    scope = current_scope()
    for p in sorted((FIXTURES_DIR / "disputes").glob("*.json")):
        d = _load_json(f"disputes/{p.name}")
        if scope and d.get("rider_id") != scope:
            continue
        out.append({
            "dispute_id": d["dispute_id"],
            "trip_id": d["trip_id"],
            "dispute_type": d["dispute_type"],
            "filed_by": d["filed_by"],
            "description": d["description"],
        })
    return out


def list_rider_ids() -> list[str]:
    return [p.stem for p in sorted((FIXTURES_DIR / "profiles" / "riders").glob("*.json"))]


def demo_accounts() -> dict:
    """Display names and demo stories for the login screen (fixtures/demo_accounts.json, synthetic)."""
    try:
        return _load_json("demo_accounts.json")
    except ToolError:
        return {"riders": {}}
