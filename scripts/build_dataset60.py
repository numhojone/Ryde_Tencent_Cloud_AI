#!/usr/bin/env python3
"""Build the RydeResolve 60-ticket dataset (DISP-101..DISP-160).

Deterministic (fixed seeds). Writes, to build/dataset60/ (or $DATASET60_OUT):
  official_format/   one full single-file JSON per dispute, in the organisers' DISP-001 layout
  app_fixtures/      the same cases split the way the app loads them (disputes/trips/profiles/expected/trip_parties)
  stories/stories.json   free-text stories for testing the story-to-ticket flow

What is real and what is synthetic:
  * rider ids and names, driver ids and names, dispute ids, trip ids, dispute types, rider-driver pairs:
    taken from the 60-ticket file the team received (re-mapped so each rider has >= 2 tickets in every category).
  * everything else (dates, places, GPS, chats, fares, photos, outcomes) is synthetic and generated here.
Expected outcomes are computed in expected_outcome(), straight from Policy v2.1 and the scenario parameters. They do not
call the app, so they can be used to test it.
"""
import json, math, os, random, shutil, sys
from datetime import date, datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))
# In this repo the script lives in scripts/, so it must not write next to it (that would overwrite the repo README
# and put official_format/, which holds the expected answers, at the top of the repo). It writes to build/dataset60/
# (git-ignored), or to DATASET60_OUT. Copy app_fixtures/ and stories/ into fixtures/ as the generated README says.
OUT = os.path.abspath(os.environ.get("DATASET60_OUT") or
                      os.path.join(os.path.dirname(__file__), "..", "build", "dataset60"))
AS_OF = datetime(2026, 10, 15, 22, 0, tzinfo=TZ)

# ------------------------------------------------------------------ people
RIDERS = [  # id, name, base profile (as of snapshot date), snapshot date
    ("R-3312", "Wong Mei Ling", dict(account_age_days=380, total_trips=96, avg_rating=4.8, dispute_history=dict(total_disputes=0, upheld=0, rejected=0), fraud_flags=0), date(2026, 9, 12)),
    ("R-4521", "Sarah Tan", dict(account_age_days=540, total_trips=187, avg_rating=4.8, dispute_history=dict(total_disputes=2, upheld=1, rejected=1, last_dispute_date="2026-07-10"), fraud_flags=0, payment_method="credit_card", payment_provider="Visa ending 4521", loyalty_tier="silver", frequent_corridors=["Orchard → Changi Airport", "CBD → Orchard"]), date(2026, 9, 12)),
    ("R-5120", "Ahmad Faiz", dict(account_age_days=300, total_trips=58, avg_rating=4.9, dispute_history=dict(total_disputes=0, upheld=0, rejected=0), fraud_flags=0), date(2026, 9, 15)),
    ("R-7001", "Chloe Ng", dict(account_age_days=10, total_trips=3, avg_rating=3.9, dispute_history=dict(total_disputes=2, upheld=0, rejected=2), fraud_flags=0), date(2026, 9, 17)),
    ("R-7823", "Daniel Lim", dict(account_age_days=210, total_trips=34, avg_rating=3.9, dispute_history=dict(total_disputes=4, upheld=1, rejected=3), fraud_flags=1, fraud_flag_details="flagged_for_frequent_late_cancellations", payment_method="e-wallet"), date(2026, 9, 13)),
    ("R-9001", "Priya Nair", dict(account_age_days=45, total_trips=7, avg_rating=4.5, dispute_history=dict(total_disputes=0, upheld=0, rejected=0), fraud_flags=0, payment_method="credit_card"), date(2026, 9, 14)),
]
DRIVERS = [
    ("D-1187", "Rajesh Kumar", "Toyota Vios (SHA 7823 K)", "Silver", dict(account_age_days=720, total_trips=2143, avg_rating=4.7, dispute_history=dict(total_disputes=3, upheld_against=1, rejected=2, last_dispute_date="2026-08-29"), fraud_flags=0, license_class="Class 3", partner_since="2024-09-23", recent_compliments=["Safe driver", "Punctual pickup"], completion_rate=0.97, cancellation_rate=0.03), date(2026, 9, 12)),
    ("D-2398", "Lim Wei Ming", "Honda HR-V (SGP 4521 M)", "White", dict(account_age_days=900, total_trips=3201, avg_rating=4.9, dispute_history=dict(total_disputes=1, upheld_against=0, rejected=1), fraud_flags=0), date(2026, 9, 13)),
    ("D-3456", "Tan Boon Huat", "Hyundai Elantra (SLM 8890 P)", "Grey", dict(account_age_days=450, total_trips=1567, avg_rating=4.8, dispute_history=dict(total_disputes=2, upheld_against=0, rejected=2), fraud_flags=0), date(2026, 9, 14)),
    ("D-4410", "Nur Aisyah", "Toyota Camry (SKB 2210 L)", "Black", dict(account_age_days=610, total_trips=1320, avg_rating=4.6, dispute_history=dict(total_disputes=4, upheld_against=1, rejected=3), fraud_flags=0), date(2026, 9, 12)),
    ("D-6021", "Hafiz Rahman", "Honda Fit (SKE 8832 Z)", "Blue", dict(account_age_days=150, total_trips=410, avg_rating=4.2, dispute_history=dict(total_disputes=3, upheld_against=1, rejected=2), fraud_flags=0), date(2026, 9, 15)),
    ("D-7002", "Ong Kai Wen", "Toyota Prius (SNX 4821 K)", "White", dict(account_age_days=500, total_trips=1800, avg_rating=4.7, dispute_history=dict(total_disputes=5, upheld_against=1, rejected=4), fraud_flags=0), date(2026, 9, 17)),
]
RID = {r[0]: r for r in RIDERS}
DID = {d[0]: d for d in DRIVERS}

# sample (non-dataset) disputes already in the app, per rider, so open_disputes counts are right
SAMPLE_OPEN = {"R-4521": 1, "R-7823": 1, "R-9001": 1, "R-3312": 1, "R-5120": 1, "R-7001": 1}

CATS = ["route_deviation", "no_show_charge", "property_damage", "safety_incident"]
# ------------------------------------------------------------------ places (approximate public coordinates)
PLACES = {
    "Orchard Central": (1.3010, 103.8398), "Tiong Bahru Plaza": (1.2847, 103.8274), "VivoCity": (1.2644, 103.8222),
    "Bugis Junction": (1.2993, 103.8555), "Marina Bay Sands": (1.2834, 103.8607), "Jurong East MRT": (1.3331, 103.7422),
    "Tampines Mall": (1.3525, 103.9447), "Raffles Place MRT": (1.2840, 103.8515), "HarbourFront Centre": (1.2653, 103.8220),
    "Clarke Quay": (1.2906, 103.8465), "Novena Square": (1.3203, 103.8438), "Bishan Junction 8": (1.3506, 103.8486),
    "Woodlands MRT": (1.4370, 103.7865), "Punggol Waterway Point": (1.4068, 103.9022), "Paya Lebar Quarter": (1.3176, 103.8927),
    "Holland Village": (1.3112, 103.7955), "Buona Vista MRT": (1.3070, 103.7905), "Changi Business Park": (1.3340, 103.9640),
    "Suntec City": (1.2956, 103.8585), "Gardens by the Bay": (1.2816, 103.8636), "NUS Kent Ridge": (1.2966, 103.7764),
    "Serangoon NEX": (1.3507, 103.8725), "Ang Mo Kio Hub": (1.3699, 103.8488), "Toa Payoh HDB Hub": (1.3326, 103.8474),
    "Bedok Mall": (1.3243, 103.9300), "Changi Airport T3": (1.3564, 103.9886), "one-north": (1.2993, 103.7873),
    "Kallang Wave Mall": (1.3028, 103.8742), "Great World": (1.2937, 103.8318), "Chinatown Point": (1.2851, 103.8440),
    "Resorts World Sentosa": (1.2554, 103.8200), "Yishun Northpoint": (1.4294, 103.8355), "Sengkang Compass One": (1.3919, 103.8951),
    "Pasir Ris Mall": (1.3722, 103.9494), "Clementi Mall": (1.3151, 103.7650), "Tanjong Pagar Centre": (1.2766, 103.8458),
    "Orchard MRT": (1.3040, 103.8318), "Lot One Choa Chu Kang": (1.3853, 103.7444), "Kovan Hub": (1.3600, 103.8850),
    "East Coast Park": (1.3010, 103.9120),
}
PNAMES = sorted(PLACES)
EXPRESSWAYS = [("PIE", "Pan-Island Expressway"), ("CTE", "Central Expressway"), ("ECP", "East Coast Parkway"),
               ("AYE", "Ayer Rajah Expressway"), ("KPE", "Kallang-Paya Lebar Expressway"), ("TPE", "Tampines Expressway"),
               ("BKE", "Bukit Timah Expressway")]
ALT_VIA = {"PIE": "ECP", "CTE": "KPE", "ECP": "PIE", "AYE": "PIE", "KPE": "CTE", "TPE": "PIE", "BKE": "CTE"}
INCIDENTS = [("vehicle_fire", "Vehicle fire", "high"), ("accident", "Multi-vehicle accident", "high"),
             ("road_works", "Emergency road works", "moderate"), ("heavy_congestion", "Heavy congestion after a stalled vehicle", "high"),
             ("flash_flood", "Flash flood reported on the slip road", "moderate")]


