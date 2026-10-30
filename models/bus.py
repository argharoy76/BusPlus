"""
A bus: the details the admin sets up, plus where it is right now.

The setup part (number, name, route, colour, ...) is saved in the `buses` table.
The live part (position, speed, trip status, ...) only lives in memory and is
updated by the driver's phone about once a second.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from config import Config
from models.records import BusRecord

BUS_AUDIENCES = ("student", "teacher")   # who may see a bus on their map


@dataclass
class Bus:
    """One bus: its setup (saved in the database) and its live state (memory only)."""
    # ---- set up by the admin (saved in the database) ----
    bus_id: str
    bus_number: str                      # staff label, e.g. "KU Bus #01"
    bus_name: str                        # what students and teachers see
    assigned_route_id: str
    license_plate: str = ""
    color_hex: str = "#0866FF"           # the bus's own marker colour
    capacity: int = 52
    audience: str = "student"            # "student" or "teacher"

    # ---- the driver assigned to it (kept in step by the driver setup) ----
    driver_id: str | None = None
    driver_name: str | None = None

    # ---- live state (memory only) ----
    current_latitude: float = Config.UNIVERSITY_LOCATION["latitude"]
    current_longitude: float = Config.UNIVERSITY_LOCATION["longitude"]
    speed_kmh: float = 0.0
    heading_deg: float = 0.0
    is_active: bool = False              # True while the driver is online and sending GPS
    is_simulating: bool = False          # True during an admin "test drive"
    trip_status: str = "IDLE"            # IDLE, EN_ROUTE or ARRIVED
    current_stop_index: int = 0          # index of the next stop on the route
    next_stop_name: str = ""
    last_update_ts: float = 0.0          # Unix time of the last GPS update

    def move_to(self, latitude: float, longitude: float, speed_kmh: float | None,
                heading_deg: float | None, trip_status: str) -> None:
        """Record a new GPS position. Missing speed/heading keep their previous values."""
        self.current_latitude = float(latitude)
        self.current_longitude = float(longitude)
        if speed_kmh is not None:
            self.speed_kmh = max(0.0, float(speed_kmh))
        if heading_deg is not None:
            self.heading_deg = float(heading_deg) % 360.0
        self.trip_status = trip_status
        self.is_active = True
        self.last_update_ts = time.time()

    def to_dict(self) -> dict:
        """JSON form sent to the browser (no private driver details such as phone numbers)."""
        return {
            "bus_id": self.bus_id,
            "bus_number": self.bus_number,
            "bus_name": self.bus_name,
            "license_plate": self.license_plate,
            "assigned_route_id": self.assigned_route_id,
            "color_hex": self.color_hex,
            "capacity": self.capacity,
            "audience": self.audience,
            "driver_id": self.driver_id,
            "driver_name": self.driver_name,
            "current_latitude": self.current_latitude,
            "current_longitude": self.current_longitude,
            "speed_kmh": round(self.speed_kmh, 1),
            "heading_deg": self.heading_deg,
            "is_active": self.is_active,
            "is_simulating": self.is_simulating,
            "trip_status": self.trip_status,
            "current_stop_index": self.current_stop_index,
            "next_stop_name": self.next_stop_name,
            "last_updated_iso": (datetime.fromtimestamp(self.last_update_ts, UTC).isoformat()
                                 if self.last_update_ts else None),
        }

    # ---------------------------------------------------------------- database
    @classmethod
    def from_record(cls, record: BusRecord) -> "Bus":
        """Build the in-memory bus from its database row (live state starts empty)."""
        return cls(
            bus_id=record.bus_id,
            bus_number=record.bus_number,
            bus_name=record.bus_name,
            assigned_route_id=record.route_id,
            license_plate=record.license_plate or "",
            color_hex=record.color_hex,
            capacity=record.capacity,
            audience=record.audience,
        )

    def to_record(self) -> BusRecord:
        """Database row for this bus's setup (saved with `db.session.merge`)."""
        return BusRecord(
            bus_id=self.bus_id,
            bus_number=self.bus_number,
            bus_name=self.bus_name,
            license_plate=self.license_plate,
            route_id=self.assigned_route_id,
            color_hex=self.color_hex,
            capacity=self.capacity,
            audience=self.audience,
        )
