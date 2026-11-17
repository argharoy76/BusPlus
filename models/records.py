"""
Database tables (Flask-SQLAlchemy).

Only what the admin sets up is saved here, so it survives restarts and updates:
routes, buses, the GPS devices fitted to them, and the riders who have signed in.

Live data (where each bus is right now, its speed, its trail) changes every
second and is kept in memory by `services.tracking_service` instead.

Dates are stored as ISO-8601 text in UTC (for example "2026-10-31T08:15:00+00:00").
"""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class RouteRecord(db.Model):
    """A bus route: its name, colour, road line and named places along it."""

    __tablename__ = "routes"

    route_id: Mapped[str] = mapped_column(String(20), primary_key=True)        # e.g. "KU-R01"
    route_name: Mapped[str] = mapped_column(String(80))                       # what everyone sees
    route_code: Mapped[str] = mapped_column(String(30))                       # short label, e.g. "R1"
    color_hex: Mapped[str] = mapped_column(String(7))                         # line colour, e.g. "#2563EB"
    stops: Mapped[list] = mapped_column(JSON, default=list)                   # [{stop_name, latitude, ...}]
    path: Mapped[list] = mapped_column(JSON, default=list)                    # road line [{lat, lng}, ...]
    via_points: Mapped[list] = mapped_column(JSON, default=list)              # points the admin clicked


class BusRecord(db.Model):
    """A bus and which route it drives today."""

    __tablename__ = "buses"

    bus_id: Mapped[str] = mapped_column(String(20), primary_key=True)          # e.g. "KU-BUS-01"
    bus_number: Mapped[str] = mapped_column(String(40))                       # e.g. "KU Bus #01" (staff only)
    bus_name: Mapped[str] = mapped_column(String(60))                         # what students see
    license_plate: Mapped[str] = mapped_column(String(40), default="")
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.route_id"))
    color_hex: Mapped[str] = mapped_column(String(7))                         # marker colour on the map
    capacity: Mapped[int] = mapped_column(Integer, default=52)
    audience: Mapped[str] = mapped_column(String(20))                         # rider type, e.g. "student"


class RiderRecord(db.Model):
    """A student or teacher who has opened the live map (shown to the admin)."""

    __tablename__ = "riders"
    __table_args__ = (UniqueConstraint("role", "rider_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20))                              # rider type, e.g. "student"
    rider_id: Mapped[str] = mapped_column(String(40))                          # student / teacher ID
    full_name: Mapped[str] = mapped_column(String(60))
    first_seen_at: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[str] = mapped_column(String(40))


class TimetableRecord(db.Model):
    """
    The bus timetable of one route, set day by day in the backend.

    days: {"sat": {"morning":   [{"bus_id": "KU-BUS-01", "time": "08:50"}, ...],   # reaches campus
                   "afternoon": [{"bus_id": "KU-BUS-01", "time": "14:30"}, ...]},  # leaves campus
           "sun": {...}, ...}        a day that is missing or empty = no bus that day
    Times are 24-hour "HH:MM".
    """

    __tablename__ = "route_timetables"

    route_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    days: Mapped[dict] = mapped_column(JSON, default=dict)


class GpsDeviceRecord(db.Model):
    """
    A GPS tracker box (ESP32 + NEO-6M) fitted to a bus. See services/device_service.py.

    The device proves who it is with a secret key. Only a SHA-256 hash of the key is
    stored, so the key itself is shown to the admin once (when it is made) and never again.
    """

    __tablename__ = "gps_devices"

    device_id: Mapped[str] = mapped_column(String(20), primary_key=True)       # e.g. "GPS-01"
    name: Mapped[str] = mapped_column(String(60))                             # e.g. "Tracker in Bus #01"
    bus_id: Mapped[str | None] = mapped_column(ForeignKey("buses.bus_id"), nullable=True, unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)            # sha256 of the secret key
    key_hint: Mapped[str] = mapped_column(String(8), default="")              # last 4 letters, to tell keys apart
    created_at: Mapped[str] = mapped_column(String(40))
    chip_id: Mapped[str | None] = mapped_column(String(20), nullable=True)    # ESP32 chip ID, when it joined by itself
    show_on_map: Mapped[bool] = mapped_column(Boolean, default=True)          # False: its bus is kept off every map


# Columns added after the first release. `store.upgrade_tables()` adds them to an older database.
#   table -> {column: SQL type and default}
ADDED_COLUMNS = {
    "gps_devices": {
        "chip_id": "VARCHAR(20)",
        "show_on_map": "BOOLEAN NOT NULL DEFAULT 1",
    },
}
