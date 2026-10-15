"""Deterministic analysis of tool output under Ryde Dispute Resolution Policy v2.1.

Pure functions: given the data the tools returned, compute the facts a ruling depends on (distances, wait times,
notification status, surge differential, photo verifiability) and the policy outcome. The deterministic backend
uses them directly; the real-LLM backend reasons on its own and the judge's numbers can be compared against these.
No function here reads the expected answers (fixtures/expected is for tests only).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

# ---- policy constants (v2.1) ----
TOLERANCE_KM = 1.0              # 1.3: deviation <= 1 km is within tolerance
FREE_WAIT_MIN = 5.0             # 2.1
NO_SHOW_FEE = 5.0               # 2.2
GOODWILL_CREDIT = 5.0           # 2.4
PICKUP_PROXIMITY_M = 100.0      # operational definition of "at the pickup location" (policy gives none)
PHOTO_WINDOW_H = 24.0           # 4.2
CLEANING_CAP = 50.0             # 4.3
ROUTE_KEYWORDS = ("traffic", "jam", "congest", "reroute", "re-route", "alternate", "alternative", "detour", "diversion",
                  "accident", "fire", "closure", "closed", "another route", "different route", "other route", "take pie",
                  "take ecp", "avoid", "blocked", "erp")


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def parse_ts(s: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(s)).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _loc(td: dict, key: str) -> dict:
    return td.get(f"{key}_location") or td.get(key) or {}


# ---------------------------------------------------------------- route deviation
def route_deviation_facts(trip: dict, fare_info: dict, traffic: dict, chats: dict, gps: dict | None = None) -> dict:
    est_km = float(trip.get("estimated_distance_km") or 0)
    act_km = float(trip.get("actual_distance_km") or 0)
    dev_km = round(act_km - est_km, 2)                                   # 1.4
    fb = (fare_info or {}).get("fare_breakdown") or {}
    rate = float(fb.get("distance_rate_per_km") or 0)
    excess_fare = round(dev_km * rate, 2) if dev_km > 0 else 0.0
    est_fare = float(trip.get("estimated_fare") or 0)
    act_fare = float(trip.get("actual_fare") or 0)

    rec = (traffic or {}).get("recommended_route") or {}
    route_name = str(rec.get("route_name", ""))
    start = parse_ts(trip.get("start_time"))
    matched = []
    for inc in (traffic or {}).get("traffic_conditions", []) or []:
        road_tok = str(inc.get("road", "")).split(" ")[0].upper()
        if not road_tok or road_tok not in route_name.upper():
            continue
        if inc.get("severity") not in ("moderate", "high"):
            continue
        t0, t1 = parse_ts(inc.get("timestamp")), parse_ts(inc.get("clear_time")) if inc.get("clear_time") else None
        if start is not None and t0 is not None and t0 <= start + 600 and (t1 is None or t1 >= start):
            matched.append(inc.get("incident_id"))
    justified = bool(matched)                                            # 1.4

    # when did the trip leave the recommended route?
    dev_ts = start
    wps = rec.get("waypoints") or []
    if wps and gps:
        for p in gps.get("points", []):
            if min(haversine_m(p["lat"], p["lng"], w["lat"], w["lng"]) for w in wps) > 1000:
                dev_ts = parse_ts(p["timestamp"]); break
    notice = None
    for m in (chats or {}).get("messages", []):
        if m.get("sender") != "driver":
            continue
        txt = str(m.get("message") or m.get("content") or "").lower()
        ts = parse_ts(m.get("timestamp"))
        if any(k in txt for k in ROUTE_KEYWORDS) and (dev_ts is None or ts is None or ts <= dev_ts + 60):
            notice = m.get("message_id") or m.get("timestamp"); break
    informed = notice is not None                                        # 1.2
    rider_asked = any(m.get("sender") == "rider" and any(w in str(m.get("message", "")).lower() for w in ("route", "right way", "why are we", "this way"))
                      for m in (chats or {}).get("messages", []))

    if dev_km <= TOLERANCE_KM:
        refund, label, outcome = 0.0, "rejected", "within_tolerance"
    elif justified and informed:
        refund, label, outcome = 0.0, "rejected", "justified_and_informed"
    elif justified:
        refund, label, outcome = excess_fare, "partial", "justified_not_informed"
    else:
        refund, label, outcome = excess_fare, "upheld", "unjustified"
    return {"estimated_km": est_km, "actual_km": act_km, "deviation_km": dev_km, "over_tolerance": dev_km > TOLERANCE_KM,
            "distance_rate": rate, "excess_distance_fare": excess_fare, "estimated_fare": est_fare, "actual_fare": act_fare,
            "fare_delta": round(act_fare - est_fare, 2), "traffic_justified": justified, "matched_incidents": matched,
            "rider_informed": informed, "rider_queried_route": rider_asked, "outcome": outcome,
            "policy_refund": refund, "ruling_label": label, "clause": "1.3"}


# ---------------------------------------------------------------- no-show
def no_show_facts(trip: dict, gps: dict, events: dict, chats: dict) -> dict:
    pk = _loc(trip, "pickup")
    plat, plng = float(pk.get("lat", 0)), float(pk.get("lng", 0))
    fee = float(trip.get("cancellation_fee") or trip.get("cancellation_fee_charged") or NO_SHOW_FEE)
    sched = parse_ts(trip.get("scheduled_time"))
    cancel = parse_ts(trip.get("cancellation_time"))
    if cancel is None:
        for e in (events or {}).get("events", []):
            if "cancel" in str(e.get("event_type")):
                cancel = parse_ts(e.get("timestamp"))
    pts = (gps or {}).get("points", []) or []
    near = [p for p in pts if haversine_m(plat, plng, p.get("lat", 0), p.get("lng", 0)) <= PICKUP_PROXIMITY_M]
    stopped = [p for p in near if p.get("speed_kmh", 99) == 0]
    arrived_ts = parse_ts(stopped[0]["timestamp"]) if stopped else None
    left_ts = parse_ts(stopped[-1]["timestamp"]) if stopped else None
    arrived_in_time = arrived_ts is not None and sched is not None and arrived_ts <= sched + FREE_WAIT_MIN * 60   # 2.4
    waited_free = bool(cancel and sched and cancel >= sched + FREE_WAIT_MIN * 60 and left_ts and left_ts >= sched + FREE_WAIT_MIN * 60 - 60)  # 2.1
    msgs = [m for m in (chats or {}).get("messages", []) if m.get("sender") == "driver" and m.get("type", "message") == "message"]
    chat_calls = [m for m in (chats or {}).get("messages", []) if m.get("sender") == "driver" and m.get("type") == "call"]
    ev_calls = [e for e in (events or {}).get("events", []) if e.get("event_type") in ("driver_called_rider", "contact_attempt_call")]
    n_calls = max(len(chat_calls), len(ev_calls))
    n_msgs = len(msgs)
    contact_ok = n_msgs >= 1 and n_calls >= 1                                                               # 2.3
    ev_arrived = any(e.get("event_type") == "driver_arrived" for e in (events or {}).get("events", []))
    contradiction = ev_arrived and not near
    if not arrived_in_time:
        outcome, refund = "driver_no_show", fee                                                              # 2.4
        goodwill = GOODWILL_CREDIT if (n_msgs == 0 and n_calls == 0) else 0.0
    elif not waited_free:
        outcome, refund, goodwill = "cancelled_before_free_wait_ended", fee, 0.0                             # 2.1
    elif not contact_ok:
        outcome, refund, goodwill = "contact_obligation_not_met", fee, 0.0                                   # 2.3
    else:
        outcome, refund, goodwill = "fee_valid", 0.0, 0.0
    return {"no_show_fee": fee, "pickup_proximity_m": PICKUP_PROXIMITY_M, "near_points": len(near), "stopped_points": len(stopped),
            "arrived_in_time": arrived_in_time, "waited_free_period": waited_free, "driver_messages": n_msgs, "driver_calls": n_calls,
            "contact_ok": contact_ok, "gps_app_contradiction": contradiction, "outcome": outcome, "policy_refund": refund,
            "goodwill_credit": goodwill, "ruling_label": "rejected" if refund == 0 else "upheld",
            "conditions_met": {"driver_arrived_in_time": arrived_in_time, "waited_free_period": waited_free,
                               "message_sent": n_msgs >= 1, "call_made": n_calls >= 1},
            "clause": {"driver_no_show": "2.4", "cancelled_before_free_wait_ended": "2.1",
                       "contact_obligation_not_met": "2.3", "fee_valid": "2.2"}[outcome],
            "dwell_min": round(((left_ts - arrived_ts) / 60.0), 1) if (arrived_ts and left_ts) else 0.0}


# ---------------------------------------------------------------- fare / surge
def fare_facts(trip: dict, fare_info: dict) -> dict:
    quote = float(trip.get("upfront_quote") or 0)
    actual = float(trip.get("actual_fare") or 0)
    diff = round(actual - quote, 2)
    log = (fare_info or {}).get("surge_pricing_log") or {}
    fb = (fare_info or {}).get("fare_breakdown") or {}
    q, a = fb.get("upfront_quote") or {}, fb.get("actual_fare") or {}
    m0, m1 = float(log.get("quote_time_surge", q.get("surge_multiplier", 1.0))), float(log.get("trip_start_surge", a.get("surge_multiplier", 1.0)))
    surge_diff = round(float(a.get("surge_amount", 0)) - float(q.get("surge_amount", 0)), 2)
    sub_same = abs(float(a.get("surgeable_subtotal", 0)) - float(q.get("surgeable_subtotal", 0))) < 0.005
    surge_only = diff > 0 and abs(diff - surge_diff) < 0.015 and sub_same                                    # 3.4
    increased = m1 > m0
    notified = bool(log.get("rider_notified"))
    if increased and not notified:
        refund = diff if surge_only else min(diff, max(surge_diff, 0.0))
        outcome = "surge_increase_not_notified"                                                              # 3.3
    elif increased and notified:
        refund, outcome = 0.0, "surge_increase_notified"
    elif diff > 0:
        refund, outcome = 0.0, "unexplained_difference"
    else:
        refund, outcome = 0.0, "no_overcharge"
    label = "rejected" if refund == 0 else ("upheld" if abs(refund - diff) < 0.015 else "partial")
    return {"upfront_quote": quote, "actual_fare": actual, "difference": diff, "surge_quote": m0, "surge_trip_start": m1,
            "surge_increased": increased, "rider_notified": notified, "surge_differential": surge_diff, "surge_only": surge_only,
            "outcome": outcome, "policy_refund": round(refund, 2), "ruling_label": label, "clause": "3.3"}


# ---------------------------------------------------------------- property damage
def damage_facts(trip: dict, dmg: dict) -> dict:
    d = (dmg or {}).get("damage_evidence") or {}
    end = parse_ts((dmg or {}).get("trip_end_time") or trip.get("end_time"))
    filed = parse_ts(d.get("claim_filed_at"))
    amount = float(d.get("claimed_amount") or trip.get("cleaning_fee_charged") or 0)
    ctype = d.get("claim_type", "cleaning")
    fee_charged = float(trip.get("cleaning_fee_charged") or amount)
    photos = d.get("photos") or []
    window = PHOTO_WINDOW_H * 3600
    submitted_in_time = bool(filed and end and filed <= end + window)                                         # 4.2
    checks = []
    for p in photos:
        taken = parse_ts(p.get("taken_at"))
        checks.append({"photo_id": p.get("photo_id"),
                       "within_24h": bool(taken and end and taken <= end + window),
                       "in_app_camera": p.get("source") == "in_app_camera" and bool(p.get("timestamped_by_app_camera")),
                       "linked_to_trip": bool(p.get("linked_to_trip"))})
    verifiable = [c for c in checks if c["within_24h"] and c["in_app_camera"] and c["linked_to_trip"]]
    quote_ok = bool(d.get("repair_quote"))
    if ctype == "repair":
        claim_valid = quote_ok and submitted_in_time
    else:
        claim_valid = bool(verifiable) and submitted_in_time and amount <= CLEANING_CAP + 1e-9
    refund = 0.0 if claim_valid else fee_charged                                                              # 4.4
    return {"claim_type": ctype, "claimed_amount": amount, "fee_charged": fee_charged, "photo_checks": checks,
            "verifiable_photos": len(verifiable), "submitted_in_24h": submitted_in_time, "over_cleaning_cap": amount > CLEANING_CAP,
            "claim_valid": claim_valid, "policy_refund": round(refund, 2), "ruling_label": "rejected" if claim_valid else "upheld",
            "outcome": "claim_valid" if claim_valid else "claim_evidence_insufficient", "clause": "4.2"}


# ---------------------------------------------------------------- confidence calibration (6.3)
def calibrate_confidence(completeness: float, clarity: float, precedent: float, credibility: float) -> float:
    """Evidence completeness, policy clarity, precedent alignment, party credibility (policy 6.3). Weights 40/30/15/15."""
    c = 0.40 * completeness + 0.30 * clarity + 0.15 * precedent + 0.15 * credibility
    return round(max(0.05, min(0.97, c)), 2)


def credibility_score(*profiles: dict) -> float:
    s = 1.0
    for p in profiles:
        if not p:
            continue
        ff = p.get("fraud_flags")
        flagged = (ff > 0) if isinstance(ff, (int, float)) else bool(ff)
        if flagged:
            s -= 0.10
        dh = p.get("dispute_history") or {}
        total = dh.get("total_disputes") or dh.get("total") or 0
        bad = dh.get("rejected") if "rejected" in dh else 0
        if total >= 3 and bad / total >= 0.5:
            s -= 0.05
    return round(max(0.5, s), 2)


def has_fraud_flag(*profiles: dict) -> bool:
    for p in profiles:
        ff = (p or {}).get("fraud_flags")
        if (isinstance(ff, (int, float)) and ff > 0) or (not isinstance(ff, (int, float)) and ff):
            return True
    return False
