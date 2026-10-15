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

import re

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
    from app.agents.intake import type_label
    tt = trip_time(t)
    pick, drop = route_of(t).split(" → ")
    k = t.get("ticket_type")
    return {"trip_id": t["trip_id"], "pickup": pick, "dropoff": drop, "time": tt.isoformat() if tt else None,
            "dispute_id": t.get("dispute_id"), "ticket_type": k, "ticket_label": type_label(k, lang) if k else None,
            # a cancelled trip was never paid for: what the rider was charged is the fee
            "fare": (t.get("cancellation_fee") or t.get("cancellation_fee_charged")) if is_cancelled(t) else _fare(t),
            "fare_kind": "fee" if is_cancelled(t) else "fare",
            "status": "cancelled" if is_cancelled(t) else "completed",
            "why": "; ".join(w for w in (why or []) if w)}


def clarify_question(lang: str) -> str:
    return L(lang, "Could you tell me a bit more about what went wrong? For example: the route was longer than expected, "
                   "you were charged a cancellation or cleaning fee, or you felt unsafe.",
                   "能再多说一点出了什么问题吗？例如：路线比预期绕远、被收了取消费或清洁费，或者您感到不安全。")


ONLY_YOUR_ACCOUNT = ("I can only look at trips on your account.", "我只能查看您账户中的行程。")
_TRIP_ID = re.compile(r"\bTRIP-\d{4}-\d+\b", re.I)
_RIDER_ID = re.compile(r"\bR-\d{4}\b", re.I)
_DRIVER_ID = re.compile(r"\bD-\d{4}\b", re.I)
_LIST = re.compile(r"\b(?:list|show|see|view|what are)\b[^.?!]{0,30}\b(?:my|all)\b[^.?!]{0,12}\b(?:rides|trips|bookings)\b"
                   r"|\bmy (?:rides|trips)\b\s*\??$|我的(?:所有)?行程|列出.*行程", re.I)


def names_someone_else(story: str, rider_id: str, trips: list[dict]) -> bool:
    """Does the story point at a trip, rider or driver that is not this rider's? (Checked before anything else.)"""
    from app.tools.fixtures import list_driver_ids, list_rider_ids, person_name
    mine = {t["trip_id"].upper() for t in trips}
    if any(m.group(0).upper() not in mine for m in _TRIP_ID.finditer(story)):
        return True
    if any(m.group(0).upper() != rider_id for m in _RIDER_ID.finditer(story)):
        return True
    my_drivers = {t.get("driver_id") for t in trips}
    if any(m.group(0).upper() not in my_drivers for m in _DRIVER_ID.finditer(story)):
        return True
    low = story.lower()
    for rid in list_rider_ids():                                # another rider by full name, or "Sarah's trip"
        name = person_name(rid)
        if rid == rider_id or not name:
            continue
        full = name.lower()
        first = full.split()[0]
        if full in low or re.search(rf"(?<![a-z]){re.escape(first)}'s\b", low):
            return True
    for did in list_driver_ids():                               # a driver who never drove this rider
        name = person_name(did)
        if did not in my_drivers and name and name.lower() in low:
            return True
    return False


def preflight(story: str, rider_id: str, lang: str = "en") -> dict | None:
    """The checks that never need language understanding: another rider's trip / name / id (refused), "list my
    rides", and one of the rider's own trip ids. Returns a stage-1 result, or None to go on and classify."""
    return find_trip(story, rider_id, lang, category="__preflight__")


