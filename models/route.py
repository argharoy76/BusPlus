"""
Routes and the named places (stops) along them.

`BusRoute` is the in-memory form used while the app runs. It is loaded from and
saved to the `routes` table (models/records.py). Every route ends at the final
destination set in `Config.FINAL_DESTINATION` (Hadi Chattar).
"""

import difflib
from dataclasses import asdict, dataclass, field

from config import Config
from models.records import RouteRecord
from services.geo import path_length_km

FINAL_STOP_NAME = Config.FINAL_DESTINATION["stop_name"]
FINAL_POINT = {"lat": Config.FINAL_DESTINATION["latitude"], "lng": Config.FINAL_DESTINATION["longitude"]}


@dataclass
class BusStop:
    """A named place on a route (for example "Malabotha More")."""

    stop_name: str
    latitude: float
    longitude: float
    sequence_order: int                  # 1 = first place on the route
    scheduled_morning_time: str = ""     # e.g. "08:35 AM" (optional)
    landmark_hint: str = ""              # e.g. "Bazar Bus Stand" (optional)

    def to_dict(self) -> dict:
        """JSON form of the stop."""
        return asdict(self)


@dataclass
class BusRoute:
    """
    A route as drawn by the admin.

    polyline_waypoints: the road line the bus drives, [{"lat", "lng"}, ...]
    via_points:         the points the admin clicked to steer that line
    stops:              named places along it; the last one is always Hadi Chattar
    """

    route_id: str
    route_name: str
    route_code: str
    color_hex: str
    stops: list[BusStop] = field(default_factory=list)
    polyline_waypoints: list[dict] = field(default_factory=list)
    via_points: list[dict] = field(default_factory=list)

    # ---------------------------------------------------------------- output
    def to_dict(self) -> dict:
        """JSON form sent to the browser."""
        return {
            "route_id": self.route_id,
            "route_name": self.route_name,
            "route_code": self.route_code,
            "color_hex": self.color_hex,
            "stops": [stop.to_dict() for stop in self.stops],
            "polyline_waypoints": self.polyline_waypoints,
            "via_points": self.via_points,
            "length_km": round(path_length_km(self.polyline_waypoints), 2),
        }

    # ---------------------------------------------------------------- lookups
    def get_stop_by_name(self, name: str) -> BusStop | None:
        """
        Find a stop by name, forgiving small differences.

        Tries, in order: exact match, one name containing the other
        ("PTI" -> "PTI More"), a close spelling (difflib), and finally the same
        first word ("Malabotha Bazar" -> "Malabotha More").
        """
        wanted = (name or "").strip().lower()
        if not wanted:
            return None
        by_name = {stop.stop_name.lower(): stop for stop in self.stops}
        if wanted in by_name:
            return by_name[wanted]
        for stop_name, stop in by_name.items():
            if wanted in stop_name or stop_name in wanted:
                return stop
        close = difflib.get_close_matches(wanted, by_name.keys(), n=1, cutoff=0.75)
        if close:
            return by_name[close[0]]
        first_word = wanted.split()[0]
        return next((stop for stop_name, stop in by_name.items() if stop_name.split()[0] == first_word), None)

    # ---------------------------------------------------------------- rules
    def end_at_final_destination(self) -> None:
        """Make sure the last stop and the last point of the line are Hadi Chattar."""
        if not self.stops or self.stops[-1].stop_name != FINAL_STOP_NAME:
            last_time = self.stops[-1].scheduled_morning_time if self.stops else ""
            dest = Config.FINAL_DESTINATION
            self.stops.append(BusStop(
                stop_name=dest["stop_name"],
                latitude=dest["latitude"],
                longitude=dest["longitude"],
                sequence_order=len(self.stops) + 1,
                scheduled_morning_time=last_time,
                landmark_hint=dest["landmark_hint"],
            ))
        if not self.polyline_waypoints or self.polyline_waypoints[-1] != FINAL_POINT:
            self.polyline_waypoints.append(dict(FINAL_POINT))

    # ---------------------------------------------------------------- database
    @classmethod
    def from_record(cls, record: RouteRecord) -> "BusRoute":
        """Build the in-memory route from its database row."""
        route = cls(
            route_id=record.route_id,
            route_name=record.route_name,
            route_code=record.route_code,
            color_hex=record.color_hex,
            stops=[BusStop(**stop) for stop in record.stops or []],
            polyline_waypoints=list(record.path or []),
            via_points=list(record.via_points or []),
        )
        route.end_at_final_destination()
        return route

    def to_record(self) -> RouteRecord:
        """Database row for this route (saved with `db.session.merge`)."""
        return RouteRecord(
            route_id=self.route_id,
            route_name=self.route_name,
            route_code=self.route_code,
            color_hex=self.color_hex,
            stops=[stop.to_dict() for stop in self.stops],
            path=self.polyline_waypoints,
            via_points=self.via_points,
        )
