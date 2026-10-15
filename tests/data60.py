"""Test helper: the fixtures as the app reads them (trip_parties.json, trips/, disputes/, profiles/).

load() -> {riders, drivers, trips, tickets}: riders / drivers {id: {"id", "name"}}, trips {trip_id: {trip_id, rider_id,
driver_id, dispute_id}} for all 66 trips (6 samples + 60 dataset), tickets {dispute_id: ticket}. evidence() -> {trip_id:
trip file}. Never reads fixtures/expected (tests that need ground truth open it themselves).
"""
import json
import pathlib
from functools import lru_cache

FX = pathlib.Path(__file__).resolve().parents[1] / "fixtures"


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load() -> dict:
    tickets = {p.stem: _j(p) for p in sorted((FX / "disputes").glob("*.json"))}
    by_trip = {t["trip_id"]: t["dispute_id"] for t in tickets.values()}
    trips = {tid: {"trip_id": tid, "rider_id": p["rider_id"], "driver_id": p["driver_id"], "dispute_id": by_trip.get(tid)}
             for tid, p in _j(FX / "trip_parties.json").items()}
    people = {kind: {p.stem: {"id": p.stem, "name": _j(p)["name"]} for p in sorted((FX / "profiles" / kind).glob("*.json"))}
              for kind in ("riders", "drivers")}
    return {"riders": people["riders"], "drivers": people["drivers"], "trips": trips, "tickets": tickets}


@lru_cache(maxsize=1)
def evidence() -> dict:
    return {p.stem: _j(p) for p in sorted((FX / "trips").glob("*.json"))}


def dataset_trip_ids() -> list:
    """The 60 dataset trips (tickets DISP-101 to DISP-160)."""
    return sorted(t for t, v in load()["trips"].items() if v["dispute_id"] and not v["dispute_id"].startswith("DISP-00"))
