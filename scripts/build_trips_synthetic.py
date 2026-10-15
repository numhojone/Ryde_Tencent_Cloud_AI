"""Build fixtures/trips_synthetic.json and fixtures/demo_accounts.json (deterministic: no randomness).

Every trip here is synthetic ("_source": "Synthetic"). It gives each demo rider 3 to 6 trips so that
matching a story to a trip has to choose within the signed-in rider's own history. Official files
(DISP-001/002/003, their trips and rider profiles) are not touched: extra trips for official riders
live only in this file.

    python scripts/build_trips_synthetic.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SGT = dt.timezone(dt.timedelta(hours=8))

P = {  # name -> (lat, lng)
    "Raffles Place": (1.2840, 103.8515), "Holland Village": (1.3112, 103.7958), "Orchard Central": (1.3048, 103.8318),
    "Changi Airport T3": (1.3644, 103.9915), "Redhill MRT": (1.2896, 103.8168), "Great World": (1.2934, 103.8318),
    "VivoCity": (1.2648, 103.8223), "Tiong Bahru Plaza": (1.2847, 103.8382), "Novena Square": (1.3203, 103.8438),
    "Toa Payoh Hub": (1.3326, 103.8478), "Marina Bay Sands": (1.2834, 103.8607), "Bugis Junction": (1.3000, 103.8556),
    "Funan": (1.2913, 103.8498), "Suntec City": (1.2950, 103.8580), "Paya Lebar Quarter": (1.3176, 103.8930),
    "Changi Business Park": (1.3340, 103.9640), "Bedok Mall": (1.3249, 103.9294), "Kallang Wave Mall": (1.3030, 103.8750),
    "Orchard MRT": (1.3040, 103.8318), "Tampines Mall": (1.3420, 103.9480), "Changi Airport T2": (1.3555, 103.9890),
    "Clarke Quay": (1.3100, 103.8500), "Bishan Junction 8": (1.3504, 103.8483), "HarbourFront Centre": (1.2653, 103.8220),
    "Chinatown Point": (1.2851, 103.8448), "Tanjong Pagar Centre": (1.2766, 103.8458),
}


def ts(d: dt.datetime) -> str:
    return d.isoformat(timespec="seconds")


def loc(name: str) -> dict:
    return {"name": name, "lat": P[name][0], "lng": P[name][1]}


def line(a: str, b: str, start: dt.datetime, minutes: int, n: int = 5) -> list[dict]:
    (la, ga), (lb, gb) = P[a], P[b]
    speeds = [0] + [38 + 9 * (i % 3) for i in range(n - 2)] + [0]
    return [{"timestamp": ts(start + dt.timedelta(minutes=round(minutes * i / (n - 1)))),
             "lat": round(la + (lb - la) * i / (n - 1), 5), "lng": round(ga + (gb - ga) * i / (n - 1), 5),
             "speed_kmh": speeds[i]} for i in range(n)]


def clean_trip(tid, rider, driver, driver_name, a, b, start, minutes, km, fare):
    end = start + dt.timedelta(minutes=minutes)
    base = round(fare - 3.0, 2)
    return {
        "trip_id": tid, "_source": "Synthetic",
        "trip_data": {"trip_id": tid, "rider_id": rider, "driver_id": driver, "driver_name": driver_name,
                      "pickup_location": loc(a), "dropoff_location": loc(b), "start_time": ts(start), "end_time": ts(end),
                      "estimated_duration_min": minutes, "actual_duration_min": minutes,
                      "estimated_distance_km": km, "actual_distance_km": km,
                      "upfront_quote": fare, "actual_fare": fare, "status": "completed", "currency": "SGD"},
        "gps_telemetry": line(a, b, start, minutes),
        "chat_logs": [
            {"message_id": "MSG-001", "sender": "driver", "sender_name": driver_name, "type": "message",
             "timestamp": ts(start - dt.timedelta(minutes=2)), "message": f"Hi, I'm at {a} now."},
            {"message_id": "MSG-002", "sender": "rider", "type": "message",
             "timestamp": ts(start - dt.timedelta(minutes=1)), "message": "Ok, coming."},
        ],
        "app_events": [{"timestamp": ts(start), "event_type": "trip_started", "details": "Trip started."},
                       {"timestamp": ts(end), "event_type": "trip_ended", "details": "Trip completed."}],
        "fare_breakdown": {"upfront_quote": {"surge_multiplier": 1.0, "surge_amount": 0.0, "total": fare, "surgeable_subtotal": base},
                           "actual_fare": {"surge_multiplier": 1.0, "surge_amount": 0.0, "total": fare, "surgeable_subtotal": base}},
        "surge_pricing_log": {"quote_time_surge": 1.0, "trip_start_surge": 1.0, "rider_notified": False,
                              "notification_method": None, "notification_timestamp": None, "reason": "no_surge"},
    }


def route_trip():
    """R-4521: a second route deviation (1.6 km over, no traffic justification, rider not told)."""
    tid, start = "TRIP-2026-30101", dt.datetime(2026, 9, 27, 19, 10, tzinfo=SGT)
    a, b = "Raffles Place", "Holland Village"
    t = clean_trip(tid, "R-4521", "D-3456", "Tan Boon Huat", a, b, start, 24, 9.8, 18.40)
    td = t["trip_data"]
    td.update({"actual_duration_min": 27, "end_time": ts(start + dt.timedelta(minutes=27)), "actual_distance_km": 11.4,
               "estimated_fare": 18.40, "actual_fare": 19.68, "excess_distance_km": 1.6, "excess_fare": 1.28,
               "route_deviated": True})
    td.pop("upfront_quote")
    wps = [(1.2840, 103.8515), (1.2790, 103.8420), (1.2860, 103.8150), (1.2990, 103.8020), (1.3112, 103.7958)]
    t["optimal_route"] = {"route_name": "AYE (Ayer Rajah Expressway) via Alexandra Rd", "estimated_distance_km": 9.8,
                          "estimated_duration_min": 24,
                          "waypoints": [{"point": i + 1, "lat": la, "lng": ln} for i, (la, ln) in enumerate(wps)]}
    actual = [(1.2840, 103.8515, 0), (1.2905, 103.8470, 32), (1.3010, 103.8380, 41), (1.3120, 103.8290, 46),
              (1.3190, 103.8150, 50), (1.3200, 103.8040, 44), (1.3150, 103.7990, 30), (1.3112, 103.7958, 0)]
    t["gps_telemetry"] = [{"timestamp": ts(start + dt.timedelta(minutes=round(27 * i / 7))), "lat": la, "lng": ln, "speed_kmh": sp}
                          for i, (la, ln, sp) in enumerate(actual)]
    t["chat_logs"] += [
        {"message_id": "MSG-003", "sender": "rider", "type": "message", "timestamp": ts(start + dt.timedelta(minutes=9)),
         "message": "Why are we going up through Orchard? Isn't the AYE quicker?"},
        {"message_id": "MSG-004", "sender": "driver", "sender_name": "Tan Boon Huat", "type": "message",
         "timestamp": ts(start + dt.timedelta(minutes=10)), "message": "This one also can, same same."},
    ]
    t["traffic_conditions"] = [{"incident_id": "TC-301", "road": "CTE (Central Expressway)", "direction": "northbound",
                                "incident_type": "slow_traffic", "severity": "low", "timestamp": ts(start - dt.timedelta(minutes=10)),
                                "clear_time": ts(start + dt.timedelta(minutes=20)), "description": "Slow traffic near Bukit Timah exit."}]
    t["fare_breakdown"] = {"estimated": {"total": 18.40}, "actual": {"total": 19.68}, "delta": {"total": 1.28},
                           "excess_distance_fare": 1.28, "distance_rate_per_km": 0.8}
    t.pop("surge_pricing_log")
    return t


def noshow_trip():
    """R-7823: a second no-show fee: driver arrived and waited, messaged once, never called (2.3 not met)."""
    tid, sched = "TRIP-2026-30201", dt.datetime(2026, 9, 24, 18, 30, tzinfo=SGT)
    a, b = "Redhill MRT", "Great World"
    la, ln = P[a]
    m = lambda x: sched + dt.timedelta(minutes=x)
    gps = [{"timestamp": ts(m(-6)), "lat": 1.2950, "lng": 103.8100, "speed_kmh": 36, "status": "en_route"},
           {"timestamp": ts(m(-3)), "lat": 1.2915, "lng": 103.8150, "speed_kmh": 22, "status": "en_route"}]
    gps += [{"timestamp": ts(m(x)), "lat": la, "lng": round(ln + 0.0001 * (x % 2), 5), "speed_kmh": 0, "status": "waiting"}
            for x in (3, 5, 7, 9)]
    gps.append({"timestamp": ts(m(10)), "lat": 1.2880, "lng": 103.8200, "speed_kmh": 28, "status": "departed"})
    return {
        "trip_id": tid, "_source": "Synthetic",
        "trip_data": {"trip_id": tid, "rider_id": "R-7823", "driver_id": "D-4410", "driver_name": "Nur Aisyah",
                      "pickup_location": loc(a), "dropoff_location": loc(b), "scheduled_time": ts(sched),
                      "driver_arrival_time": ts(m(3)), "driver_wait_start": ts(m(3)), "cancellation_time": ts(m(9)),
                      "cancellation_fee": 5.0, "cancellation_reason": "rider_no_show", "status": "cancelled_no_show_rider",
                      "upfront_quote": 9.20, "currency": "SGD"},
        "gps_telemetry": gps,
        "chat_logs": [
            {"timestamp": ts(m(3)), "sender": "driver", "type": "message", "content": "I'm at Redhill MRT exit A, grey Corolla."},
            {"timestamp": ts(m(11)), "sender": "rider", "type": "message", "content": "Sorry I'm here now, where are you?"},
        ],
        "app_events": [
            {"timestamp": ts(m(-12)), "event_type": "booking_confirmed", "details": "Booked Redhill MRT to Great World, pickup 18:30."},
            {"timestamp": ts(m(-11)), "event_type": "driver_assigned", "details": "Driver D-4410 assigned."},
            {"timestamp": ts(m(3)), "event_type": "driver_arrived", "details": "Driver arrived at the pickup point."},
            {"timestamp": ts(m(5)), "event_type": "free_wait_expired", "details": "Free 5-minute wait ended."},
            {"timestamp": ts(m(9)), "event_type": "driver_cancelled_no_show", "details": "Driver cancelled: rider no-show."},
            {"timestamp": ts(m(9)), "event_type": "no_show_fee_charged", "details": "S$5.00 no-show fee charged."},
        ],
    }


def D(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=SGT)


TRIPS = [
    # R-4521 (official rider, DISP-001): a second route deviation + two clean trips
    route_trip(),
    clean_trip("TRIP-2026-30102", "R-4521", "D-2398", "Lim Wei Ming", "Orchard Central", "Raffles Place", D(2026, 9, 18, 8, 20), 14, 4.6, 13.20),
    clean_trip("TRIP-2026-30103", "R-4521", "D-6021", "Hafiz Rahman", "Changi Airport T3", "Orchard Central", D(2026, 9, 30, 22, 40), 28, 21.0, 29.10),
    # R-7823 (official rider, DISP-002): a second no-show fee on another day + two clean trips
    noshow_trip(),
    clean_trip("TRIP-2026-30202", "R-7823", "D-7002", "Ong Kai Wen", "VivoCity", "Tiong Bahru Plaza", D(2026, 9, 16, 12, 5), 11, 3.4, 9.80),
    clean_trip("TRIP-2026-30203", "R-7823", "D-1187", "Rajesh Kumar", "Novena Square", "Toa Payoh Hub", D(2026, 10, 2, 17, 45), 10, 2.9, 8.60),
    # R-9001 (official rider, DISP-003): normal fares only; one same-day look-alike
    clean_trip("TRIP-2026-30301", "R-9001", "D-3456", "Tan Boon Huat", "Marina Bay Sands", "Bugis Junction", D(2026, 9, 14, 23, 30), 12, 3.6, 11.50),
    clean_trip("TRIP-2026-30302", "R-9001", "D-4410", "Nur Aisyah", "Funan", "Suntec City", D(2026, 9, 21, 13, 10), 7, 1.9, 7.90),
    clean_trip("TRIP-2026-30303", "R-9001", "D-2398", "Lim Wei Ming", "Bugis Junction", "Paya Lebar Quarter", D(2026, 10, 5, 9, 0), 16, 5.8, 14.20),
    # R-3312 (DISP-004)
    clean_trip("TRIP-2026-30401", "R-3312", "D-6021", "Hafiz Rahman", "Changi Business Park", "Bedok Mall", D(2026, 9, 8, 18, 40), 15, 6.1, 12.30),
    clean_trip("TRIP-2026-30402", "R-3312", "D-7002", "Ong Kai Wen", "Kallang Wave Mall", "Orchard MRT", D(2026, 9, 19, 20, 15), 18, 7.4, 15.60),
    # R-5120 (DISP-005)
    clean_trip("TRIP-2026-30501", "R-5120", "D-1187", "Rajesh Kumar", "Tampines Mall", "Changi Airport T2", D(2026, 9, 20, 6, 10), 14, 7.0, 14.80),
    clean_trip("TRIP-2026-30502", "R-5120", "D-3456", "Tan Boon Huat", "Clarke Quay", "Bishan Junction 8", D(2026, 10, 3, 23, 40), 19, 10.2, 19.90),
    # R-7001 (DISP-006)
    clean_trip("TRIP-2026-30601", "R-7001", "D-2398", "Lim Wei Ming", "HarbourFront Centre", "Chinatown Point", D(2026, 9, 10, 11, 20), 13, 3.9, 9.40),
    clean_trip("TRIP-2026-30602", "R-7001", "D-4410", "Nur Aisyah", "Tanjong Pagar Centre", "Funan", D(2026, 9, 25, 8, 5), 9, 2.6, 8.10),
]

UNCLEAR = {"key": "unclear", "label_en": "Unclear story", "label_zh": "描述不清",
           "en": "Something went wrong with my last ride.", "zh": "我上一趟行程出了点问题。"}
ACCOUNTS = {
    "_source": "Synthetic",
    "_note": "Demo login accounts. Display names are invented for the demo (profiles carry no names); "
             "R-4521's name is the one in the official DISP-001 chat log. Stories are suggestions for the demo strip.",
    "riders": {
        "R-4521": {"name": "Sarah Tan", "stories": [
            {"key": "route_pick", "label_en": "Longer route (two trips fit)", "label_zh": "绕路（两趟都符合）",
             "en": "My driver took a much longer route than usual and I paid more than I should have.",
             "zh": "司机绕路了，走了更远的路线，我多付了钱。"},
            {"key": "route_one", "label_en": "Detour to Changi T3", "label_zh": "去樟宜机场绕路",
             "en": "The driver took a long detour on the way to Changi Airport T3 and never told me.",
             "zh": "去樟宜机场的路上司机绕路了，也没告诉我。"}, UNCLEAR]},
        "R-7823": {"name": "Daniel Lim", "stories": [
            {"key": "noshow_pick", "label_en": "No-show fee (two trips fit)", "label_zh": "爽约费（两趟都符合）",
             "en": "The driver never came and I was still charged a $5 cancellation fee.",
             "zh": "司机一直没来，我还被收了$5取消费。"},
            {"key": "no_match", "label_en": "Fare above quote (no such trip)", "label_zh": "车费高于报价（无此行程）",
             "en": "The fare was much higher than the upfront quote and nobody told me.",
             "zh": "车费比报价高很多，也没人通知我。"}, UNCLEAR]},
        "R-9001": {"name": "Priya Nair", "stories": [
            {"key": "fare_one", "label_en": "Fare above quote", "label_zh": "车费高于报价",
             "en": "I was charged $16.50 but the quote was $12.00, and nobody told me the price went up.",
             "zh": "报价是$12.00，结果收了我$16.50，没人告诉我涨价。"},
            {"key": "no_match", "label_en": "No-show fee (no such trip)", "label_zh": "爽约费（无此行程）",
             "en": "The driver never showed up and I got a $5 cancellation fee.",
             "zh": "司机没来，我却被收了$5取消费。"}, UNCLEAR]},
        "R-3312": {"name": "Wong Mei Ling", "stories": [
            {"key": "damage_one", "label_en": "Cleaning fee", "label_zh": "清洁费",
             "en": "I was charged a S$35 cleaning fee but I never spilled anything.",
             "zh": "我被收了S$35清洁费，但我根本没有弄脏车。"}, UNCLEAR]},
        "R-5120": {"name": "Ahmad Faiz", "stories": [
            {"key": "safety_one", "label_en": "Speeding driver", "label_zh": "司机超速",
             "en": "The driver was speeding over 100 km/h and shouted at me when I asked him to slow down.",
             "zh": "司机超速开到100 km/h以上，我让他开慢点他还吼我。"}, UNCLEAR]},
        "R-7001": {"name": "Chloe Ng", "stories": [
            {"key": "noshow_one", "label_en": "No-show fee", "label_zh": "爽约费",
             "en": "The app charged me a S$5 cancellation fee but I never saw the driver.",
             "zh": "App收了我S$5取消费，但我根本没看到司机。"}, UNCLEAR]},
    },
}

if __name__ == "__main__":
    (ROOT / "fixtures" / "trips_synthetic.json").write_text(
        json.dumps({"_source": "Synthetic", "_note": "Extra demo trips so each demo rider has 3 to 6 trips. Generated by "
                    "scripts/build_trips_synthetic.py.", "trips": TRIPS}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "fixtures" / "demo_accounts.json").write_text(json.dumps(ACCOUNTS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(TRIPS)} synthetic trips, {len(ACCOUNTS['riders'])} demo accounts")