def find_trip(story: str, rider_id: str, lang: str = "en", category: str | None = None) -> dict | None:
    """Stage 1 decision for one story, within one rider's own trips only.

    category: the dispute type already understood (by the model in Live AI mode, or tapped by the rider); without
    it, the keyword rules classify (Offline demo and the older callers).
    Returns {state: foreign | list | clarify | none | confirm | pick, category, signals, message, candidates[], recent[]}.
    The rider's trips are loaded first, from the session's rider_id; nothing else is ever looked at.
    """
    trips = load_rider_trips(rider_id)                    # only this rider's trips, whatever the story names
    by_date = sorted(trips, key=lambda t: -(trip_time(t).timestamp() if trip_time(t) else 0))
    all_cards = [card(t, lang) for t in by_date]
    peek = category == "__preflight__"
    if category and not peek:
        signals = [category]
    elif peek:
        category, signals = None, []
    else:
        category, signals = classify_by_rules(story)
    base = {"category": category if signals else None, "signals": signals, "recent": all_cards}
    if names_someone_else(story, rider_id, trips):
        # no hint whether that trip, rider or driver exists
        return {**base, "state": "foreign", "candidates": [], "recent": [], "message": L(lang, *ONLY_YOUR_ACCOUNT)}
    if _LIST.search(story):
        return {**base, "state": "list", "candidates": all_cards,
                "message": L(lang, f"Here are your {len(all_cards)} rides. Tap the one you need help with.",
                                   f"这是您的 {len(all_cards)} 趟行程。请点选需要处理的那一趟。")}
    own_id = next((m.group(0).upper() for m in _TRIP_ID.finditer(story)), None)
    if own_id:
        t = next(t for t in trips if t["trip_id"].upper() == own_id)
        return {**base, "state": "confirm", "candidates": [card(t, lang)],
                "message": L(lang, "I found this trip. Is this the one?", "我找到了这趟行程。是这一趟吗？")}
    if peek:
        return None
    if not signals:
        return {**base, "state": "clarify", "message": clarify_question(lang), "candidates": []}

    # the ticket on each trip says what kind of dispute it is; trip evidence is the fallback
    fits = [t for t in trips if t.get("ticket_type") == category] or [t for t in trips if category_fits(category, t)]
    if not fits:
        return {**base, "state": "none", "candidates": [],
                "message": L(lang, "I couldn't find a ride of that kind on your account. Here are all your rides: tap one, "
                                   "or tell me more (where you were going, the date, the amount).",
                                   "在您的账户中没有找到这类行程。以下是您的全部行程：可以点选其中一趟，"
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


def type_mismatch(story: str, trip: dict, understood: str | None = None) -> dict | None:
    """The story sounds like one kind of dispute but the trip's ticket is another: ask, never silently override.
    understood: the type stage 1 already worked out (model or rider's tap); else the keyword rules decide."""
    if understood in ("route_deviation", "no_show_charge", "property_damage", "safety_incident"):
        category, signals = understood, [understood]
    else:
        category, signals = classify_by_rules(story)
    ticket_type = trip.get("ticket_type")
    if signals and ticket_type and category != ticket_type:
        return {"story_type": category, "ticket_type": ticket_type}
    return None


# ---------------------------------------------------------------- quick-fill stories for the demo strip

_VAGUE = {
    "route_deviation": ("My driver took a much longer route than usual and I paid more than I should have.",
                        "司机绕路了，走了更远的路线，我多付了钱。"),
    "no_show_charge": ("The driver never came and I was still charged a $5 cancellation fee.", "司机一直没来，我还被收了$5取消费。"),
    "property_damage": ("I was charged a cleaning fee but I never dirtied the car.", "我被收了清洁费，但我根本没有弄脏车。"),
    "safety_incident": ("My driver was driving dangerously and I felt unsafe.", "司机开车很危险，我觉得很不安全。"),
}


def _specific(t: dict) -> tuple[str, str]:
    tt = trip_time(t)
    d_en, d_zh = f"{tt.day} {tt:%b}", f"{tt.month}月{tt.day}日"
    a, b = route_of(t).split(" → ")
    k = t.get("ticket_type")
    if k == "route_deviation":
        return (f"On {d_en} the driver took a long detour from {a} to {b} and charged me more.",
                f"{d_zh}从{a}到{b}，司机绕路了，多收了我的钱。")
    if k == "no_show_charge":
        return (f"On {d_en} I waited at {a} but the driver never came, and I was charged a $5 cancellation fee.",
                f"{d_zh}我在{a}等车，司机一直没来，还被收了$5取消费。")
    if k == "property_damage":
        fee = t.get("cleaning_fee_charged") or 0
        return (f"I was charged a S${fee:.0f} cleaning fee after my ride from {a} on {d_en}, but I never dirtied the car.",
                f"{d_zh}从{a}坐车后被收了S${fee:.0f}清洁费，但我根本没有弄脏车。")
    return (f"On {d_en}, on my ride from {a} to {b}, the driver was driving dangerously and I felt unsafe.",
            f"{d_zh}从{a}到{b}的行程中，司机开车很危险，我觉得很不安全。")


def demo_stories(rider_id: str) -> list[dict]:
    """Quick-fill stories built from this rider's own rides, so every button leads to a real match for them."""
    from app.agents.intake import type_label
    trips = sorted(load_rider_trips(rider_id), key=lambda t: trip_time(t).timestamp() if trip_time(t) else 0)
    out = []
    for k in ("route_deviation", "no_show_charge", "property_damage", "safety_incident"):
        mine = [t for t in trips if t.get("ticket_type") == k]
        if not mine:
            continue
        if len(mine) >= 2:
            en, zh = _VAGUE[k]
            out.append({"key": f"{k}_pick", "en": en, "zh": zh, "expect": "pick",
                        "label_en": f"{type_label(k, 'en')} ({len(mine)} rides fit)", "label_zh": f"{type_label(k, 'zh')}（{len(mine)} 趟符合）"})
        t = mine[-1]
        en, zh = _specific(t)
        tt = trip_time(t)
        out.append({"key": f"{k}_one", "en": en, "zh": zh, "expect": "confirm", "trip_id": t["trip_id"],
                    "label_en": f"{type_label(k, 'en')}, {tt.day} {tt:%b}", "label_zh": f"{type_label(k, 'zh')}，{tt.month}月{tt.day}日"})
    out.append({"key": "list", "en": "Show me all my rides.", "zh": "列出我的所有行程。", "expect": "list",
                "label_en": "List my rides", "label_zh": "列出我的行程"})
    out.append({"key": "unclear", "en": "Something went wrong with my last ride.", "zh": "我上一趟行程出了点问题。", "expect": "clarify",
                "label_en": "Unclear story", "label_zh": "描述不清"})
    return out
