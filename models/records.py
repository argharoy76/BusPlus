"""
Database tables (Flask-SQLAlchemy).

Only what the admin sets up is saved here, so it survives restarts and updates:
routes, buses, drivers, and the students/teachers who have signed in.

Live data (where each bus is right now, its speed, its trail) changes every
second and is kept in memory by `services.tracking_service` instead.

Dates are stored as ISO-8601 text in UTC (for example "2026-10-31T08:15:00+00:00").
"""

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
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


class DriverRecord(db.Model):
    """A driver account created by the admin. The PIN is stored only as a hash."""

    __tablename__ = "drivers"

    driver_id: Mapped[str] = mapped_column(String(20), primary_key=True)       # e.g. "DRV-01"
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(60), unique=True)            # drivers sign in with it
    phone: Mapped[str] = mapped_column(String(30), default="")
    pin_hash: Mapped[str] = mapped_column(String(255))
    bus_id: Mapped[str | None] = mapped_column(ForeignKey("buses.bus_id"), nullable=True)
    assignment_updated_at: Mapped[str | None] = mapped_column(String(40))      # admin changed bus/route
    assignment_seen_at: Mapped[str | None] = mapped_column(String(40))         # driver read the change
    session_token: Mapped[str | None] = mapped_column(String(64))              # phone holding the account
    last_login_at: Mapped[str | None] = mapped_column(String(40))


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
