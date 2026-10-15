"""Match a rider's story to one of their recent trips.

A story cannot create evidence: GPS, chat, fare logs and app events always come from the platform's
records for a trip. So before anything is ruled, the story has to be tied to a real trip. This runs in
code (both LLM and deterministic modes), before the intake agent.

Scoring, per trip:
- place names in the story vs the trip's pickup / drop-off names (fuzzy, case-insensitive, local aliases)
- amounts in the story vs the trip's quote, fare and fee fields; distance, duration and speed vs the record
- dates / times in the story vs the trip's times
- whether the category the story suggests is possible for the trip (a cancelled trip cannot be a route
  deviation, a completed trip is not a no-show)

A trip is chosen only when its score clears AUTO_MIN_SCORE and leads the runner-up by AUTO_MIN_MARGIN.
Otherwise nothing is chosen and the top candidates are returned for the rider to pick from.

claim_check() compares the story's numbers with the chosen trip's records. It is informational only
and is never passed to the agents that rule.
"""
from __future__ import annotations

import datetime as _dt
import re

from app.extract import extract_numbers, extract_times, find_places
from app.i18n import L, CUR

AUTO_MIN_SCORE = 3.0
AUTO_MIN_MARGIN = 1.5

_MONEY_FIELDS = ("upfront_quote", "estimated_fare", "actual_fare", "fare_charged", "fare_difference", "excess_fare",
                 "cancellation_fee", "cancellation_fee_charged", "cleaning_fee_charged")
_RELEVANT = {
    "route_deviation": ("estimated_fare", "actual_fare", "excess_fare"),
    "no_show_charge": ("cancellation_fee", "cancellation_fee_charged"),
    "fare_dispute": ("upfront_quote", "actual_fare", "fare_difference"),
    "property_damage": ("cleaning_fee_charged",),
    "safety_incident": ("fare_charged", "actual_fare"),
}
_FIELD_LABEL = {
    "upfront_quote": ("upfront quote", "预付报价"), "estimated_fare": ("estimated fare", "预估车费"),
    "actual_fare": ("actual fare", "实际车费"), "fare_charged": ("fare charged", "所收车费"),
    "fare_difference": ("fare difference", "车费差额"), "excess_fare": ("excess fare", "超额车费"),
    "cancellation_fee": ("cancellation fee", "取消费"), "cancellation_fee_charged": ("cancellation fee", "取消费"),
    "cleaning_fee_charged": ("cleaning fee", "清洁费"),
}


def is_cancelled(t: dict) -> bool:
    return "cancel" in str(t.get("status") or "").lower() or bool(t.get("cancellation_time"))


def trip_time(t: dict) -> _dt.datetime | None:
    for k in ("start_time", "scheduled_time", "driver_arrival_time", "cancellation_time"):
        if t.get(k):
            try:
                return _dt.datetime.fromisoformat(t[k])
            except ValueError:
                continue
    return None


def route_of(t: dict) -> str:
    p = (t.get("pickup_location") or {}).get("name", "?")
    d = (t.get("dropoff_location") or {}).get("name", "?")
    return f"{p} → {d}"


def _money(v: float) -> str:
    return f"{CUR}{v:.2f}"


