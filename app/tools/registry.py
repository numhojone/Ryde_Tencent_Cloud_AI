"""Tool registry: OpenAI-compatible function schemas + dispatch.

The `tools` parameter of an OpenAI-compatible API expects this schema:
{
  "type": "function",
  "function": {"name": ..., "description": ..., "parameters": {...JSON Schema...}}
}
"""
from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from app.tools import fixtures as F


# JSON Schema as dicts, fed straight into the OpenAI SDK `tools` parameter
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_trip_data",
            "description": "Get basic trip info: pickup/dropoff, scheduled/actual times, fare, distance and duration (optimal vs actual). Always check for route-deviation disputes.",
            "parameters": {
                "type": "object",
                "properties": {"trip_id": {"type": "string", "description": "Trip ID, e.g. TRIP-1001"}},
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gps_telemetry",
            "description": "Get the trip GPS points (timestamp, lat/lng, speed, status). Use it to judge arrival, dwell time and the route driven.",
            "parameters": {
                "type": "object",
                "properties": {"trip_id": {"type": "string"}},
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chat_logs",
            "description": "Get the in-trip communication log (rider/driver/system messages and calls). Use it to verify contact attempts and each side's statements.",
            "parameters": {
                "type": "object",
                "properties": {"trip_id": {"type": "string"}},
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_app_events",
            "description": "Get app-side system events: driver arrival, wait timer, contact attempts, free-wait expiry, fee charged, etc.",
            "parameters": {
                "type": "object",
                "properties": {"trip_id": {"type": "string"}},
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rider_profile",
            "description": "Get the rider profile: account age, total trips, rating, dispute history (total/upheld/rejected), fraud flags.",
            "parameters": {
                "type": "object",
                "properties": {"rider_id": {"type": "string"}},
                "required": ["rider_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_driver_profile",
            "description": "Get the driver profile (same fields as the rider profile, plus vehicle info).",
            "parameters": {
                "type": "object",
                "properties": {"driver_id": {"type": "string"}},
                "required": ["driver_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy",
            "description": "Return the Ryde Dispute Resolution Policy v2.1 sections that apply to a dispute type (with section numbers such as 1.2, 2.3, 3.3) and the section 6 ruling thresholds. Rulings must cite the relevant sections.",
            "parameters": {
                "type": "object",
                "properties": {"dispute_type": {"type": "string", "description": "One of route_deviation, no_show_charge, fare_dispute, property_damage, safety_incident"}},
                "required": ["dispute_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_traffic_reference",
            "description": "Get historical traffic-API incidents around the trip (road, severity, start and clear time) and the system-recommended route. Used in route-deviation disputes to judge whether a reroute was traffic-justified.",
            "parameters": {
                "type": "object",
                "properties": {"trip_id": {"type": "string"}},
                "required": ["trip_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fare_breakdown",
            "description": "Get the fare quote vs actual fare, per-component breakdown (surge multiplier, surge amount, booking fee) and the surge pricing log including whether the rider was notified. Used for fare disputes and for distance-fare rates in route disputes.",
            "parameters": {"type": "object", "properties": {"trip_id": {"type": "string"}}, "required": ["trip_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_damage_evidence",
            "description": "Get a property-damage claim: claim type and amount, photos (capture time, whether taken by the in-app camera, linked to the trip) and any repair quote. Used for property-damage disputes.",
            "parameters": {"type": "object", "properties": {"trip_id": {"type": "string"}}, "required": ["trip_id"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_precedents",
            "description": "Search past rulings by dispute type. Optional fact tags (e.g. rider_not_informed, traffic_justified, surge_increase) rank results by overlap. Cite a relevant precedent case ID in the ruling rationale.",
            "parameters": {"type": "object", "properties": {"dispute_type": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["dispute_type"]},
        },
    },
]


# name -> callable
DISPATCH: dict[str, Callable[..., Any]] = {
    "get_trip_data": F.get_trip_data,
    "get_gps_telemetry": F.get_gps_telemetry,
    "get_chat_logs": F.get_chat_logs,
    "get_app_events": F.get_app_events,
    "get_rider_profile": F.get_rider_profile,
    "get_driver_profile": F.get_driver_profile,
    "get_policy": F.get_policy,
    "get_traffic_reference": F.get_traffic_reference,
    "get_fare_breakdown": F.get_fare_breakdown,
    "get_damage_evidence": F.get_damage_evidence,
    "search_precedents": F.search_precedents,
}


def call_tool(name: str, arguments: dict | str) -> dict:
    """Run a tool call. `arguments` may be a dict or a JSON string. Returns {ok, result|error}."""
    try:
        if isinstance(arguments, str):
            arguments = json.loads(arguments) if arguments else {}
        fn = DISPATCH.get(name)
        if fn is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        result = fn(**arguments)
        return {"ok": True, "result": result}
    except F.ToolError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}


def summarize_for_log(name: str, arguments: dict) -> str:
    """One-line readable summary of a tool call (for the event stream)."""
    if not arguments:
        return f"{name}()"
    parts = [f"{k}={v}" for k, v in arguments.items()]
    return f"{name}({', '.join(parts)})"
