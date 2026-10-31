"""
Bus schedules: one timetable per route, set day by day by the admin (Schedules tab).

For every day of the week a route has
  * morning trips:   which bus, and the time it REACHES the campus
  * afternoon trips: which bus, and the time it LEAVES the campus
A day without trips means no bus that day.

Students, teachers and drivers only see TODAY's timetable (Bangladesh date) in the
"Bus schedule" pop-up. Times are stored as 24-hour "HH:MM".
"""

import re

from sqlalchemy import select

from content.site_text import DAY_NAMES
from content.starting_data import SCHEDULES as STARTING_SCHEDULES
from extensions import db
from models.records import TimetableRecord
from services import geo, store, tracking

TIME_24H_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DAYS = tuple(DAY_NAMES)              # ("sat", "sun", "mon", "tue", "wed", "thu", "fri")
PARTS = ("morning", "afternoon")
MAX_TRIPS = 30                       # per day and part
PYTHON_WEEKDAY_TO_DAY = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")   # date.weekday() -> key


def today_key() -> str:
    """Today's day key in Bangladesh time, e.g. "sat"."""
    return PYTHON_WEEKDAY_TO_DAY[geo.local_now().weekday()]


def _saved_days() -> dict[str, dict]:
    """route_id -> its saved week {"sat": {"morning": [...], "afternoon": [...]}, ...}."""
    return {row.route_id: row.days or {} for row in store.all_rows(TimetableRecord)}


def todays_schedules(audience: str | None = None) -> dict:
    """
    Today's trips of every route for the pop-up, with each trip's bus name and colour.
    With `audience` (e.g. "student") trips of buses meant for another group are left out.
    """
    day = today_key()
    saved = _saved_days()
    buses = {b["bus_id"]: b for b in tracking.all_buses()}
    routes = []
    for route in tracking.all_routes():
        today = saved.get(route["route_id"], {}).get(day, {})
        entry = {"route_id": route["route_id"], "route_name": route["route_name"], "color_hex": route["color_hex"]}
        for part in PARTS:
            trips = []
            for trip in today.get(part, []):
                bus = buses.get(trip.get("bus_id"))
                if audience and bus and bus["audience"] != audience:
                    continue
                trips.append({"time": trip["time"],
                              "bus_name": bus["bus_name"] if bus else "",
                              "color_hex": bus["color_hex"] if bus else route["color_hex"]})
            entry[part] = trips
        routes.append(entry)
    return {"day": day, "day_name": DAY_NAMES[day], "routes": routes}


def all_timetables() -> list[dict]:
    """Every route with its full week (for the backend), days in week order, missing days empty."""
    saved = _saved_days()
    return [{
        "route_id": route["route_id"],
        "route_name": route["route_name"],
        "color_hex": route["color_hex"],
        "days": {day: {part: saved.get(route["route_id"], {}).get(day, {}).get(part, []) for part in PARTS}
                 for day in DAYS},
    } for route in tracking.all_routes()]


def save_timetable(route_id: str, data: dict) -> dict:
    """
    Save a route's whole week from the backend.
    Body: {"days": {"sat": {"morning": [{"bus_id", "time"}], "afternoon": [...]}, ...}}
    Raises LookupError (no such route) or ValueError (bad input, readable message).
    """
    if tracking.get_route(route_id) is None:
        raise LookupError(f"Route {route_id} not found.")
    raw_days = data.get("days")
    if not isinstance(raw_days, dict):
        raise ValueError("The timetable is not valid.")
    unknown = set(raw_days) - set(DAYS)
    if unknown:
        raise ValueError(f"Unknown day: {', '.join(sorted(unknown))}.")
    days = {day: {part: _clean_trips(raw_days.get(day, {}).get(part), DAY_NAMES[day], part) for part in PARTS}
            for day in DAYS}
    store.save(TimetableRecord(route_id=route_id, days=days))
    return next(t for t in all_timetables() if t["route_id"] == route_id)


def delete_timetable(route_id: str) -> None:
    """Remove a route's timetable (when the route itself is deleted)."""
    store.delete(TimetableRecord, route_id)


def seed_timetables() -> None:
    """Add the starting timetables (content/starting_data.py) once, if there are none at all."""
    if db.session.scalar(select(TimetableRecord.route_id).limit(1)) is not None:
        return
    for route_id, spec in STARTING_SCHEDULES.items():
        if tracking.get_route(route_id) is None:
            continue
        week = {part: [{"bus_id": bus_id, "time": time} for bus_id, time in spec[part]] for part in PARTS}
        db.session.add(TimetableRecord(route_id=route_id,
                                       days={day: week for day in spec.get("days", DAYS)}))
    db.session.commit()


def _clean_trips(trips, day_name: str, part: str) -> list[dict]:
    """Check one day's morning or afternoon trips: a known bus (or none) and a valid time. Sorted by time."""
    if not trips:
        return []
    if not isinstance(trips, list) or len(trips) > MAX_TRIPS:
        raise ValueError(f"{day_name} {part}: at most {MAX_TRIPS} buses.")
    clean = []
    for trip in trips:
        time = str((trip or {}).get("time") or "").strip()
        bus_id = str((trip or {}).get("bus_id") or "").strip()
        if not TIME_24H_RE.match(time):
            raise ValueError(f"{day_name} {part}: enter a time for every bus.")
        if bus_id and tracking.get_bus(bus_id) is None:
            raise ValueError(f"{day_name} {part}: bus {bus_id} doesn't exist.")
        clean.append({"bus_id": bus_id, "time": time})
    return sorted(clean, key=lambda t: t["time"])