def _score_trip(t: dict, story: str, places: list[dict], nums: dict, times: list[dict],
                category: str | None, lang: str, now: _dt.datetime | None = None) -> tuple[float, list[str]]:
    score, reasons = 0.0, []
    names = {"pickup": (t.get("pickup_location") or {}).get("name"),
             "dropoff": (t.get("dropoff_location") or {}).get("name")}

    # ---- places
    for role, name in names.items():
        hit = max((h for h in places if h["place"] == name), key=lambda h: h["coverage"], default=None)
        if not hit:
            continue
        score += 3.0 * hit["coverage"] + (0.5 if hit["role"] == role else 0.0)
        reasons.append(L(lang, f"{'pickup' if role == 'pickup' else 'drop-off'} {name}",
                               f"{'上车点' if role == 'pickup' else '下车点'} {name}"))

    # ---- amounts
    amt_pts, matched_vals = 0.0, set()
    for a in nums["amounts"]:
        for f in _MONEY_FIELDS:
            rv = t.get(f)
            if isinstance(rv, (int, float)) and abs(rv - a["value"]) < 0.011 and a["value"] not in matched_vals:
                matched_vals.add(a["value"])
                amt_pts += 1.5 + (0.5 if category and f in _RELEVANT.get(category, ()) else 0.0)
                en, zh = _FIELD_LABEL[f]
                reasons.append(L(lang, f"{_money(a['value'])} = {en}", f"{_money(a['value'])} = {zh}"))
    score += min(amt_pts, 4.0)

    # ---- distance, duration, speed
    for d in nums["distances"]:
        for f in ("excess_distance_km", "actual_distance_km", "estimated_distance_km"):
            rv = t.get(f)
            if isinstance(rv, (int, float)) and abs(rv - d["value"]) <= max(0.15, 0.03 * rv):
                score += 1.5
                reasons.append(L(lang, f"{d['value']:g} km = {f.replace('_', ' ')}", f"{d['value']:g} 公里与行程记录一致"))
                break
    for d in nums["durations"]:
        for f in ("actual_duration_min", "estimated_duration_min"):
            rv = t.get(f)
            if isinstance(rv, (int, float)) and abs(rv - d["value"]) <= 1:
                score += 1.0
                reasons.append(L(lang, f"{d['value']:g} min = {f.replace('_', ' ')}", f"{d['value']:g} 分钟与行程记录一致"))
                break
    peak = t.get("gps_max_speed_kmh")
    for s in nums["speeds"]:
        if isinstance(peak, (int, float)) and peak >= 0.9 * s["value"]:
            score += 1.5
            reasons.append(L(lang, f"GPS peak {peak:g} km/h fits {s['value']:g} km/h", f"GPS 最高车速 {peak:g} 公里/小时，与 {s['value']:g} 相符"))
            break

    # ---- dates and times
    tt = trip_time(t)
    if tt:
        date_hit = hour_hit = part_hit = False
        for x in times:
            if x.get("month") and x.get("day") == tt.day and x["month"] == tt.month:
                date_hit = True
            if x.get("hour") is not None:
                diff = abs((x["hour"] * 60 + x.get("minute", 0)) - (tt.hour * 60 + tt.minute))
                if min(diff, 1440 - diff) <= 60:
                    hour_hit = True
            if x.get("part"):
                h = tt.hour
                part_hit |= {"morning": 5 <= h < 12, "afternoon": 12 <= h < 18,
                             "evening": h >= 17 or h < 2, "late_night": h < 5}[x["part"]]
        if not date_hit:
            for x in times:
                if x.get("weekday") is not None and x["weekday"] == tt.weekday():
                    score += 1.0
                    reasons.append(L(lang, f"on a {tt.strftime('%A')}", f"星期{'一二三四五六日'[tt.weekday()]}"))
                    break
                if x.get("days_ago") is not None and (now or _dt.datetime.now(tt.tzinfo)).date() - _dt.timedelta(days=x["days_ago"]) == tt.date():
                    date_hit = True
        if date_hit:
            score += 1.5
            reasons.append(L(lang, f"date {tt.day} {tt.strftime('%b')}", f"日期 {tt.month}月{tt.day}日"))
        if hour_hit:
            score += 1.0
            reasons.append(L(lang, f"time around {tt.strftime('%H:%M')}", f"时间约 {tt.strftime('%H:%M')}"))
        elif part_hit:
            score += 0.5
            reasons.append(L(lang, "time of day fits", "时段相符"))

    # ---- driver's name (first or full name written in the story)
    dn = (t.get("driver_name") or "").strip()
    if dn:
        low = (story or "").lower()
        parts = [w for w in dn.lower().split() if len(w) >= 3]
        if dn.lower() in low or any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low) for w in parts):
            score += 2.0
            reasons.append(L(lang, f"driver {dn}", f"司机 {dn}"))

    # ---- is the category possible for this trip?
    if category:
        cancelled = is_cancelled(t)
        events = {e.get("event_type") for e in t.get("app_events") or []}
        if category in ("route_deviation", "fare_dispute") and cancelled:
            score -= 4.0
            reasons.append(L(lang, "cancelled trip, cannot be a route or fare dispute", "已取消的行程，不可能是绕路或车费争议"))
        elif category == "no_show_charge" and not cancelled:
            score -= 4.0
            reasons.append(L(lang, "completed trip, cannot be a no-show", "已完成的行程，不可能是爽约"))
        elif category == "route_deviation" and (t.get("route_deviated") or t.get("excess_distance_km")):
            score += 1.5
            reasons.append(L(lang, "record shows a route deviation", "记录显示有绕路"))
        elif category == "no_show_charge" and (t.get("cancellation_fee") or t.get("cancellation_fee_charged")):
            score += 1.5
            reasons.append(L(lang, "record shows a no-show fee", "记录显示收取了爽约费"))
        elif category == "fare_dispute" and t.get("upfront_quote") is not None and t.get("actual_fare") is not None \
                and abs(t["actual_fare"] - t["upfront_quote"]) > 0.01:
            score += 1.5
            reasons.append(L(lang, "record shows fare above quote", "记录显示车费高于报价"))
        elif category == "property_damage":
            if t.get("cleaning_fee_charged") or "cleaning_fee_charged" in events or "damage_claim_filed" in events:
                score += 1.5
                reasons.append(L(lang, "record shows a cleaning fee", "记录显示收取了清洁费"))
            else:
                score -= 2.0
        elif category == "safety_incident":
            if "speeding_alert" in events and _mentions_speed(story):
                score += 2.0
                reasons.append(L(lang, "record has a speeding alert", "记录中有超速警报"))
            elif cancelled:
                score -= 1.0
    return round(score, 2), reasons