def hav_m(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = math.radians(b[0] - a[0]), math.radians(b[1] - a[1])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def mkpath(a, b, n, bulge_m=0.0, side=1):
    ym = (b[0] - a[0]) * 111320.0
    cl = math.cos(math.radians((a[0] + b[0]) / 2))
    xm = (b[1] - a[1]) * 111320.0 * cl
    L = math.hypot(xm, ym) or 1.0
    px, py = -ym / L * side, xm / L * side
    pts = []
    for i in range(n):
        t = i / (n - 1)
        off = bulge_m * math.sin(math.pi * t)
        pts.append((round(a[0] + (ym * t + py * off) / 111320.0, 5), round(a[1] + (xm * t + px * off) / (111320.0 * cl), 5)))
    return pts


def iso(dt):
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def money(x):
    return round(float(x) + 1e-9, 2)


def fdate(d):
    return f"{d.day} {d.strftime('%B')}"


# ------------------------------------------------------------------ case plan
# The ticket skeleton below is EXACTLY the team's 60-ticket file: dispute number, rider, driver and dispute type
# (R = route_deviation, N = no_show_charge, P = property_damage [cleaning_fee_dispute in the file], S = safety_incident).
SKELETON = """
101 R-3312 D-1187 R|102 R-3312 D-2398 R|103 R-3312 D-3456 N|104 R-3312 D-4410 N|105 R-3312 D-6021 P|106 R-3312 D-7002 P|107 R-3312 D-1187 S|108 R-3312 D-2398 S|109 R-3312 D-3456 R|110 R-3312 D-4410 N
111 R-4521 D-6021 R|112 R-4521 D-7002 R|113 R-4521 D-1187 N|114 R-4521 D-2398 N|115 R-4521 D-3456 P|116 R-4521 D-4410 P|117 R-4521 D-6021 S|118 R-4521 D-7002 S|119 R-4521 D-1187 P|120 R-4521 D-2398 N
121 R-5120 D-3456 R|122 R-5120 D-4410 R|123 R-5120 D-6021 N|124 R-5120 D-7002 N|125 R-5120 D-1187 P|126 R-5120 D-2398 P|127 R-5120 D-3456 S|128 R-5120 D-4410 S|129 R-5120 D-6021 P|130 R-5120 D-7002 S
131 R-7001 D-1187 R|132 R-7001 D-2398 R|133 R-7001 D-3456 N|134 R-7001 D-4410 N|135 R-7001 D-6021 P|136 R-7001 D-7002 P|137 R-7001 D-1187 S|138 R-7001 D-2398 S|139 R-7001 D-3456 R|140 R-7001 D-4410 N
141 R-7823 D-6021 R|142 R-7823 D-7002 R|143 R-7823 D-1187 N|144 R-7823 D-2398 N|145 R-7823 D-3456 P|146 R-7823 D-4410 P|147 R-7823 D-6021 S|148 R-7823 D-7002 S|149 R-7823 D-1187 P|150 R-7823 D-2398 S
151 R-9001 D-3456 R|152 R-9001 D-4410 R|153 R-9001 D-6021 N|154 R-9001 D-7002 N|155 R-9001 D-1187 P|156 R-9001 D-2398 P|157 R-9001 D-3456 S|158 R-9001 D-4410 S|159 R-9001 D-6021 R|160 R-9001 D-7002 S
"""
CODE = {"R": "route_deviation", "N": "no_show_charge", "P": "property_damage", "S": "safety_incident"}


def plan():
    """Return the ordered list of 60 case stubs (rider, category, scenario, driver, date) deterministically."""
    scen = {
        "route_deviation": ["within_tol"] * 2 + ["just_informed"] * 2 + ["just_late_inform", "just_noinform_small", "just_noinform_small",
                            "just_noinform_large", "just_noinform_large", "unjust_small", "unjust_small", "unjust_large", "unjust_large", "thin", "thin"],
        "no_show_charge": ["fee_valid"] * 3 + ["driver_late_contact"] * 2 + ["driver_late_nocontact"] * 2 + ["msg_only"] * 2 + ["call_only"] +
                          ["left_early"] * 2 + ["thin_gps", "thin_chat", "thin_events"],
        "property_damage": ["valid_cleaning"] * 3 + ["external_photo", "late_photo", "unlinked_photo", "claim_filed_late", "valid_small_fee",
                            "repair_with_quote", "repair_with_quote", "repair_no_quote", "no_photos", "valid_cleaning_max", "external_photo", "unlinked_photo"],
        "safety_incident": ["reckless_speeding", "reckless_speeding", "reckless_speeding", "harassment_chat", "harassment_chat", "harassment_chat",
                            "verbal_abuse", "verbal_abuse", "verbal_abuse", "collision", "collision", "distracted_driving", "distracted_driving",
                            "unsafe_detour_night", "suspected_intoxication"],
    }
    rr = random.Random(20261016)
    for k in scen:
        assert len(scen[k]) == 15, (k, len(scen[k]))
        rr.shuffle(scen[k])
    rows = [x for chunk in SKELETON.strip().split("\n") for x in chunk.split("|")]
    taken = {c: 0 for c in CATS}
    seen_in_block, cases = {}, []
    for row in rows:
        num, rid, drv, code = row.split()
        n = int(num) - 100
        cat = CODE[code]
        ri = [r[0] for r in RIDERS].index(rid)
        slot = seen_in_block.get(rid, 0); seen_in_block[rid] = slot + 1
        sc = scen[cat][taken[cat]]; taken[cat] += 1
        day = date(2026, 9, 18) + timedelta(days=int(slot * 2.7 + ri * 0.5))
        cases.append(dict(n=n, rider=rid, cat=cat, scen=sc, driver=drv, day=day, slot=slot))
    assert [c["n"] for c in cases] == list(range(1, 61))
    for rid in RID:
        for k in CATS:
            assert sum(1 for c in cases if c["rider"] == rid and c["cat"] == k) >= 2, (rid, k)   # every rider has 2+ tickets in every category
    for k in CATS:
        assert sum(1 for c in cases if c["cat"] == k) == 15
    return cases


# ------------------------------------------------------------------ helpers for text
def pick(rnd, seq):
    return seq[rnd.randrange(len(seq))]


def pair(rnd, lo_km, hi_km):
    while True:
        a, b = rnd.sample(PNAMES, 2)
        d = hav_m(PLACES[a], PLACES[b]) / 1000.0
        if lo_km <= d <= hi_km:
            return a, b, d


def msgs_pre_trip(rnd, drv, t0, rider_name, place):
    dn = DID[drv]
    first = pick(rnd, [f"Hi, I'm at {place} now, {dn[3].lower()} {dn[2].split(' (')[0]}, plate {dn[2].split('(')[1][:-1]}.",
                       f"Hello! Arrived at {place}. {dn[3]} {dn[2].split(' (')[0]}, plate {dn[2].split('(')[1][:-1]}."])
    return [("driver", dn[1], t0 - timedelta(minutes=2), first), ("rider", rider_name, t0 - timedelta(minutes=1), pick(rnd, ["Hi, coming now!", "Thanks, I see you.", "On my way, 1 min."]))]


def chat_entries(items):
    out = []
    for i, it in enumerate(items, 1):
        sender, name, ts, text = it[:4]
        typ = it[4] if len(it) > 4 else "message"
        e = {"message_id": f"MSG-{i:03d}", "sender": sender, "sender_name": name, "timestamp": iso(ts), "type": typ, "message": text}
        out.append(e)
    return out


ROUTE_KW = ("traffic", "jam", "congest", "reroute", "re-route", "alternate", "alternative", "detour", "diversion", "accident", "fire", "closure",
            "closed", "another route", "different route", "other route", "take pie", "take ecp", "avoid", "blocked", "erp")


def has_kw(txt):
    t = txt.lower()
    return any(k in t for k in ROUTE_KW)


# ================================================================== ROUTE DEVIATION
RATE = 0.80   # S$ per km (official DISP-001 dataset: "distance fare is calculated at $0.80/km")


def expected_route(dev, justified, informed):
    """Policy v2.1 section 1.3 refund matrix, computed directly from the scenario parameters."""
    excess = money(dev * RATE)
    if dev <= 1.0:
        return "rejected", 0.0, "1.3"
    if justified and informed:
        return "rejected", 0.0, "1.3"
    if justified:
        return "partial", excess, "1.3"
    return "upheld", excess, "1.3"


def build_route(c, rnd):
    rider, drv, sc, day = c["rider"], c["driver"], c["scen"], c["day"]
    rname, dn = RID[rider][1], DID[drv]
    a_name, b_name, straight = pair(rnd, 6, 21)
    A, B = PLACES[a_name], PLACES[b_name]
    est_km = round(straight * 1.28, 1)
    dev = {"within_tol": lambda: round(rnd.uniform(0.3, 0.9), 1), "just_informed": lambda: round(rnd.uniform(1.4, 3.6), 1),
           "just_late_inform": lambda: round(rnd.uniform(1.3, 1.9), 1), "just_noinform_small": lambda: round(rnd.uniform(1.2, 1.9), 1),
           "just_noinform_large": lambda: round(rnd.uniform(2.3, 4.8), 1), "unjust_small": lambda: round(rnd.uniform(1.2, 1.9), 1),
           "unjust_large": lambda: round(rnd.uniform(2.4, 5.5), 1), "thin": lambda: round(rnd.uniform(1.4, 3.0), 1)}[sc]()
    justified = sc.startswith("just_")
    informed = sc == "just_informed"
    thin = sc == "thin"
    start = datetime(day.year, day.month, day.day, rnd.randint(7, 21), rnd.choice(range(0, 60, 5)), tzinfo=TZ)
    est_min = max(12, round(est_km * 1.7))
    act_min = est_min + max(1, round(dev * 1.5 + rnd.uniform(-1, 2)))
    end = start + timedelta(minutes=act_min)
    tolls = rnd.choice([0.0, 1.2, 2.4, 3.6])
    est_fare = money(4.0 + 0.8 + est_km * RATE + est_min * 0.16 + tolls)
    ex_dist = money(dev * RATE)
    ex_toll = rnd.choice([0.0, 0.8, 1.6, 2.2]) if dev > 1 else 0.0
    ex_time = money((act_min - est_min) * 0.16)
    act_fare = money(est_fare + ex_dist + ex_toll + ex_time)
    tok, full = pick(rnd, EXPRESSWAYS)
    alt = ALT_VIA[tok]
    route_name = f"{tok} ({full}) — direct route"

    W = mkpath(A, B, 12, 250 * rnd.choice([1, -1]))
    waypoints = [{"point": i + 1, "lat": p[0], "lng": p[1],
                  "location_desc": f"{a_name} (pickup)" if i == 0 else (f"{b_name} (dropoff)" if i == 11 else f"{tok} segment {i}")} for i, p in enumerate(W)]
    optimal = {"route_name": route_name, "total_waypoints": 12, "estimated_distance_km": est_km, "estimated_duration_min": est_min,
               "waypoints": waypoints, "notes": f"System-recommended route via {tok}."}

    # GPS
    side = rnd.choice([1, -1])
    deviated = dev > 1.0
    H = min(3000, 1500 + 400 * dev)
    D = mkpath(A, B, 12, H, side) if deviated else None
    gps, dev_ts = [], None
    if thin:
        pts = [(W[0], start, 0), (W[-1], end, 0)]
        for i, (p, t, sp) in enumerate(pts):
            gps.append({"point": i + 1, "timestamp": iso(t), "lat": p[0], "lng": p[1], "speed_kmh": sp, "location_desc": "start" if i == 0 else "end"})
    else:
        for i in range(12):
            t = start + timedelta(seconds=int(act_min * 60 * i / 11))
            if deviated and 3 <= i <= 10:
                p = D[i]
            elif not deviated and 0 < i < 11:
                p = (round(W[i][0] + rnd.uniform(-0.0008, 0.0008), 5), round(W[i][1] + rnd.uniform(-0.0008, 0.0008), 5))
            else:
                p = W[i]
            sp = 0 if i in (0, 11) else rnd.choice([34, 38, 42, 48, 55, 62, 70])
            on_route = not (deviated and 3 <= i <= 10)
            gps.append({"point": i + 1, "timestamp": iso(t), "lat": p[0], "lng": p[1], "speed_kmh": sp,
                        "location_desc": (f"{a_name} (pickup)" if i == 0 else f"{b_name} (dropoff)" if i == 11 else
                                          (f"On recommended {tok} route" if on_route else "Off the recommended route"))})
            if dev_ts is None and min(hav_m(p, w) for w in W) > 1000:
                dev_ts = t
    if deviated and not thin:
        assert dev_ts is not None, (c["n"], "deviation never exceeds 1 km from the recommended route")
    dts = dev_ts or (start + timedelta(minutes=8))

    # traffic
    if justified:
        itype, idesc, sev = pick(rnd, INCIDENTS)
        t0 = start - timedelta(minutes=rnd.randint(8, 25))
        t1 = start + timedelta(minutes=rnd.randint(25, 70))
        traffic = [{"incident_id": "TC-001", "road": f"{tok} ({full})", "direction": "towards " + b_name, "stretch": f"{tok} between the pickup and {b_name}",
                    "incident_type": itype, "severity": sev, "timestamp": iso(t0), "clear_time": iso(t1),
                    "description": f"{idesc} on {tok}. Lanes blocked, long delays reported from {t0.strftime('%H:%M')}."},
                   {"incident_id": "TC-002", "road": f"{alt}", "direction": "towards " + b_name, "stretch": f"{alt} alternative corridor",
                    "incident_type": "traffic_flow", "severity": "low", "timestamp": iso(start), "clear_time": None,
                    "description": f"{alt} flowing smoothly. No incidents. An alternative through {alt} was reasonable."}]
    else:
        traffic = [{"incident_id": "TC-001", "road": f"{tok} ({full})", "direction": "towards " + b_name, "stretch": f"{tok} pickup to dropoff",
                    "incident_type": "traffic_flow", "severity": "low", "timestamp": iso(start - timedelta(minutes=10)), "clear_time": None,
                    "description": f"{tok} flowing normally during the trip window. No incidents reported."}]

    # chat
    ch = list(msgs_pre_trip(rnd, drv, start, rname, a_name))
    if thin:
        ch = [("driver", dn[1], start - timedelta(minutes=2), f"Hi, I'm at {a_name}.")]
    elif sc == "within_tol":
        ch.append(("rider", rname, end - timedelta(minutes=2), "Thanks, just dropping off here."))
    elif informed:
        ch.append(("driver", dn[1], dts - timedelta(seconds=40), f"Heads up, {idesc.lower()} on {tok}. I'll take {alt} instead to avoid the jam."))
        ch.append(("rider", rname, dts - timedelta(seconds=5), "OK, noted. Thanks for letting me know."))
    elif sc == "just_late_inform":
        ch.append(("rider", rname, dts + timedelta(minutes=2), "Why are we going this way? This doesn't look like the usual route."))
        ch.append(("driver", dn[1], dts + timedelta(minutes=3), "Don't worry, I know a quicker way."))
        ch.append(("driver", dn[1], dts + timedelta(minutes=7), f"Sorry, I should have said earlier. There was an accident ahead on {tok}, so I took another route."))
    else:
        ch.append(("rider", rname, dts + timedelta(minutes=rnd.randint(2, 4)), pick(rnd, ["Hey, are we going the right way? This doesn't look like the usual route.", "Why are we going this way? I normally take a different road.", "Is this the right way? The map looks different from what I expected."])))
        if rnd.random() < 0.75:
            ch.append(("driver", dn[1], dts + timedelta(minutes=5), pick(rnd, ["Don't worry, I know the way.", "Relax, this way is faster.", "Trust me, I drive here every day."])))
    chat = chat_entries(ch)
    for m in chat:   # keyword hygiene: only the intended notification messages may contain route keywords
        if m["sender"] == "driver":
            is_notice = (informed and "Heads up" in m["message"]) or (sc == "just_late_inform" and "Sorry, I should have said" in m["message"])
            assert has_kw(m["message"]) == is_notice, (c["n"], m["message"])

    events = [{"timestamp": iso(start - timedelta(minutes=9)), "event_type": "driver_assigned", "details": f"Driver {drv} assigned."},
              {"timestamp": iso(start), "event_type": "trip_started", "details": f"Trip started at {a_name}."},
              {"timestamp": iso(end), "event_type": "trip_ended", "details": f"Trip ended at {b_name}. Fare S${act_fare:.2f} charged."}]
    if thin:
        events = events[:1] + events[2:]

    fare_breakdown = {"estimated": {"total": est_fare}, "actual": {"total": act_fare}, "delta": {"total": money(act_fare - est_fare)},
                      "excess_distance_fare": ex_dist, "excess_tolls": ex_toll, "excess_time_fare": ex_time, "distance_rate_per_km": RATE}
    trip_data = {"trip_id": c["trip_id"], "rider_id": rider, "driver_id": drv,
                 "pickup_location": {"name": a_name, "address": f"{a_name}, Singapore", "lat": A[0], "lng": A[1]},
                 "dropoff_location": {"name": b_name, "address": f"{b_name}, Singapore", "lat": B[0], "lng": B[1]},
                 "start_time": iso(start), "end_time": iso(end), "estimated_duration_min": est_min, "actual_duration_min": act_min,
                 "estimated_distance_km": est_km, "actual_distance_km": round(est_km + dev, 1), "estimated_fare": est_fare, "actual_fare": act_fare,
                 "excess_distance_km": dev, "excess_fare": money(act_fare - est_fare), "route_deviated": dev > 0.0, "weather": rnd.choice(["clear", "partly_cloudy", "light_rain"]),
                 "trip_type": "standard", "status": "completed", "currency": "SGD"}

    # description
    note = {"within_tol": "It felt a bit longer than usual and the fare was higher than the estimate.",
            "just_informed": "The driver messaged about traffic, but I still think the extra charge is unfair.",
            "just_late_inform": "The driver only explained the route change much later, after I asked.",
            }.get(sc, rnd.choice(["The driver did not tell me about any route change or the reason.", "I asked about the route and did not get a proper explanation.", "Nobody told me why we left the normal route."]))
    desc = (f"On {fdate(day)} I took a Ryde from {a_name} to {b_name}. The upfront estimate was about S${est_fare:.2f} but I was charged S${act_fare:.2f}. "
            f"The trip was about {dev:.1f} km longer than the recommended route. {note} I am requesting a refund of the excess fare.")
    if sc == "thin":
        outcome = ("escalated", None, "safety_net")
        must = True
    else:
        lab, amt, cl = expected_route(dev, justified, informed)
        outcome, must = (lab, amt, cl), dev > 2.0
    ts_filed = end + timedelta(minutes=rnd.randint(25, 200))
    exp = dict(ruling=outcome[0], refund_amount=outcome[1], clause=outcome[2], must_escalate=bool(must or thin),
               must_escalate_reason=(["deviation_over_2km"] if dev > 2 and not thin else []) + (["thin_evidence"] if thin else []),
               facts=dict(deviation_km=dev, traffic_justified=justified, rider_informed=informed, excess_distance_fare=ex_dist))
    wait = None
    return dict(
        trip_data=trip_data, gps=gps, chat=chat, events=events, extra=dict(fare_breakdown=fare_breakdown, optimal_route=optimal, traffic_conditions=traffic),
        description=desc, requested_resolution="refund_excess_fare", requested_amount=money(act_fare - est_fare), filed_at=ts_filed, expected=exp,
        route_text=f"{a_name} → {b_name}", outcome_text=f"Trip completed, fare S${act_fare:.2f} (quote S${est_fare:.2f})",
        story=dict(a=a_name, b=b_name, day=day, est=est_fare, act=act_fare, dev=dev),
        official_extra=dict(
            traffic_analysis=dict(reroute_justified=justified, notification_failure=(justified and not informed), alternative_route_via=alt,
                                  policy_reference="Ryde Dispute Resolution Policy v2.1 section 1.2 to 1.4"),
            chat_log_analysis=dict(total_messages=len(chat), route_notification_sent=informed, rider_inquired_about_route=any("way" in m["message"].lower() or "route" in m["message"].lower() for m in chat if m["sender"] == "rider")),
        ),
        evidence=[("gps_telemetry", f"GPS trail {'follows' if not deviated else 'leaves'} the recommended route", "driver" if not deviated else "rider"),
                  ("fare_comparison", f"Actual fare S${act_fare:.2f} vs estimate S${est_fare:.2f}", "rider"),
                  ("distance_comparison", f"Actual {est_km + dev:.1f} km vs recommended {est_km} km (+{dev:.1f} km)", "rider" if dev > 1 else "driver"),
                  ("traffic_report", ("Incident on the recommended route at trip start" if justified else "No incident on the recommended route"), "driver" if justified else "rider"),
                  ("chat_logs", ("Driver notified the rider of the reroute" if informed else "No timely route-change notification in chat"), "driver" if informed else "rider"),
                  ("driver_history", f"Driver rating {dn[4]['avg_rating']}, {dn[4]['total_trips']} trips, no fraud flags", "driver")],
    )


# ================================================================== NO-SHOW
def build_noshow(c, rnd):
    rider, drv, sc, day = c["rider"], c["driver"], c["scen"], c["day"]
    rname, dn = RID[rider][1], DID[drv]
    p_name, d_name, _ = pair(rnd, 3, 16)
    P, Dst = PLACES[p_name], PLACES[d_name]
    T = datetime(day.year, day.month, day.day, rnd.randint(6, 22), rnd.choice(range(0, 60, 5)), tzinfo=TZ)
    booked = T - timedelta(minutes=rnd.randint(20, 35))
    O = (round(P[0] + rnd.choice([0.011, -0.012]), 5), round(P[1] + rnd.choice([0.010, -0.011]), 5))
    thin = sc.startswith("thin")
    M = lambda mins: T + timedelta(seconds=int(mins * 60))
    arrive_m = {"fee_valid": rnd.uniform(-4, 3), "driver_late_contact": rnd.uniform(7, 12), "driver_late_nocontact": rnd.uniform(7, 12),
                "msg_only": rnd.uniform(-3, 2), "call_only": rnd.uniform(-3, 2), "left_early": rnd.uniform(-2, 1),
                "thin_gps": 1.0, "thin_chat": rnd.uniform(-3, 2), "thin_events": rnd.uniform(-3, 2)}[sc]
    arrive_m = round(arrive_m * 2) / 2
    cancel_m = {"fee_valid": rnd.uniform(6, 9), "driver_late_contact": arrive_m + rnd.uniform(3, 5), "driver_late_nocontact": arrive_m + rnd.uniform(2, 4),
                "msg_only": rnd.uniform(6, 9), "call_only": rnd.uniform(6, 9), "left_early": rnd.uniform(2.2, 4.2),
                "thin_gps": rnd.uniform(6, 9), "thin_chat": rnd.uniform(6, 9), "thin_events": rnd.uniform(6, 9)}[sc]
    cancel_m = round(cancel_m * 2) / 2
    arrive, cancel = M(arrive_m), M(cancel_m)

    gps = []
    if sc == "thin_gps":
        for i, (mins, f, sp) in enumerate([(-6, 0.45, 18), (-3, 0.18, 12)]):
            p = (round(O[0] + (P[0] - O[0]) * (1 - f) + 0.0001, 5), round(O[1] + (P[1] - O[1]) * (1 - f) + 0.0001, 5))
            gps.append({"timestamp": iso(M(mins)), "lat": p[0], "lng": p[1], "speed_kmh": sp, "status": "en_route"})
    else:
        app = mkpath(O, P, 5)
        for i, (dm, sp) in enumerate([(-13, 40), (-9, 36), (-5, 30), (-2, 14)]):
            tm = arrive_m + dm
            gps.append({"timestamp": iso(M(tm)), "lat": app[i][0], "lng": app[i][1], "speed_kmh": sp, "status": "en_route"})
        gps.append({"timestamp": iso(arrive), "lat": P[0], "lng": P[1], "speed_kmh": 0, "status": "arrived"})
        t = arrive_m + 2.0
        while t < cancel_m - 0.01:
            gps.append({"timestamp": iso(M(t)), "lat": P[0], "lng": P[1], "speed_kmh": 0, "status": "waiting"})
            t += 2.0
        gps.append({"timestamp": iso(cancel), "lat": P[0], "lng": P[1], "speed_kmh": 0, "status": "cancelled"})

    plate = dn[2].split("(")[1][:-1]
    car = f"{dn[3]} {dn[2].split(' (')[0]}"
    items = []
    def drv_msg(mins, text): items.append(("driver", dn[1], M(mins), text, "message"))
    def drv_call(mins, text): items.append(("driver", dn[1], M(mins), text, "call"))
    def rid_msg(mins, text): items.append(("rider", rname, M(mins), text, "message"))
    called = False
    if sc == "fee_valid":
        drv_msg(arrive_m + 0.5, f"I've arrived at {p_name}, waiting at the pickup point. {car}, plate {plate}.")
        drv_call(arrive_m + 3.0, "Outgoing call to rider — not answered (rang 22s, no response).")
        drv_msg(cancel_m - 1.0, "Are you coming down? I've been waiting. Please let me know or I will have to cancel.")
        rid_msg(cancel_m + rnd.randint(6, 14), "I was at the entrance the whole time! Why was I charged?"); called = True
    elif sc == "driver_late_contact":
        rid_msg(0.5, f"I'm at {p_name} now, waiting at the main entrance.")
        drv_msg(arrive_m + 0.5, f"Sorry I'm late, just arrived at {p_name}. {car}, plate {plate}.")
        drv_call(arrive_m + 1.5, "Outgoing call to rider — not answered.")
        rid_msg(cancel_m + 6, "I waited 10 minutes and had to leave. Why is there a fee?"); called = True
    elif sc == "driver_late_nocontact":
        rid_msg(3.0, f"Where are you? I'm at the entrance of {p_name}.")
        rid_msg(8.0, "Driver, are you still coming? The map shows you are not here.")
    elif sc == "msg_only":
        drv_msg(arrive_m + 0.5, f"Hi, I'm at {p_name}, waiting at the drop-off bay. {car}, plate {plate}.")
        drv_msg(cancel_m - 1.5, "I've waited quite a while. Are you coming? I'll need to cancel soon.")
        rid_msg(cancel_m + 7, "My phone was on silent. You didn't call me before cancelling!")
    elif sc == "call_only":
        drv_call(arrive_m + 3.5, "Outgoing call to rider — not answered (rang 18s, no response).")
        rid_msg(arrive_m + 4.5, "Sorry, still in the lift, give me 2 minutes!")
        called = True
    elif sc == "left_early":
        drv_msg(arrive_m + 0.5, f"Arrived at {p_name}. {car}, plate {plate}.")
        drv_call(arrive_m + 1.5, "Outgoing call to rider — not answered.")
        rid_msg(cancel_m + 3, "I only just got downstairs and you already cancelled?!"); called = True
    elif sc == "thin_gps":
        pass
    elif sc == "thin_chat":
        drv_msg(arrive_m + 0.5, f"I've arrived at {p_name}.")
    elif sc == "thin_events":
        drv_msg(arrive_m + 0.5, f"I've arrived at {p_name}, waiting.")
        rid_msg(cancel_m + 5, "I was there! Please remove the fee.")
    items.sort(key=lambda x: x[2])
    chat = chat_entries(items)

    ev = [{"timestamp": iso(booked), "event_type": "booking_confirmed", "details": f"Rider {rider} booked from {p_name} to {d_name}. Scheduled pickup {T.strftime('%H:%M')}."},
          {"timestamp": iso(booked + timedelta(seconds=15)), "event_type": "driver_assigned", "details": f"Driver {drv} ({dn[1]}, {dn[2]}) assigned."},
          {"timestamp": iso(booked + timedelta(seconds=20)), "event_type": "driver_en_route", "details": "Driver started navigating to the pickup location."},
          {"timestamp": iso(arrive), "event_type": "driver_arrived", "details": ("System marked the driver as arrived (location about 420 m from the pickup point)." if sc == "thin_gps" else "Driver GPS within 10 m of the pickup point. Auto-arrival confirmed.")},
          {"timestamp": iso(arrive + timedelta(seconds=5)), "event_type": "rider_notified", "details": "Push notification sent to rider: 'Your driver has arrived.'"},
          {"timestamp": iso(arrive + timedelta(seconds=10)), "event_type": "wait_timer_started", "details": "Free wait timer started (5 minutes)."}]
    if sc in ("fee_valid", "left_early", "call_only", "driver_late_contact"):
        ev.append({"timestamp": iso(M(arrive_m + (3.0 if sc in ("fee_valid", "call_only") else 1.5))), "event_type": "driver_called_rider", "details": "Driver initiated an in-app call to the rider. No answer."})
    ev.append({"timestamp": iso(M(5.0)), "event_type": "wait_timer_expired", "details": "Free 5-minute wait counted from the scheduled pickup time ended."})
    ev.append({"timestamp": iso(cancel), "event_type": "cancellation_fee_charged", "details": "S$5.00 no-show cancellation fee charged to the rider."})
    if sc == "thin_events":
        ev = [ev[-1]]
    ev.sort(key=lambda e: e["timestamp"])
    if sc == "left_early":
        ev = [e for e in ev if e["event_type"] != "wait_timer_expired"]

    trip_data = {"trip_id": c["trip_id"], "rider_id": rider, "driver_id": drv,
                 "pickup_location": {"name": p_name, "address": f"{p_name}, Singapore", "lat": P[0], "lng": P[1]},
                 "dropoff_location": {"name": d_name, "address": f"{d_name}, Singapore", "lat": Dst[0], "lng": Dst[1]},
                 "scheduled_time": iso(T), "driver_arrival_time": iso(arrive), "driver_wait_start": iso(arrive), "cancellation_time": iso(cancel),
                 "cancellation_fee": 5.0, "cancellation_reason": "rider_no_show", "status": "cancelled_no_show_rider", "currency": "SGD"}

    # expected (independent of the app): policy 2.1 to 2.4
    contact_msgs = {"fee_valid": 2, "driver_late_contact": 1, "driver_late_nocontact": 0, "msg_only": 2, "call_only": 0, "left_early": 1, "thin_gps": 0, "thin_chat": 1, "thin_events": 1}[sc]
    contact_calls = 1 if sc in ("fee_valid", "driver_late_contact", "call_only", "left_early") else 0
    goodwill = 0.0
    if thin:
        lab, amt, cl = "escalated", None, "safety_net"
    elif arrive_m > 5.0:
        lab, amt, cl = "upheld", 5.0, "2.4"
        goodwill = 5.0 if (contact_msgs == 0 and contact_calls == 0) else 0.0
    elif cancel_m < 5.0:
        lab, amt, cl = "upheld", 5.0, "2.1"
    elif contact_msgs < 1 or contact_calls < 1:
        lab, amt, cl = "upheld", 5.0, "2.3"
    else:
        lab, amt, cl = "rejected", 0.0, "2.2"
    exp = dict(ruling=lab, refund_amount=amt, clause=cl, goodwill_credit=goodwill, must_escalate=thin, must_escalate_reason=["thin_evidence"] if thin else [],
               facts=dict(arrival_minutes_after_schedule=arrive_m, cancel_minutes_after_schedule=cancel_m, driver_messages=contact_msgs, driver_calls=contact_calls))

    desc = {
        "fee_valid": f"I was waiting at the entrance of {p_name} on {fdate(day)} for my {T.strftime('%H:%M')} booking, but the driver cancelled and charged me a S$5 no-show fee. I never got a call from the driver. Please refund the fee.",
        "driver_late_contact": f"My driver arrived at {p_name} very late on {fdate(day)} (the booking was for {T.strftime('%H:%M')}). I waited and then had to leave, and now I'm charged a S$5 no-show fee. Please reverse it.",
        "driver_late_nocontact": f"The driver never showed up at {p_name} on {fdate(day)} for my {T.strftime('%H:%M')} pickup and never contacted me, but I was still charged a S$5 cancellation fee. I want the fee refunded.",
        "msg_only": f"I was charged a S$5 no-show fee for my {T.strftime('%H:%M')} booking at {p_name} on {fdate(day)}. The driver only sent chat messages and did not call me. Please refund the fee.",
        "call_only": f"The driver called once and then cancelled my {T.strftime('%H:%M')} pickup at {p_name} on {fdate(day)}. I was still on my way down and was charged S$5. Please refund it.",
        "left_early": f"The driver cancelled my {p_name} pickup on {fdate(day)} only a few minutes after the scheduled time, before I even got downstairs, and charged me S$5. This does not seem fair.",
        "thin_gps": f"I was at {p_name} on {fdate(day)} at {T.strftime('%H:%M')} and the driver was nowhere near the pickup point, yet I was charged a S$5 no-show fee. Please check and refund.",
        "thin_chat": f"I was charged a S$5 no-show fee at {p_name} on {fdate(day)}. The driver barely contacted me. Please look into it.",
        "thin_events": f"On {fdate(day)} my {p_name} booking was cancelled as a no-show and I paid S$5. I was there. Please review.",
    }[sc]
    wait = dict(scheduled=iso(T), driver_arrival=iso(arrive), cancelled_at=iso(cancel), arrival_minutes_vs_schedule=arrive_m, driver_messages=contact_msgs, driver_calls=contact_calls)
    return dict(trip_data=trip_data, gps=gps, chat=chat, events=ev, extra={}, description=desc, requested_resolution="reverse_cancellation_fee",
                requested_amount=5.0, filed_at=cancel + timedelta(minutes=rnd.randint(8, 120)), expected=exp,
                route_text=f"{p_name} → {d_name}", outcome_text="Trip cancelled, S$5 no-show fee charged",
                story=dict(a=p_name, b=d_name, day=day, time=T.strftime("%H:%M")),
                official_extra=dict(wait_analysis=wait),
                evidence=[("gps_telemetry", "Driver GPS around the pickup point" if not sc == "thin_gps" else "GPS shows only 2 en-route points", "driver" if not sc.startswith("driver_late") else "rider"),
                          ("app_events", "Wait timer and fee events recorded", "driver"),
                          ("chat_logs", f"{contact_msgs} driver message(s), {contact_calls} call(s)", "driver" if contact_msgs and contact_calls else "rider"),
                          ("driver_history", f"Driver rating {dn[4]['avg_rating']}, {dn[4]['total_trips']} trips", "driver")])


# ================================================================== PROPERTY DAMAGE / CLEANING
CLEAN_CAP = 50.0
WORKSHOPS = ["Kaki Bukit Auto Care", "Ubi Motor Works", "Woodlands Panel & Paint", "Tuas Certified Repairs"]
STAINS = ["a coffee spill on the rear seat", "a stain on the seat", "vomit on the floor mat", "a sticky drink spill on the door panel", "mud on the back seat"]


def expected_damage(claim_type, amount, fee, photo_ok, in_time, has_quote):
    """Policy 4.2 to 4.4: unsupported claim is reversed; valid cleaning claim (<= S$50) stands; repair claims need a quote and a human."""
    if claim_type == "repair":
        valid = has_quote and in_time
    else:
        valid = photo_ok and in_time and amount <= CLEAN_CAP
    return ("rejected", 0.0, "4.2") if valid else ("upheld", money(fee), "4.4")


def build_property(c, rnd):
    rider, drv, sc, day = c["rider"], c["driver"], c["scen"], c["day"]
    rname, dn = RID[rider][1], DID[drv]
    a_name, b_name, straight = pair(rnd, 3, 20)
    A, B = PLACES[a_name], PLACES[b_name]
    km = round(straight * 1.3, 1)
    start = datetime(day.year, day.month, day.day, rnd.choice([7, 8, 12, 18, 20, 21, 22, 23]), rnd.choice(range(0, 60, 5)), tzinfo=TZ)
    dur = max(10, round(km * 1.8))
    end = start + timedelta(minutes=dur)
    fare = money(4.8 + km * RATE + dur * 0.16)
    repair = sc.startswith("repair")
    stain = pick(rnd, STAINS)
    amount = {"valid_cleaning": rnd.choice([18, 22, 25, 28, 30, 35, 40, 45]), "valid_cleaning_max": 50, "valid_small_fee": rnd.choice([8, 9]),
              "external_photo": rnd.choice([20, 25, 30, 35]), "late_photo": rnd.choice([25, 30, 40]), "unlinked_photo": rnd.choice([20, 30, 45]),
              "claim_filed_late": rnd.choice([25, 35]), "no_photos": rnd.choice([20, 30]),
              "repair_with_quote": rnd.choice([120, 160, 240, 320]), "repair_no_quote": rnd.choice([140, 180, 260])}[sc]
    amount = float(amount)

    def photo(pid, taken, source="in_app_camera", stamped=True, linked=True, desc="Rear seat"):
        return {"photo_id": pid, "taken_at": iso(taken), "source": source, "timestamped_by_app_camera": stamped, "linked_to_trip": linked, "description": desc}

    in_time_photo = lambda: end + timedelta(minutes=rnd.randint(10, 70))
    filed = end + timedelta(hours=rnd.randint(2, 9), minutes=rnd.randint(0, 50))
    photos, quote = [], None
    if sc in ("valid_cleaning", "valid_cleaning_max", "valid_small_fee"):
        photos = [photo("PH-1", in_time_photo(), desc=stain.capitalize())] + ([photo("PH-2", in_time_photo() + timedelta(minutes=2), desc="Close-up")] if rnd.random() < 0.5 else [])
    elif sc == "external_photo":
        t = end + timedelta(hours=rnd.randint(3, 12))
        photos = [photo("PH-1", t, "external_upload", False, False, stain.capitalize())]
        filed = t + timedelta(hours=rnd.randint(1, 3))
    elif sc == "late_photo":
        t = end + timedelta(hours=rnd.randint(28, 40)); photos = [photo("PH-1", t, desc=stain.capitalize())]; filed = t + timedelta(hours=1)
    elif sc == "unlinked_photo":
        photos = [photo("PH-1", in_time_photo(), "in_app_camera", True, False, stain.capitalize())]
    elif sc == "claim_filed_late":
        photos = [photo("PH-1", in_time_photo(), desc=stain.capitalize())]; filed = end + timedelta(hours=rnd.randint(26, 34))
    elif sc in ("repair_with_quote", "repair_no_quote"):
        photos = [photo("PH-1", in_time_photo(), desc="Scratch and dent on the rear door panel"), photo("PH-2", in_time_photo() + timedelta(minutes=3), desc="Interior trim damage")]
        if sc == "repair_with_quote":
            quote = {"workshop": pick(rnd, WORKSHOPS), "certified": True, "amount": amount, "submitted_at": iso(end + timedelta(days=rnd.randint(2, 5)))}
    charged_at = filed + timedelta(minutes=rnd.randint(1, 3))
    photo_ok = any(p["source"] == "in_app_camera" and p["timestamped_by_app_camera"] and p["linked_to_trip"] and
                   datetime.fromisoformat(p["taken_at"]) <= end + timedelta(hours=24) for p in photos)
    in_time = filed <= end + timedelta(hours=24)
    ctype = "repair" if repair else "cleaning"
    if sc == "no_photos":
        lab, amt, cl = "escalated", None, "safety_net"
    else:
        lab, amt, cl = expected_damage(ctype, amount, amount, photo_ok, in_time, quote is not None)
    must = repair or sc == "no_photos"
    reasons = (["repair_claim"] if repair else []) + (["thin_evidence"] if sc == "no_photos" else [])

    gps = []
    path = mkpath(A, B, 7, 200)
    for i, p in enumerate(path):
        gps.append({"timestamp": iso(start + timedelta(seconds=int(dur * 60 * i / 6))), "lat": p[0], "lng": p[1],
                    "speed_kmh": 0 if i in (0, 6) else rnd.choice([35, 42, 50, 58, 64])})
    ch = list(msgs_pre_trip(rnd, drv, start, rname, a_name))
    ch.append(("rider", rname, charged_at + timedelta(minutes=rnd.randint(40, 120)),
               pick(rnd, [f"Why was I charged S${amount:.0f} for {'repairs' if repair else 'cleaning'}? I did not damage anything.", f"I just saw a S${amount:.0f} {'damage' if repair else 'cleaning'} fee. Please explain.", "Nobody told me anything about a problem in the car."])))
    chat = chat_entries(ch)
    fee_key = "damage_fee_charged" if repair else "cleaning_fee_charged"
    trip_data = {"trip_id": c["trip_id"], "rider_id": rider, "driver_id": drv,
                 "pickup_location": {"name": a_name, "address": f"{a_name}, Singapore", "lat": A[0], "lng": A[1]},
                 "dropoff_location": {"name": b_name, "address": f"{b_name}, Singapore", "lat": B[0], "lng": B[1]},
                 "start_time": iso(start), "end_time": iso(end), "actual_distance_km": km, "status": "completed", "currency": "SGD",
                 "fare_charged": fare, fee_key: amount}
    ev = [{"timestamp": iso(start), "event_type": "trip_started", "details": f"Trip started at {a_name}."},
          {"timestamp": iso(end), "event_type": "trip_ended", "details": "Trip completed."},
          {"timestamp": iso(filed), "event_type": "damage_claim_filed", "details": f"Driver filed {ctype} claim S${amount:.2f}."},
          {"timestamp": iso(charged_at), "event_type": f"{'damage' if repair else 'cleaning'}_fee_charged", "details": f"S${amount:.2f} {ctype} fee charged to rider."}]
    dmg = {"claim_type": ctype, "claimed_amount": amount, "claim_filed_at": iso(filed), "photos": photos, "repair_quote": quote}
    desc = {
        "valid_cleaning": f"I was charged a S${amount:.0f} cleaning fee after my ride from {a_name} to {b_name} on {fdate(day)}. At most there was a small spill. I think this is too much. Please reverse the fee.",
        "valid_cleaning_max": f"I was charged the maximum S$50 cleaning fee after my trip from {a_name} to {b_name} on {fdate(day)}. The car was not that dirty. Please reverse it.",
        "valid_small_fee": f"A S${amount:.0f} cleaning fee appeared after my {fdate(day)} trip from {a_name} to {b_name}. I don't think I made any mess. Please remove it.",
        "external_photo": f"I was charged a S${amount:.0f} cleaning fee for my {fdate(day)} trip ({a_name} to {b_name}). I did not spill or dirty anything and the driver never mentioned it. Please reverse the charge.",
        "late_photo": f"A S${amount:.0f} cleaning fee was added more than a day after my trip from {a_name} to {b_name} on {fdate(day)}. I did not make any mess. Please reverse it.",
        "unlinked_photo": f"I was charged S${amount:.0f} for cleaning after riding from {a_name} to {b_name} on {fdate(day)}. The photo the driver sent doesn't look like my ride. Please reverse the fee.",
        "claim_filed_late": f"The driver claimed a S${amount:.0f} cleaning fee more than a day after my {fdate(day)} trip from {a_name} to {b_name}. This feels too late to be valid. Please reverse it.",
        "no_photos": f"I was charged a S${amount:.0f} cleaning fee after my {fdate(day)} ride from {a_name} to {b_name} with no photos or explanation at all. Please reverse the charge.",
        "repair_with_quote": f"The driver is claiming S${amount:.0f} for damage to the car after my {fdate(day)} ride from {a_name} to {b_name}. I did not damage anything. I am disputing the charge.",
        "repair_no_quote": f"I was charged S${amount:.0f} for car damage after my trip from {a_name} to {b_name} on {fdate(day)}, but I was never shown a quote or any proof. I am disputing it.",
    }[sc]
    return dict(trip_data=trip_data, gps=gps, chat=chat, events=ev, extra=dict(damage_evidence=dmg), description=desc,
                requested_resolution="reverse_damage_fee" if repair else "reverse_cleaning_fee", requested_amount=amount, filed_at=charged_at + timedelta(hours=rnd.randint(1, 4)),
                expected=dict(ruling=lab, refund_amount=amt, clause=cl, must_escalate=must, must_escalate_reason=reasons,
                              facts=dict(claim_type=ctype, claimed_amount=amount, verifiable_photo=photo_ok, claim_in_24h=in_time, repair_quote=quote is not None)),
                route_text=f"{a_name} → {b_name}", outcome_text=f"Trip completed, S${amount:.0f} {'damage' if repair else 'cleaning'} fee charged",
                story=dict(a=a_name, b=b_name, day=day, amount=amount, repair=repair),
                official_extra=dict(photo_review=[dict(photo_id=p["photo_id"], in_app_camera=p["source"] == "in_app_camera", linked_to_trip=p["linked_to_trip"],
                                                      within_24h=datetime.fromisoformat(p["taken_at"]) <= end + timedelta(hours=24)) for p in photos]),
                evidence=[("damage_evidence", f"{len(photos)} photo(s); {'verifiable in-app photo present' if photo_ok else 'no verifiable photo'}", "driver" if photo_ok else "rider"),
                          ("claim_timing", f"Claim filed {'within' if in_time else 'after'} 24h of trip end", "driver" if in_time else "rider"),
                          ("chat_logs", "Rider disputed the charge in chat", "rider"),
                          ("driver_history", f"Driver rating {dn[4]['avg_rating']}, {dn[4]['total_trips']} trips", "driver")])


# ================================================================== SAFETY
def build_safety(c, rnd):
    rider, drv, sc, day = c["rider"], c["driver"], c["scen"], c["day"]
    rname, dn = RID[rider][1], DID[drv]
    a_name, b_name, straight = pair(rnd, 5, 18)
    A, B = PLACES[a_name], PLACES[b_name]
    km = round(straight * 1.3, 1)
    hour = rnd.choice([23, 0, 1, 22]) if sc == "unsafe_detour_night" else rnd.choice([8, 13, 18, 20, 21, 22])
    start = datetime(day.year, day.month, day.day, hour, rnd.choice(range(0, 60, 5)), tzinfo=TZ)
    dur = max(12, round(km * 1.7))
    end = start + timedelta(minutes=dur)
    fare = money(4.8 + km * RATE + dur * 0.16)
    N = 9
    path = mkpath(A, B, N, 2200 if sc == "unsafe_detour_night" else 200)
    speeds = [0] + [rnd.choice([38, 44, 52, 58, 64]) for _ in range(N - 2)] + [0]
    ev = [{"timestamp": iso(start), "event_type": "trip_started", "details": f"Trip started at {a_name}."}]
    ch = list(msgs_pre_trip(rnd, drv, start, rname, a_name))
    T = lambda f: start + timedelta(seconds=int(dur * 60 * f))
    if sc == "reckless_speeding":
        for i in (3, 4, 5):
            speeds[i] = rnd.choice([98, 104, 112, 121])
        ev += [{"timestamp": iso(T(0.40)), "event_type": "speeding_alert", "details": f"Speed {speeds[3]} km/h in an 80 km/h zone."},
               {"timestamp": iso(T(0.55)), "event_type": "speeding_alert", "details": f"Speed {speeds[5]} km/h in an 80 km/h zone."},
               {"timestamp": iso(T(0.50)), "event_type": "harsh_braking_alert", "details": "Harsh braking event detected."}]
        ch += [("rider", rname, T(0.42), "Please slow down, we're going really fast."), ("driver", dn[1], T(0.43), "Relax lah, I know what I'm doing.")]
        desc = f"On {fdate(day)} my driver from {a_name} to {b_name} was speeding on the expressway, weaving between lanes and braking hard. I asked him to slow down and he ignored me. I felt very unsafe."
        cat, sev = "reckless_driving", "high"
    elif sc == "harassment_chat":
        ch += [("driver", dn[1], T(0.30), "Can I have your number? You seem very nice."), ("rider", rname, T(0.32), "No thanks. Please just drive."),
               ("driver", dn[1], T(0.45), "Where do you stay? I can fetch you again next time, just us."), ("rider", rname, T(0.47), "Please stop. I'm uncomfortable.")]
        ev += [{"timestamp": iso(T(0.47)), "event_type": "rider_in_app_safety_report", "details": "Rider tapped 'I feel uncomfortable' in the app."}]
        desc = f"During my {fdate(day)} ride from {a_name} to {b_name} the driver kept asking for my number and where I live, even after I said no. It made me very uncomfortable and I want this reviewed."
        cat, sev = "harassment", "high"
    elif sc == "verbal_abuse":
        ch += [("rider", rname, T(0.35), "Could you please turn down the aircon a bit? I'm cold."), ("driver", dn[1], T(0.36), "Don't tell me what to do in my own car!"),
               ("driver", dn[1], T(0.50), "If you keep complaining I will drop you off right here on the road.")]
        ev += [{"timestamp": iso(T(0.52)), "event_type": "rider_in_app_safety_report", "details": "Rider reported driver conduct (verbal abuse and threat to stop the trip)."}]
        desc = f"On {fdate(day)} on my trip from {a_name} to {b_name} the driver shouted at me after I asked about the aircon and threatened to leave me by the road. I was scared."
        cat, sev = "verbal_abuse_threat", "high"
    elif sc == "collision":
        speeds[5] = 0
        ev += [{"timestamp": iso(T(0.58)), "event_type": "collision_detected", "details": "Accelerometer impact detected (low severity). Vehicle stopped for 3 minutes."}]
        ch += [("rider", rname, T(0.60), "Are you okay? We hit something!"), ("driver", dn[1], T(0.61), "Just a small bump, don't worry. Everything is fine.")]
        desc = f"My ride on {fdate(day)} from {a_name} to {b_name} was involved in a collision. The driver told me not to worry and carried on. I had a sore neck afterwards and want this recorded."
        cat, sev = "accident", "high"
    elif sc == "distracted_driving":
        ev += [{"timestamp": iso(T(0.30)), "event_type": "phone_usage_alert", "details": "Handset movement detected while the vehicle was moving."},
               {"timestamp": iso(T(0.62)), "event_type": "phone_usage_alert", "details": "Handset movement detected while the vehicle was moving."},
               {"timestamp": iso(T(0.65)), "event_type": "harsh_braking_alert", "details": "Harsh braking event detected."}]
        ch += [("rider", rname, T(0.33), "Excuse me, you keep looking at your phone while driving.")]
        desc = f"On {fdate(day)} from {a_name} to {b_name} the driver was on his phone during the ride, scrolling while driving and almost hitting the car in front. I felt unsafe."
        cat, sev = "distracted_driving", "high"
    elif sc == "unsafe_detour_night":
        ev += [{"timestamp": iso(T(0.45)), "event_type": "route_anomaly_alert", "details": "Vehicle left the recommended corridor into an industrial area."}]
        ch += [("rider", rname, T(0.46), "Where are we going? I don't recognise this road."), ("driver", dn[1], T(0.47), "Shortcut. Don't worry.")]
        desc = f"It was late at night on {fdate(day)} on my ride from {a_name} to {b_name}. The driver turned into a dark industrial road I didn't know and would not explain. I was afraid and want this checked."
        cat, sev = "unsafe_conduct", "high"
    else:  # suspected_intoxication
        for i in (3, 4, 5):
            speeds[i] = rnd.choice([30, 64, 28])
        ev += [{"timestamp": iso(T(0.35)), "event_type": "lane_deviation_alert", "details": "Repeated lane deviation detected."},
               {"timestamp": iso(T(0.50)), "event_type": "harsh_braking_alert", "details": "Harsh braking event detected."}]
        ch += [("rider", rname, T(0.36), "Are you okay to drive? You smell strongly of alcohol.")]
        desc = f"On {fdate(day)} on my ride from {a_name} to {b_name} I suspect the driver had been drinking. He smelled of alcohol, kept drifting between lanes and braked suddenly. I want this investigated."
        cat, sev = "suspected_impaired_driving", "high"
    ev.append({"timestamp": iso(end), "event_type": "trip_ended", "details": "Trip completed."})
    ev.sort(key=lambda e: e["timestamp"])
    ch.sort(key=lambda x: x[2])
    chat = chat_entries(ch)
    gps = [{"timestamp": iso(T(i / (N - 1))), "lat": p[0], "lng": p[1], "speed_kmh": speeds[i]} for i, p in enumerate(path)]
    trip_data = {"trip_id": c["trip_id"], "rider_id": rider, "driver_id": drv,
                 "pickup_location": {"name": a_name, "address": f"{a_name}, Singapore", "lat": A[0], "lng": A[1]},
                 "dropoff_location": {"name": b_name, "address": f"{b_name}, Singapore", "lat": B[0], "lng": B[1]},
                 "start_time": iso(start), "end_time": iso(end), "actual_distance_km": km, "status": "completed", "currency": "SGD", "fare_charged": fare}
    filed = end + timedelta(minutes=rnd.randint(5, 120))
    exp = dict(ruling="escalated", refund_amount=None, clause="5.1/5.2", must_escalate=True, must_escalate_reason=["safety_incident"],
               facts=dict(subtype=cat))
    incident = dict(category=cat, severity_indicator=sev, reported_by="rider", alleged_party="driver", reported_at=iso(filed), status="flagged_for_human_review",
                    note="AI may only gather evidence and prepare the case file (policy 5.2). No ruling, no fault finding, no recommended resolution.",
                    interim_measures_under_policy_5_3=["temporary suspension of the accused party's account", "no new trip acceptance or booking", "lifted if the reviewer finds no violation"])
    return dict(trip_data=trip_data, gps=gps, chat=chat, events=ev, extra={}, description=desc, requested_resolution="safety_review", requested_amount=None,
                filed_at=filed, expected=exp, route_text=f"{a_name} → {b_name}", outcome_text="Trip completed, safety report filed",
                story=dict(a=a_name, b=b_name, day=day, sub=cat), official_extra=dict(incident_report=incident),
                evidence=[("gps_telemetry", "Trip telemetry recorded", "rider"), ("app_events", f"{len(ev)} app events incl. safety alerts", "rider"),
                          ("chat_logs", f"{len(chat)} chat messages", "rider"), ("driver_history", f"Driver rating {dn[4]['avg_rating']}, {dn[4]['total_trips']} trips", "driver")])


BUILDERS = {"route_deviation": build_route, "no_show_charge": build_noshow, "property_damage": build_property, "safety_incident": build_safety}


# ================================================================== assembly
SAMPLE_PARTIES = {  # the six sample cases already in the app (DISP-001..006), kept as they are
    "TRIP-2026-09871": {"rider_id": "R-4521", "driver_id": "D-1187", "route": "Orchard Central → Changi Airport T3", "outcome": "Trip completed (route deviated)"},
    "TRIP-2026-09945": {"rider_id": "R-7823", "driver_id": "D-2398", "route": "Tiong Bahru Plaza → VivoCity", "outcome": "Trip cancelled, S$5 no-show fee charged"},
    "TRIP-2026-10023": {"rider_id": "R-9001", "driver_id": "D-3456", "route": "Bugis Junction → Marina Bay Sands", "outcome": "Trip completed (fare S$16.50 vs quote S$12.00)"},
    "TRIP-2026-10201": {"rider_id": "R-3312", "driver_id": "D-4410", "route": "Orchard MRT → Changi Business Park", "outcome": "Trip completed, S$35 cleaning fee charged"},
    "TRIP-2026-10305": {"rider_id": "R-5120", "driver_id": "D-6021", "route": "Clarke Quay → Tampines Mall", "outcome": "Trip completed (speeding alert)"},
    "TRIP-2026-10410": {"rider_id": "R-7001", "driver_id": "D-7002", "route": "Tanjong Pagar Centre → HarbourFront", "outcome": "Trip cancelled, S$5 no-show fee charged"},
}
SAMPLE_DRIVER_OPEN = {"D-1187": 1, "D-2398": 1, "D-3456": 1, "D-4410": 1, "D-6021": 1, "D-7002": 1}
EVENT = "Tencent Cloud AI Agent Hackathon Singapore 2026 — AI Agent Digital Native Track"
SRC = ("Synthetic. Dispute id, trip id, rider and driver (ids and names), dispute type and the rider-driver pair are exactly as in the team's 60-ticket file "
       "(cleaning_fee_dispute is called property_damage here); every other field (dates, places, GPS, chats, fares, photos, outcomes) is generated by scripts/build_dataset60.py.")
LABEL = {"rejected": "no_refund", "partial": "partial_refund", "upheld": "full_refund", "escalated": "escalated_to_human"}
TYPE_NAME = {"route_deviation": "route deviation", "no_show_charge": "no-show charge", "property_damage": "property damage / cleaning fee", "safety_incident": "safety incident"}


def rationale(cat, e):
    txt = _rationale(cat, e)
    f = e["facts"]
    if cat == "route_deviation" and e["ruling"] != "escalated" and f["deviation_km"] > 2.0:
        txt += " The deviation is over 2 km, so the AI recommendation needs human approval (policy 6.1)."
    if cat == "property_damage" and f["claim_type"] == "repair" and "6.1" not in txt:
        txt += " Repair claims always need human review (policy 6.1)."
    return txt


def _rationale(cat, e):
    f = e["facts"]
    if cat == "route_deviation":
        if e["ruling"] == "escalated":
            return "Evidence is too thin (GPS and chat) to rule automatically. Escalated to a human reviewer."
        if f["deviation_km"] <= 1.0:
            return f"Deviation of {f['deviation_km']} km is within the 1 km tolerance (policy 1.3). No refund."
        if f["traffic_justified"] and f["rider_informed"]:
            return "A traffic incident justified the reroute and the driver informed the rider in time (policy 1.2, 1.3). No refund."
        if f["traffic_justified"]:
            return f"The reroute was traffic-justified but the rider was not informed in time (policy 1.2). Partial refund of the excess distance fare (S${f['excess_distance_fare']:.2f})."
        return f"No traffic justification for a {f['deviation_km']} km deviation (policy 1.3). Full refund of the excess distance fare (S${f['excess_distance_fare']:.2f})."
    if cat == "no_show_charge":
        return {"2.2": "Driver arrived on time, waited the 5-minute free period and contacted the rider by message and call. The S$5 fee stands (policy 2.2, 2.3).",
                "2.3": "Driver did not meet both contact obligations (message AND call) before cancelling. The fee is voided (policy 2.3).",
                "2.1": "Driver cancelled before the 5-minute free wait ended. The fee is voided (policy 2.1).",
                "2.4": "Driver arrived more than 5 minutes after the scheduled pickup. The rider may cancel without charge (policy 2.4)." + (" No contact attempt was made, so a S$5 goodwill credit also applies." if e.get("goodwill_credit") else ""),
                "safety_net": "Evidence is too thin to rule automatically (a source is empty or near-empty). Escalated to a human reviewer."}[e["clause"]]
    if cat == "property_damage":
        if e["ruling"] == "escalated":
            return "No photo evidence is on record, so the evidence base is too thin for an automatic ruling. Escalated (policy 4.4 would reject an unsupported claim)."
        if e["ruling"] == "rejected":
            return "Verifiable in-app photo evidence within 24 hours supports the claim" + (" and the repair quote is on record. Repair claims always need human approval (policy 6.1)." if f["claim_type"] == "repair" else f" and the fee is within the S$50 cap. The fee stands (policy 4.2, 4.3).")
        return "The evidence does not meet policy 4.2 (timing, in-app camera, or link to the trip) or a required quote is missing. The claim is rejected and the fee reversed (policy 4.4)."
    return "Safety-related dispute. AI may only gather evidence and prepare a case file. A human must review (policy 5.1, 5.2)."


def snapshot(kind, pid, as_of, ds):
    """Profile as it stood at `as_of` (a datetime). Time-consistent: trips and open disputes only count what happened before."""
    if kind == "rider":
        _, name, base, bdate = RID[pid]
        mine = [x for x in ds if x["rider"] == pid]
        sample = SAMPLE_OPEN.get(pid, 0)
        rate = 0.2
    else:
        _, name, veh, color, base, bdate = DID[pid]
        mine = [x for x in ds if x["driver"] == pid]
        sample = SAMPLE_DRIVER_OPEN.get(pid, 0)
        rate = 3.1
    days = max(0, (as_of.date() - bdate).days)
    prof = json.loads(json.dumps(base))
    prof["name"] = name
    prof["account_age_days"] = base["account_age_days"] + days
    prof["account_created_at"] = iso(datetime(bdate.year, bdate.month, bdate.day, tzinfo=TZ) - timedelta(days=base["account_age_days"]))
    prof["total_trips"] = base["total_trips"] + int(days * rate) + sum(1 for x in mine if x["trip_start"] < as_of)
    prof["dispute_history"]["open_disputes"] = sample + sum(1 for x in mine if x["filed_at"] < as_of)
    if kind == "driver":
        prof["vehicle"], prof["vehicle_color"] = veh, color
    prof = {("rider_id" if kind == "rider" else "driver_id"): pid, **prof}
    prof["profile_as_of"] = as_of.date().isoformat()
    return prof


def main():
    plan_ = plan()
    cases = []
    for c in plan_:
        c["trip_id"] = f"TRIP-2026-{2000 + c['n']}"
        c["dispute_id"] = f"DISP-{100 + c['n']}"
        rnd = random.Random(777000 + c["n"])
        b = BUILDERS[c["cat"]](c, rnd)
        b.update(c)
        b["trip_start"] = datetime.fromisoformat(b["trip_data"].get("start_time") or b["trip_data"]["scheduled_time"])
        cases.append(b)

    # ---- sanity checks
    assert len(cases) == 60 and len({x["trip_id"] for x in cases}) == 60
    for rid in RID:
        for cat in CATS:
            n_ = sum(1 for x in cases if x["rider"] == rid and x["cat"] == cat)
            assert n_ >= 2, (rid, cat, n_)
    for x in cases:
        assert x["filed_at"] <= AS_OF, (x["dispute_id"], x["filed_at"])
        assert x["filed_at"] > x["trip_start"], (x["dispute_id"], "filed before trip")

    ds = [dict(rider=x["rider"], driver=x["driver"], trip_start=x["trip_start"], filed_at=x["filed_at"]) for x in cases]
    for d in ("official_format", "app_fixtures/disputes", "app_fixtures/trips", "app_fixtures/expected", "app_fixtures/profiles/riders", "app_fixtures/profiles/drivers", "stories"):
        shutil.rmtree(os.path.join(OUT, d), ignore_errors=True)
        os.makedirs(os.path.join(OUT, d), exist_ok=True)

    def dump(path, obj):
        with open(os.path.join(OUT, path), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    parties = dict(SAMPLE_PARTIES)
    for x in cases:
        e = x["expected"]
        rider, drv = RID[x["rider"]], DID[x["driver"]]
        e["rationale"] = rationale(x["cat"], e)
        fparts = {"safety_incident": "high"}
        ticket = {"dispute_id": x["dispute_id"], "trip_id": x["trip_id"], "filed_by": "rider", "filed_by_id": x["rider"], "dispute_type": x["cat"],
                  "description": x["description"], "filed_at": iso(x["filed_at"]), "status": "open",
                  "priority": "high" if x["cat"] == "safety_incident" or (e.get("must_escalate")) else "medium", "assigned_to": "RydeResolve_Auto_Resolution",
                  "evidence_provided": {"route_deviation": ["trip_screenshot", "gps_route_screenshot", "receipt"], "no_show_charge": ["chat_screenshot", "receipt"],
                                        "property_damage": ["receipt", "rider_statement"], "safety_incident": ["in_app_safety_report", "trip_screenshot"]}[x["cat"]]}
        # ---------- official single-file format
        off = {"case_metadata": {"dataset_id": x["dispute_id"], "scenario": x["cat"], "platform": "RydeResolve", "event": EVENT, "version": "1.0",
                                 "expected_ruling": LABEL[e["ruling"]], "expected_refund_amount": e["refund_amount"], "ruling_rationale": e["rationale"], "_source": SRC},
               "dispute_ticket": ticket,
               "rider_profile": snapshot("rider", x["rider"], x["filed_at"], ds), "driver_profile": snapshot("driver", x["driver"], x["filed_at"], ds),
               "trip_data": x["trip_data"]}
        if "fare_breakdown" in x["extra"]:
            off["fare_breakdown"] = {**x["extra"]["fare_breakdown"], "notes": f"Distance fare is calculated at S${RATE:.2f}/km."}
        off["gps_telemetry"] = x["gps"]
        if "optimal_route" in x["extra"]:
            off["optimal_route"] = x["extra"]["optimal_route"]
        off["chat_logs"] = x["chat"]
        if "chat_log_analysis" in x["official_extra"]:
            off["chat_log_analysis"] = x["official_extra"]["chat_log_analysis"]
        if "traffic_conditions" in x["extra"]:
            off["traffic_conditions"] = x["extra"]["traffic_conditions"]
        if "traffic_analysis" in x["official_extra"]:
            off["traffic_analysis"] = x["official_extra"]["traffic_analysis"]
        off["app_events"] = x["events"]
        for k in ("damage_evidence",):
            if k in x["extra"]:
                off[k] = x["extra"][k]
        for k in ("photo_review", "wait_analysis", "incident_report"):
            if k in x["official_extra"]:
                off[k] = x["official_extra"][k]
        items = [{"id": f"EV-{i:03d}", "type": t, "description": d, "supports": s} for i, (t, d, s) in enumerate(x["evidence"], 1)]
        off["evidence_summary"] = {"total_evidence_items": len(items), "items": items,
                                   "rider_supporting": [i["id"] for i in items if i["supports"] == "rider"], "driver_supporting": [i["id"] for i in items if i["supports"] == "driver"]}
        rec = {"ruling": LABEL[e["ruling"]], "refund_amount": e["refund_amount"], "currency": "SGD", "rationale": e["rationale"]}
        if x["cat"] == "safety_incident":
            rec["note"] = "No recommendation: AI cannot rule on safety incidents (policy 5.2)."
        else:
            rec["actions"] = ([{"action": "refund_rider", "amount": e["refund_amount"], "currency": "SGD", "method": "original_payment_method"}] if e["refund_amount"] else []) + \
                             ([{"action": "goodwill_credit", "amount": e["goodwill_credit"], "currency": "SGD"}] if e.get("goodwill_credit") else []) + \
                             ([{"action": "human_review", "reason": e["must_escalate_reason"]}] if e["must_escalate"] else [])
        off["recommended_ruling"] = rec
        dump(f"official_format/{x['dispute_id']}.json", off)

        # ---------- app fixtures (ground truth kept out of the trip and dispute files)
        dump(f"app_fixtures/disputes/{x['dispute_id']}.json",
             {"dispute_id": x["dispute_id"], "_source": "Synthetic (ticket ids and parties from the team's 60-ticket file)", "trip_id": x["trip_id"], "filed_by": "rider",
              "rider_id": x["rider"], "driver_id": x["driver"], "dispute_type": x["cat"], "description": x["description"], "filed_at": iso(x["filed_at"]),
              "requested_resolution": x["requested_resolution"], "requested_amount": x["requested_amount"]})
        trip = {"trip_id": x["trip_id"], "_source": "Synthetic (generated by build_dataset60.py)", "trip_data": x["trip_data"], "gps_telemetry": x["gps"],
                "chat_logs": x["chat"], "app_events": x["events"], **x["extra"]}
        dump(f"app_fixtures/trips/{x['trip_id']}.json", trip)
        dump(f"app_fixtures/expected/{x['dispute_id']}.json",
             {"source": "computed from Policy v2.1 and the scenario parameters (build_dataset60.py), not by the app", "scenario": x["scen"],
              "ruling": e["ruling"], "refund_amount": e["refund_amount"], "goodwill_credit": e.get("goodwill_credit", 0.0), "clause": e["clause"],
              "must_escalate": e["must_escalate"], "must_escalate_reason": e["must_escalate_reason"],
              "fraud_flag_party": x["rider"] == "R-7823", "rationale": e["rationale"], "facts": e["facts"]})
        parties[x["trip_id"]] = {"rider_id": x["rider"], "driver_id": x["driver"], "route": x["route_text"], "outcome": x["outcome_text"]}

    last = AS_OF
    for rid in RID:
        dump(f"app_fixtures/profiles/riders/{rid}.json", snapshot("rider", rid, last, ds))
    for did in DID:
        dump(f"app_fixtures/profiles/drivers/{did}.json", snapshot("driver", did, last, ds))
    dump("app_fixtures/trip_parties.json", parties)

    # ---------- stories
    stories = []
    vague = {"route_deviation": ["The driver took a really long route and I got charged more.", "My driver went round and round and the fare was higher than expected.", "I think I was overcharged because the driver took a longer way."],
             "no_show_charge": ["I got charged a cancellation fee but the driver wasn't even there.", "Charged a no-show fee but I was waiting for the driver.", "The driver cancelled on me and I still paid a fee."],
             "property_damage": ["I got charged a cleaning fee that I don't think is fair.", "There's a damage fee on my account for a ride where I did nothing wrong.", "Why am I being charged for cleaning? I didn't make a mess."],
             "safety_incident": ["The driver made me feel unsafe on one of my recent trips.", "I want to report something that happened with a driver, I was scared.", "My last ride was not safe, I want this looked at."]}
    casual = {"route_deviation": "Eh the driver cannot go the normal way one lah, bring me round and round then charge me more. Please check.",
              "no_show_charge": "Aiyo the driver cancel on me and still charge me $5 no show fee, I was waiting there leh.",
              "property_damage": "Why got cleaning fee ah? I never dirty the car, please remove lah.",
              "safety_incident": "That driver very scary lah, I don't feel safe, please check."}
    sub_phrase = {"reckless_driving": "the driver was speeding and braking hard and I felt unsafe", "harassment": "the driver kept asking for my number and made me uncomfortable",
                  "verbal_abuse_threat": "the driver shouted at me and threatened to drop me off on the road", "accident": "the car was in a collision and the driver carried on",
                  "distracted_driving": "the driver was on his phone while driving", "unsafe_conduct": "the driver took a dark industrial road at night and would not explain",
                  "suspected_impaired_driving": "I think the driver had been drinking"}
    for x in cases:
        s = x["story"]; d = fdate(s["day"]); cat = x["cat"]
        if cat == "route_deviation":
            precise = f"On {d} I took a Ryde from {s['a']} to {s['b']} and paid S${s['act']:.2f} when the estimate was S${s['est']:.2f}. The driver went a much longer way. Please refund the extra."
        elif cat == "no_show_charge":
            precise = f"I had a pickup at {s['a']} on {d} at {s['time']} but the driver cancelled and I was charged a S$5 no-show fee. Please refund it."
        elif cat == "property_damage":
            precise = f"After my ride from {s['a']} to {s['b']} on {d} I was charged a S${s['amount']:.0f} {'damage' if s['repair'] else 'cleaning'} fee. I did not cause any damage. Please reverse it."
        else:
            precise = f"On {d} on my ride from {s['a']} to {s['b']}, {sub_phrase[s['sub']]}. I want this reviewed."
        peers = [y["trip_id"] for y in cases if y["rider"] == x["rider"] and y["cat"] == cat]
        base = dict(rider_id=x["rider"], rider_name=RID[x["rider"]][1], language="en", expected_dispute_id=x["dispute_id"], expected_trip_id=x["trip_id"],
                    expected_category=cat, same_category_trips_for_this_rider=peers)
        vr = random.Random(5150 + x["n"])
        stories.append({"story_id": f"STORY-{x['n']:03d}-precise", "style": "precise", "text": precise, "expect_picker": False, **base})
        stories.append({"story_id": f"STORY-{x['n']:03d}-vague", "style": "vague", "text": vr.choice(vague[cat]), "expect_picker": True, **base})
        stories.append({"story_id": f"STORY-{x['n']:03d}-casual", "style": "casual", "text": casual[cat], "expect_picker": True, **base})
    neg = []
    for i, x in enumerate(cases[:60:7]):
        other = next(y for y in cases if y["rider"] != x["rider"] and y["cat"] == x["cat"])
        neg.append({"story_id": f"STORY-NEG-{i + 1:02d}", "style": "other_rider_trip", "rider_id": x["rider"], "rider_name": RID[x["rider"]][1],
                    "text": f"Please check trip {other['trip_id']}, the {TYPE_NAME[other['cat']]} charge on {RID[other['rider']][1]}'s account is wrong.",
                    "expected_result": "refuse_not_on_this_account", "must_not_reveal": [other["trip_id"], RID[other["rider"]][1], other["rider"]]})
    dump("stories/stories.json", {"note": "Story prompts for testing the free-text flow. 'expect_picker' is true when the rider has more than one trip in that category, so the story alone cannot identify one trip.",
                                  "stories": stories, "negative_stories": neg})

    write_readme(cases)
    # ---------- summary
    print("cases", len(cases))
    print("rider x category matrix")
    for rid in RID:
        print(" ", rid, RID[rid][1], [sum(1 for x in cases if x["rider"] == rid and x["cat"] == c) for c in CATS])
    from collections import Counter
    print("expected rulings:", dict(Counter((x["cat"], x["expected"]["ruling"]) for x in cases)))
    print("must_escalate:", sum(1 for x in cases if x["expected"]["must_escalate"]))
    print("dates", min(x["trip_start"] for x in cases).date(), max(x["filed_at"] for x in cases).date())


def write_readme(cases):
    from collections import Counter, defaultdict
    sc_tab = defaultdict(Counter)
    for x in cases:
        sc_tab[x["cat"]][(x["scen"], x["expected"]["ruling"], x["expected"]["refund_amount"] is not None)] += 1
    rows = []
    for cat in CATS:
        rows.append(f"**{TYPE_NAME[cat]}**\n")
        rows.append("| scenario | expected ruling | tickets |\n|---|---|---|")
        agg = defaultdict(lambda: [0, set()])
        for (scn, ruling, _), n_ in sorted(sc_tab[cat].items()):
            agg[scn][0] += n_; agg[scn][1].add(ruling)
        for scn, (n_, rl) in agg.items():
            rows.append(f"| {scn} | {', '.join(sorted(rl))} | {n_} |")
        rows.append("")
    matrix = ["| rider | route | no-show | property | safety | total |", "|---|---|---|---|---|---|"]
    for rid, name, _b, _d in RIDERS:
        cnt = [sum(1 for x in cases if x["rider"] == rid and x["cat"] == c) for c in CATS]
        matrix.append(f"| {name} ({rid}) | " + " | ".join(map(str, cnt)) + f" | {sum(cnt)} |")
    must = sum(1 for x in cases if x["expected"]["must_escalate"])
    txt = f"""# RydeResolve 60-ticket dataset (DISP-101 to DISP-160)

Full tickets in the layout of the organisers' DISP-001 sample, plus the same cases split the way the app loads them.

## What is real and what is synthetic
- **From the team's 60-ticket file (unchanged):** dispute id, trip id, rider id and name, driver id and name, dispute type, and the rider-driver pair for every ticket. The only rename is `cleaning_fee_dispute` to `property_damage` (the organisers' category table calls it Property Damage / Mess).
- **Synthetic (generated by `scripts/build_dataset60.py`, fixed seeds):** every other field: dates, places, GPS, chats, fares, photos, repair quotes, traffic incidents, profile statistics, and all expected outcomes.
- Expected outcomes are computed straight from Ryde Dispute Resolution Policy v2.1 and the scenario parameters, not by calling the app. They are **our reading of the policy**, not organiser answers.

## What was inconsistent in the old 60 tickets, and what changed
1. The tickets were shells: no trip, GPS, chat or evidence (every tool call would fail with "data not found"), one identical placeholder description per type, and one identical filing timestamp. Now each ticket has a distinct story, trip, evidence and timeline.
2. Names existed only in the ticket files; the app's profile files had no names. Every profile now carries the name.
3. Profiles contradicted the tickets: Priya Nair had 7 trips in total but 10 disputed trips, Chloe Ng had 3 trips on a 10-day-old account. Profiles are now time-consistent: each ticket embeds a snapshot as of its filing date, the app profile is as of 2026-10-15, trips and open disputes only count what happened before, and `total_trips` is never below the number of disputed trips.
4. Official sample profile values (dispute history, fraud flags, ratings) are not changed. Only `name`, `account_age_days`, `total_trips`, `open_disputes` and `profile_as_of` are added or advanced.
5. Dispute type name `cleaning_fee_dispute` is now `property_damage`.
6. Trip dates run from 2026-09-18 to 2026-10-14, after the sample cases (DISP-001 to DISP-006), so the sample profiles stay valid.

## Coverage
Every rider has at least 2 tickets in every category (15 tickets per category, 10 per rider).

""" + "\n".join(matrix) + f"""

Scenarios per category (every scenario below is built so the policy gives one clear answer):

""" + "\n".join(rows) + f"""
{must} of the 60 tickets must reach a human by a deterministic rule (deviation over 2 km, repair claim, safety incident, or evidence too thin for the safety net).

## Folders
- `official_format/`: one full JSON per dispute, same layout as the organisers' DISP-001 file. Contains the expected ruling inside (as the organisers' file does), so **do not load this folder into the app**; use it for reference, review and submission screenshots.
- `app_fixtures/`: the same cases split for the app: `disputes/` (ticket only), `trips/` (trip evidence only), `expected/` (ground truth, tests only), `profiles/riders` and `profiles/drivers` (with names), `trip_parties.json` (all 66 trips: the 6 samples plus these 60).
- `stories/stories.json`: 180 free-text stories (precise, vague, Singlish-style, 3 per ticket) and 9 negative stories that name another rider's trip. `expect_picker` is true when the rider has several trips in that category.
- `tests/test_dataset60.py`: offline tests (shape, parties and profiles consistent, no ground truth in trip or dispute files, rulings in EN and ZH, safety never ruled by the AI).
- `scripts/build_dataset60.py`: regenerates everything (`python3 -I scripts/build_dataset60.py`).

## Using `expected/`
`ruling` is `rejected` (rider's dispute fails, fee stands), `partial`, `upheld` (rider wins, `refund_amount` refunded) or `escalated` (a human must decide, `refund_amount` is null).
`must_escalate` is true when a deterministic rule forces human review. `fraud_flag_party` is true for Daniel Lim (R-7823, fraud flag 1): the 95% confidence bar (policy 6.3) often makes the app escalate cases the policy would otherwise rule on. In that case the app's `recommendation` field (not `ruling`) should equal the expected ruling and refund. `tests/test_dataset60.py` already does this.

## Add to the repo
```
cp -r app_fixtures/disputes/. fixtures/disputes/
cp -r app_fixtures/trips/. fixtures/trips/
cp -r app_fixtures/expected/. fixtures/expected/
cp -r app_fixtures/profiles/riders/. fixtures/profiles/riders/
cp -r app_fixtures/profiles/drivers/. fixtures/profiles/drivers/
cp app_fixtures/trip_parties.json fixtures/trip_parties.json     # replaces the file: it already contains the 6 samples
cp tests/test_dataset60.py tests/
```
The old test in `tests/test_rydeResolve.py` loops over every file in `fixtures/expected/`. Change its glob from `DISP-*.json` to `DISP-00*.json` so it only covers the six samples, then run `pytest -q`.

## Honest limits
- All trip evidence is synthetic. The organisers' dataset has none for these tickets.
- Photos are metadata only (no images), so the "image analysis" stretch goal is not exercised.
- The offline backend was run on all 60 tickets and matches `expected/` (with the fraud-flag rule above). The live LLM backend has not been run on all 60.
- Fare disputes are not in this set (the organisers' category table has four types). The fare sample is still DISP-003.
"""
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(txt)


if __name__ == "__main__":
    main()
