"""
Small helpers for saving to and reading from the database.

The services keep a fast in-memory copy of routes, buses and GPS devices, and use
these helpers to write every admin change straight through to the database.
All functions must run inside a Flask app context (any request handler does).
"""

from datetime import UTC, datetime

from sqlalchemy import inspect, select, text

from extensions import db
from models.records import ADDED_COLUMNS, RiderRecord, RouteRecord
from models.seed_data import default_buses, default_routes


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


def upgrade_tables() -> None:
    """
    Add columns that newer versions of BusPlus need to an older database (ADDED_COLUMNS in
    models/records.py). `db.create_all()` makes missing tables but never changes existing ones.
    """
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    for table, columns in ADDED_COLUMNS.items():
        if table not in tables:
            continue
        have = {column["name"] for column in inspector.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in have:
                db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
    db.session.commit()


def seed_defaults() -> None:
    """Fill an empty database with the built-in KU routes and buses. Does nothing if routes exist."""
    if db.session.scalar(select(RouteRecord.route_id).limit(1)) is not None:
        return
    db.session.add_all(route.to_record() for route in default_routes())
    db.session.add_all(bus.to_record() for bus in default_buses())
    db.session.commit()


def record_rider(role: str, rider_id: str, full_name: str) -> None:
    """
    Remember a student/teacher who opened the map (insert, or refresh the last-seen time).
    The name from the first sign-in is kept, so someone typing another person's ID can't rename them.
    """
    now = utc_now_iso()
    rider = db.session.scalar(select(RiderRecord).filter_by(role=role, rider_id=rider_id))
    if rider is None:
        db.session.add(RiderRecord(role=role, rider_id=rider_id, full_name=full_name,
                                   first_seen_at=now, last_seen_at=now))
    else:
        rider.last_seen_at = now
    db.session.commit()


def list_riders() -> list[dict]:
    """Students and teachers, most recently seen first (for the admin's Users tab)."""
    rows = db.session.scalars(select(RiderRecord).order_by(RiderRecord.last_seen_at.desc()))
    return [{"role": r.role, "rider_id": r.rider_id, "full_name": r.full_name,
             "first_seen_at": r.first_seen_at, "last_seen_at": r.last_seen_at} for r in rows]