def _mentions_speed(story: str) -> bool:
    low = (story or "").lower()
    return any(w in low for w in ("speeding", "too fast", "km/h", "kmh", "超速", "开太快", "开得太快", "laju", "வேக"))


def match_trip(story: str, extracted_facts: dict | None, trips: list[dict], *,
               category: str | None = None, lang: str = "en") -> dict:
    """Score the story against each trip. Returns {trip_id | None, confidence, reasons, candidates[]}.

    `trips` are platform trip records (trip_data shape, optionally with app_events / gps_max_speed_kmh).
    `category` is the rule-based guess of the dispute type, or None when the story gave no signal.
    `extracted_facts` is accepted for callers that already have them; the matcher re-reads the story
    itself so it sees every number and place, not only the ones that were given a role.
    """
    places = find_places(story, tuple(sorted({n for t in trips for n in (
        (t.get("pickup_location") or {}).get("name"), (t.get("dropoff_location") or {}).get("name")) if n})))
    nums = extract_numbers(story)
    times = extract_times(story)
    scored = []
    for t in trips:
        s, why = _score_trip(t, story, places, nums, times, category, lang)
        tt = trip_time(t)
        scored.append({"trip_id": t.get("trip_id"), "route": route_of(t), "score": s, "reasons": why,
                       "status": "cancelled" if is_cancelled(t) else "completed",
                       "time": tt.isoformat() if tt else None, "_ts": tt.timestamp() if tt else 0})
    # best score first; among equals, the most recent trip first
    scored.sort(key=lambda c: (-c["score"], -c["_ts"]))
    for c in scored:
        c.pop("_ts")
    top = scored[0] if scored else None
    second = scored[1]["score"] if len(scored) > 1 else 0.0
    if not top:
        return {"trip_id": None, "confidence": 0.0, "reasons": [], "candidates": []}
    lead = top["score"] - max(second, 0.0)
    strength = min(1.0, max(top["score"], 0.0) / 6.0)
    separation = lead / top["score"] if top["score"] > 0 else 0.0
    confidence = round(min(0.99, 0.5 * strength + 0.5 * separation), 2)
    chosen = top["score"] >= AUTO_MIN_SCORE and lead >= AUTO_MIN_MARGIN
    return {
        "trip_id": top["trip_id"] if chosen else None,
        "route": top["route"] if chosen else None,
        "confidence": confidence if chosen else 0.0,
        "reasons": top["reasons"] if chosen else [],
        "candidates": scored[:3],
    }


