"""
Small helpers for saving to and reading from the database.

The services keep a fast in-memory copy of routes, buses and drivers, and use
these helpers to write every admin change straight through to the database.
All functions must run inside a Flask app context (any request handler does).
"""

from datetime import UTC, datetime

from sqlalchemy import select

from extensions import db
from models.records import RiderRecord, RouteRecord
from models.seed_data import default_buses, default_routes, demo_drivers


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 text, the format all saved dates use."""
    return datetime.now(UTC).isoformat()


def save(record: db.Model) -> None:
    """Insert or update one row (matched by primary key) and commit."""
    db.session.merge(record)
    db.session.commit()


def delete(model: type[db.Model], key: str) -> None:
    """Delete the row of `model` with primary key `key` (if it exists) and commit."""
    row = db.session.get(model, key)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


def all_rows(model: type[db.Model]) -> list:
    """Every row of a table."""
    return list(db.session.scalars(select(model)))


def seed_defaults(with_demo_drivers: bool) -> None:
    """
    Fill an empty database with the built-in KU routes and buses
    (and, if asked, four demo drivers with PIN 1234). Does nothing if routes exist.
    """
    if db.session.scalar(select(RouteRecord.route_id).limit(1)) is not None:
        return
    db.session.add_all(route.to_record() for route in default_routes())
    db.session.add_all(bus.to_record() for bus in default_buses())
    if with_demo_drivers:
        db.session.add_all(driver.to_record() for driver in demo_drivers())
    db.session.commit()


def record_rider(role: str, rider_id: str, full_name: str) -> None:
    """Remember a student/teacher who opened the map (insert, or refresh name and last-seen time)."""
    now = utc_now_iso()
    rider = db.session.scalar(select(RiderRecord).filter_by(role=role, rider_id=rider_id))
    if rider is None:
        db.session.add(RiderRecord(role=role, rider_id=rider_id, full_name=full_name,
                                   first_seen_at=now, last_seen_at=now))
    else:
        rider.full_name = full_name
        rider.last_seen_at = now
    db.session.commit()


def list_riders() -> list[dict]:
    """Students and teachers, most recently seen first (for the admin's Users tab)."""
    rows = db.session.scalars(select(RiderRecord).order_by(RiderRecord.last_seen_at.desc()))
    return [{"role": r.role, "rider_id": r.rider_id, "full_name": r.full_name,
             "first_seen_at": r.first_seen_at, "last_seen_at": r.last_seen_at} for r in rows]

