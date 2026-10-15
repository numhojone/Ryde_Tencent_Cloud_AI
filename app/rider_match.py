"""Stage 1 of the rider app: which of the signed-in rider's trips is the story about?

Deterministic and offline, in both modes:
  a. classify the category with the intake rules; no signal at all -> ask one clarifying question
  b. only the signed-in rider's trips (rider_id from the session, never from the browser or the story)
  c. keep the trips the category is possible for, judged on trip data:
       no_show_charge  cancelled with a no-show / cancellation fee
       fare_dispute    final fare above the upfront quote
       route_deviation completed, with route data showing a longer actual distance than estimated
       property_damage a cleaning / damage fee or a damage claim on the trip
       safety_incident any trip
  d. rank them with the story-to-trip scorer (places, amounts, dates, weekdays, today / yesterday,
     time of day, driver name)
  e. 0 -> "no matching trip" plus the rider's recent trips; 1 clear -> "is this the one?";
     2 or more close -> a picker

Nothing here decides a ruling, and no case exists until the rider confirms a trip.
"""
from __future__ import annotations

from app.agents.intake import classify_by_rules
from app.extract import extract_numbers, extract_times, find_places
from app.i18n import CUR, L
from app.tools.fixtures import load_rider_trips
from app.trip_match import AUTO_MIN_MARGIN, _score_trip, is_cancelled, route_of, trip_time

MAX_CARDS = 5


def category_fits(category: str, t: dict) -> bool:
    if category == "no_show_charge":
        return is_cancelled(t) and bool(t.get("cancellation_fee") or t.get("cancellation_fee_charged"))
    if category == "fare_dispute":
        q, a = t.get("upfront_quote"), t.get("actual_fare")
        return not is_cancelled(t) and isinstance(q, (int, float)) and isinstance(a, (int, float)) and a > q + 0.009
    if category == "route_deviation":
        e, a = t.get("estimated_distance_km"), t.get("actual_distance_km")
        return (not is_cancelled(t) and isinstance(e, (int, float)) and isinstance(a, (int, float)) and a > e) \
            or bool(t.get("route_deviated"))
    if category == "property_damage":
        return bool(t.get("cleaning_fee_charged") or t.get("damage_fee_charged") or t.get("has_damage_claim"))
    return True                                            # safety_incident: any trip


def _fare(t: dict):
    for k in ("actual_fare", "fare_charged", "estimated_fare", "upfront_quote"):
        if isinstance(t.get(k), (int, float)):
            return t[k]
    return None


def _why_category(category: str, t: dict, lang: str) -> str:
    if category == "no_show_charge":
        fee = t.get("cancellation_fee") or t.get("cancellation_fee_charged")
        return L(lang, f"cancelled, {CUR}{fee:.2f} no-show fee", f"已取消，收取 {CUR}{fee:.2f} 爽约费")
    if category == "fare_dispute":
        return L(lang, f"fare {CUR}{t['actual_fare']:.2f} above the {CUR}{t['upfront_quote']:.2f} quote",
                       f"车费 {CUR}{t['actual_fare']:.2f} 高于报价 {CUR}{t['upfront_quote']:.2f}")
    if category == "route_deviation":
        return L(lang, f"{t['actual_distance_km']} km driven vs {t['estimated_distance_km']} km estimated",
                       f"实际 {t['actual_distance_km']} 公里，预估 {t['estimated_distance_km']} 公里")
    if category == "property_damage":
        fee = t.get("cleaning_fee_charged")
        return L(lang, f"{CUR}{fee:.2f} cleaning fee" if fee else "damage claim on this trip",
                       f"收取 {CUR}{fee:.2f} 清洁费" if fee else "该行程有损坏索赔")
    return ""


def card(t: dict, lang: str, why: list[str] | None = None) -> dict:
    tt = trip_time(t)
    pick, drop = route_of(t).split(" → ")
    return {"trip_id": t["trip_id"], "pickup": pick, "dropoff": drop, "time": tt.isoformat() if tt else None,
            # a cancelled trip was never paid for: what the rider was charged is the fee
            "fare": (t.get("cancellation_fee") or t.get("cancellation_fee_charged")) if is_cancelled(t) else _fare(t),
            "fare_kind": "fee" if is_cancelled(t) else "fare",
            "status": "cancelled" if is_cancelled(t) else "completed",
            "why": "; ".join(w for w in (why or []) if w)}


def clarify_question(lang: str) -> str:
    return L(lang, "Could you tell me a bit more about what went wrong? For example: the route was longer than expected, "
                   "the fare was higher than the quote, you were charged a cancellation or cleaning fee, or you felt unsafe.",
                   "能再多说一点出了什么问题吗？例如：路线比预期绕远、车费高于报价、被收了取消费或清洁费，或者您感到不安全。")


def find_trip(story: str, rider_id: str, lang: str = "en") -> dict:
    """Stage 1 decision for one story, within one rider's trips.

    Returns {state: clarify | none | confirm | pick, category, signals, message, candidates[], recent[]}.
    """
    category, signals = classify_by_rules(story)
    trips = load_rider_trips(rider_id)                    # only this rider's trips, whatever the story names
    recent = sorted(trips, key=lambda t: -(trip_time(t).timestamp() if trip_time(t) else 0))
    recent_cards = [card(t, lang) for t in recent[:MAX_CARDS]]
    base = {"category": category if signals else None, "signals": signals, "recent": recent_cards}
    if not signals:
        return {**base, "state": "clarify", "message": clarify_question(lang), "candidates": []}

    fits = [t for t in trips if category_fits(category, t)]
    if not fits:
        return {**base, "state": "none", "candidates": [],
                "message": L(lang, "I couldn't find a trip in your account that fits this. Here are your recent trips: tap one, "
                                   "or tell me more (where you were going, the date, the amount).",
                                   "在您的账户中没有找到符合描述的行程。以下是您最近的行程：可以点选其中一趟，"
                                   "或者再补充一些细节（目的地、日期、金额）。")}

    places = find_places(story)
    nums, times = extract_numbers(story), extract_times(story)
    scored = []
    for t in fits:
        s, why = _score_trip(t, story, places, nums, times, category, lang)
        tt = trip_time(t)
        scored.append((s, tt.timestamp() if tt else 0, t, why))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    lead = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0.0)
    # the category line already says what the "record shows ..." bonus says
    cards = [card(t, lang, [_why_category(category, t, lang)] + [w for w in why if not w.startswith(("record shows", "记录显示"))])
             for s, _, t, why in scored[:MAX_CARDS]]
    for c, (s, *_rest) in zip(cards, scored):
        c["score"] = round(s, 2)
    if len(scored) == 1 or lead >= AUTO_MIN_MARGIN:
        return {**base, "state": "confirm", "candidates": cards[:1],
                "message": L(lang, "I found this trip. Is this the one?", "我找到了这趟行程。是这一趟吗？")}
    close = [c for c, (s, *_r) in zip(cards, scored) if scored[0][0] - s < AUTO_MIN_MARGIN]
    return {**base, "state": "pick", "candidates": close,
            "message": L(lang, f"{len(close)} of your trips could fit. Which one was it?",
                               f"您有 {len(close)} 趟行程可能符合。是哪一趟？")}


def owns_trip(rider_id: str, trip_id: str) -> bool:
    return any(t["trip_id"] == trip_id for t in load_rider_trips(rider_id))