# ---------------------------------------------------------------- claim check

def _cmp(v: float, rv: float) -> str:
    return "consistent" if abs(v - rv) <= max(0.011, 0.03 * abs(rv)) else "discrepancy"


def claim_check(story: str, facts: dict, trip: dict, lang: str = "en") -> list[dict]:
    """Compare the numbers in the story with the trip's records. Informational only: never used to rule.

    `trip` is the trip_data record (optionally with gps_max_speed_kmh).
    Each item: {claim, story_value, record_field, record_value, status} with status
    consistent | discrepancy | not_in_record.
    """
    out: list[dict] = []

    def add(claim, v, fields, label_en, label_zh):
        if v is None:
            return
        for f in fields:
            rv = trip.get(f)
            if isinstance(rv, (int, float)):
                out.append({"claim": claim, "label": L(lang, label_en, label_zh), "story_value": v,
                            "record_field": f, "record_value": rv, "status": _cmp(v, rv)})
                return
        out.append({"claim": claim, "label": L(lang, label_en, label_zh), "story_value": v,
                    "record_field": None, "record_value": None, "status": "not_in_record"})

    fee = facts.get("fee_type")
    add("quoted_amount", facts.get("quoted_amount"), ("upfront_quote", "estimated_fare"), "Quoted / expected fare", "报价 / 预期车费")
    charged_fields = {"cleaning_fee": ("cleaning_fee_charged",),
                      "cancellation_fee": ("cancellation_fee", "cancellation_fee_charged"),
                      "damage_fee": ("damage_fee_charged",)}.get(fee, ("actual_fare", "fare_charged"))
    add("charged_amount", facts.get("charged_amount"), charged_fields, "Amount charged", "被收取金额")
    diff = facts.get("claimed_difference")
    if diff is not None:
        rec = trip.get("fare_difference", trip.get("excess_fare"))
        if rec is None and isinstance(trip.get("actual_fare"), (int, float)) and isinstance(trip.get("upfront_quote"), (int, float)):
            rec = round(trip["actual_fare"] - trip["upfront_quote"], 2)
        out.append({"claim": "claimed_difference", "label": L(lang, "Difference claimed", "主张的差额"),
                    "story_value": diff, "record_field": "fare_difference" if rec is not None else None,
                    "record_value": rec, "status": _cmp(diff, rec) if rec is not None else "not_in_record"})
    nums = extract_numbers(story)
    for d in nums["distances"][:2]:
        f = "excess_distance_km" if trip.get("excess_distance_km") is not None else "actual_distance_km"
        add("distance_km", d["value"], (f,), "Distance (km)", "距离（公里）")
    for s in nums["speeds"][:1]:
        peak = trip.get("gps_max_speed_kmh")
        out.append({"claim": "speed_kmh", "label": L(lang, "Speed (km/h)", "车速（公里/小时）"), "story_value": s["value"],
                    "record_field": "gps_max_speed_kmh" if peak is not None else None, "record_value": peak,
                    # "over 100 km/h" is borne out by any recorded peak at or near that speed
                    "status": ("not_in_record" if peak is None else
                               "consistent" if peak >= 0.9 * s["value"] else "discrepancy")})
    return out
