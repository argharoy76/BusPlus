"""
Routes, buses and live bus tracking.

`TrackingService` keeps every route and bus in memory so the live map is fast:
  * Admin changes (add/edit/delete a route or bus) are written to the database
    straight away (services/store.py) and survive restarts.
  * Live data (GPS position, speed, trail, online/offline) is memory only.

Open maps follow the buses through a "version" number: every bus change bumps
it and wakes up `wait_for_change()`, which the live stream (/api/buses/stream)
uses to push updates within milliseconds.

All public methods are thread-safe (one re-entrant lock guards the state).
"""

import re
import threading
import time
import uuid
from itertools import pairwise

from content import colors, rules
from models.bus import BUS_AUDIENCES, Bus
from models.records import BusRecord, RouteRecord
from models.route import FINAL_STOP_NAME, BusRoute, BusStop
from services import geo, store
from services.words import say

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TIME_RE = re.compile(r"^(0?[1-9]|1[0-2]):[0-5]\d\s?(AM|PM)$", re.IGNORECASE)

# Colours offered to new buses and new routes (the first unused one is picked): content/colors.py
BUS_COLOR_PALETTE = colors.BUS_COLORS
ROUTE_COLOR_PALETTE = colors.ROUTE_COLORS

TRAIL_MIN_STEP_KM = rules.TRAIL_MIN_STEP_KM   # ignore GPS wobble smaller than this when drawing the trail
TRAIL_MAX_POINTS = rules.TRAIL_MAX_POINTS     # keep at most this many trail points per bus
AT_STOP_RADIUS_KM = 0.2       # closer than this to a stop = "at the stop"

SIMULATION_TICK_S = 1.0       # test drive: one position update per second
SIMULATION_SPEED_KMH = 30.0   # test drive: base speed before the speed multiplier


class TrackingService:
    """All routes and buses, their live state, and the live-update signal (one instance per process)."""
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)   # wakes live streams on any bus change
        self._routes: dict[str, BusRoute] = {}
        self._buses: dict[str, Bus] = {}
        self._trails: dict[str, list[list[float]]] = {}   # bus_id -> [[lat, lng], ...] of this trip
        self._simulation_runs: dict[str, str] = {}        # bus_id -> id of its one running test drive
        self._simulation_threads: dict[str, threading.Thread] = {}
        self._version = 0

    # =====================================================================
    # Start-up
    # =====================================================================
    def load(self) -> None:
        """(Re)load routes and buses from the database. Called once by create_app()."""
        with self._lock:
            self._simulation_runs.clear()          # any running test drive stops by itself
            self._routes = {r.route_id: BusRoute.from_record(r) for r in store.all_rows(RouteRecord)}
            self._buses = {b.bus_id: Bus.from_record(b) for b in store.all_rows(BusRecord)}
            self._trails.clear()
            for bus in self._buses.values():
                self._park_at_route_start(bus)
            self._bump()

    # =====================================================================
    # Routes
    # =====================================================================
    def all_routes(self) -> list[dict]:
        """Every route as JSON-ready dicts."""
        with self._lock:
            return [route.to_dict() for route in self._routes.values()]

    def get_route(self, route_id: str | None) -> BusRoute | None:
        """The route with this ID, or None."""
        with self._lock:
            return self._routes.get(route_id or "")

    def create_route(self, data: dict) -> dict:
        """Add a route from the admin's route editor. Raises ValueError with a readable message."""
        with self._lock:
            clean = self._clean_route_fields(data, creating=True)
            route_id = self._next_free_id("KU-R", self._routes)
            used_colors = {r.color_hex.upper() for r in self._routes.values()}
            route = BusRoute(
                route_id=route_id,
                route_name=clean["route_name"],
                route_code=clean.get("route_code") or f"R{int(route_id[-2:])}",
                color_hex=clean.get("color_hex") or _first_unused(ROUTE_COLOR_PALETTE, used_colors),
            )
            self._apply_points(route, clean["points"], clean["path"])
            self._routes[route_id] = route
            store.save(route.to_record())
            self._bump()
            return route.to_dict()

    def update_route(self, route_id: str, data: dict) -> dict | None:
        """Edit a route (name, colour and/or its line). Returns None if it doesn't exist."""
        with self._lock:
            route = self._routes.get(route_id)
            if route is None:
                return None
            clean = self._clean_route_fields(data, creating=False)
            for key in ("route_name", "route_code", "color_hex"):
                if key in clean:
                    setattr(route, key, clean[key])
            if "points" in clean:
                self._apply_points(route, clean["points"], clean["path"])
            store.save(route.to_record())
            self._bump()
            return route.to_dict()

    def delete_route(self, route_id: str) -> bool:
        """Remove a route. Refused (ValueError) while any bus still uses it."""
        with self._lock:
            if route_id not in self._routes:
                return False
            in_use = [b.bus_number for b in self._buses.values() if b.assigned_route_id == route_id]
            if in_use:
                raise ValueError(say("{buses} use this route. Move them to another route in Buses first.",
                                     buses=", ".join(in_use)))
            del self._routes[route_id]
            store.delete(RouteRecord, route_id)
            self._bump()
            return True

    def _clean_route_fields(self, data: dict, creating: bool) -> dict:
        """
        Check the route editor's form.

        Expected: {"route_name": str, "color_hex": "#RRGGBB",
                   "points": [{"lat", "lng", "name"?, "time"?}, ...],   # clicked on the map
                   "path":   [[lat, lng], ...]}                          # road line (optional)
        """
        clean: dict = {}
        name = str(data.get("route_name") or "").strip()
        if creating and not name:
            raise ValueError(say("Route name is required."))
        if name:
            clean["route_name"] = name[:80]
        if data.get("route_code"):
            clean["route_code"] = str(data["route_code"]).strip()[:30]
        if data.get("color_hex"):
            clean["color_hex"] = _clean_color(data["color_hex"], say("Route colour must look like #2563EB."))

        if creating or "points" in data:
            raw_points = data.get("points") or []
            if not isinstance(raw_points, list):
                raise ValueError(say("Route points must be a list."))
            points = []
            for i, point in enumerate(raw_points, start=1):
                if not isinstance(point, dict):
                    raise ValueError(say("Point {number} is not valid.", number=i))
                point_name = str(point.get("name") or "").strip()
                if point_name.lower() == FINAL_STOP_NAME.lower():
                    continue                      # Hadi Chattar is always added at the end anyway
                lat, lng = _clean_position(point.get("lat"), point.get("lng"), say("Point {number}", number=i))
                time_txt = str(point.get("time") or "").strip().upper()
                if time_txt and not TIME_RE.match(time_txt):
                    raise ValueError(say("Time for point {number} must look like 08:35 AM.", number=i))
                points.append({"name": point_name[:60], "lat": lat, "lng": lng, "time": time_txt})
            if not points:
                raise ValueError(say("Click the map to draw the route."))
            clean["points"] = points
            clean["path"] = _clean_path(data.get("path"))
        return clean

    @staticmethod
    def _apply_points(route: BusRoute, points: list[dict], path: list[dict] | None) -> None:
        """
        Rebuild a route from the admin's points:
          * the line follows the road path from the editor (or straight lines if there is none)
          * points that have a name become the route's stops; Hadi Chattar is always last
        """
        route.via_points = [{"lat": p["lat"], "lng": p["lng"], "name": p["name"]} for p in points]
        named = [p for p in points if p["name"]]
        route.stops = [
            BusStop(stop_name=p["name"], latitude=p["lat"], longitude=p["lng"],
                    sequence_order=i, scheduled_morning_time=p["time"])
            for i, p in enumerate(named, start=1)
        ]
        route.polyline_waypoints = path or [{"lat": p["lat"], "lng": p["lng"]} for p in points]
        route.end_at_final_destination()

    # =====================================================================
    # Buses (admin setup)
    # =====================================================================
    def all_buses(self, audience: str | None = None) -> list[dict]:
        """
        Every bus (or only the student / teacher buses) as JSON-ready dicts, with
        its route's name and colour, and the trail of its current trip while it is live.
        """
        with self._lock:
            return [self._bus_dict(bus) for bus in self._buses.values()
                    if audience is None or bus.audience == audience]

    def get_bus(self, bus_id: str | None) -> Bus | None:
        """The bus with this ID, or None."""
        with self._lock:
            return self._buses.get(bus_id or "")

    def buses_on_route(self, route_id: str, audience: str | None = None) -> list[Bus]:
        """Buses currently assigned to a route (optionally only those for students or teachers)."""
        with self._lock:
            return [b for b in self._buses.values()
                    if b.assigned_route_id == route_id and (audience is None or b.audience == audience)]

    def create_bus(self, data: dict) -> dict:
        """Add a bus. It waits at the start of its route. Raises ValueError on bad input."""
        with self._lock:
            clean = self._clean_bus_fields(data, creating=True)
            used_colors = {b.color_hex.upper() for b in self._buses.values()}
            bus = Bus(
                bus_id=self._next_free_id("KU-BUS-", self._buses),
                bus_number=clean["bus_number"],
                bus_name=clean.get("bus_name") or clean["bus_number"],
                license_plate=clean.get("license_plate", ""),
                assigned_route_id=clean["assigned_route_id"],
                color_hex=clean.get("color_hex") or _first_unused(BUS_COLOR_PALETTE, used_colors),
                capacity=clean.get("capacity", rules.DEFAULT_BUS_SEATS),
                audience=clean.get("audience", BUS_AUDIENCES[0]),
            )
            self._park_at_route_start(bus)
            self._buses[bus.bus_id] = bus
            store.save(bus.to_record())
            self._bump()
            return self._bus_dict(bus)

    def update_bus(self, bus_id: str, data: dict) -> dict | None:
        """Edit a bus. Its route can't change during a live trip. Returns None if it doesn't exist."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None
            clean = self._clean_bus_fields(data, creating=False)
            route_changed = clean.get("assigned_route_id", bus.assigned_route_id) != bus.assigned_route_id
            if route_changed and bus.is_active:
                raise ValueError(say("{bus} is on a live trip. Stop the trip before changing its route.",
                                     bus=bus.bus_number))
            for key, value in clean.items():
                setattr(bus, key, value)
            if route_changed:
                self._park_at_route_start(bus)
            store.save(bus.to_record())
            self._bump()
            return self._bus_dict(bus)

    def delete_bus(self, bus_id: str) -> bool:
        """Remove a bus. Refused (ValueError) while it is on a live trip."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return False
            if bus.is_active:
                raise ValueError(say("{bus} is on a live trip. Stop the trip before deleting it.", bus=bus.bus_number))
            del self._buses[bus_id]
            self._trails.pop(bus_id, None)
            store.delete(BusRecord, bus_id)
            self._bump()
            return True

    def show_driver_on_bus(self, driver_id: str, driver_name: str | None, bus_id: str | None) -> None:
        """Show a driver on their bus (and on no other bus). bus_id=None just removes them."""
        with self._lock:
            for bus in self._buses.values():
                if bus.driver_id == driver_id:
                    bus.driver_id = bus.driver_name = None
            bus = self._buses.get(bus_id or "")
            if bus is not None:
                bus.driver_id, bus.driver_name = driver_id, driver_name
            self._bump()

    def _clean_bus_fields(self, data: dict, creating: bool) -> dict:
        """Check the bus form from the admin panel. Raises ValueError with a readable message."""
        clean: dict = {}
        for key, limit in (("bus_number", 40), ("bus_name", 60), ("license_plate", 40)):
            if data.get(key) is not None:
                clean[key] = str(data[key]).strip()[:limit]
        if (creating or "bus_number" in clean) and not clean.get("bus_number"):
            raise ValueError(say("Bus number is required (e.g. KU Bus #05)."))

        if data.get("assigned_route_id"):
            route_id = str(data["assigned_route_id"]).strip()
            if route_id not in self._routes:
                raise ValueError(say("Route {id} doesn't exist.", id=route_id))
            clean["assigned_route_id"] = route_id
        elif creating:
            raise ValueError(say("Please choose a route for the bus."))

        if data.get("color_hex"):
            clean["color_hex"] = _clean_color(data["color_hex"], say("Colour must look like #E11D48."))

        if data.get("audience"):
            audience = str(data["audience"]).strip().lower()
            if audience not in BUS_AUDIENCES:
                raise ValueError(say("A bus must be for one of: {types}.", types=", ".join(BUS_AUDIENCES)))
            clean["audience"] = audience

        if data.get("capacity") not in (None, ""):
            try:
                capacity = int(data["capacity"])
            except (TypeError, ValueError):
                raise ValueError(say("Capacity must be a whole number.")) from None
            if not 1 <= capacity <= rules.MAX_BUS_SEATS:
                raise ValueError(say("Capacity must be between 1 and {max}.", max=rules.MAX_BUS_SEATS))
            clean["capacity"] = capacity
        return clean

    # =====================================================================
    # Live tracking (driver's phone)
    # =====================================================================
    def update_location(self, bus_id: str, latitude: float, longitude: float,
                        speed_kmh: float | None = None, heading_deg: float | None = None,
                        trip_status: str = "EN_ROUTE") -> dict | None:
        """
        Record a GPS position from the driver's phone (or a test drive).

        Missing speed is worked out from the distance since the last position,
        missing heading from the direction of travel. Also extends the bus's
        trail and works out its next stop. Returns the bus, or None if unknown.
        """
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None

            if speed_kmh is None and bus.is_active and bus.last_update_ts:
                seconds = time.time() - bus.last_update_ts
                if 1.0 <= seconds <= 120.0:
                    km = geo.distance_km(bus.current_latitude, bus.current_longitude, latitude, longitude)
                    speed_kmh = min(120.0, km / (seconds / 3600.0))

            moved = (bus.current_latitude, bus.current_longitude) != (latitude, longitude)
            if heading_deg is None and moved:
                heading_deg = geo.bearing_deg(bus.current_latitude, bus.current_longitude, latitude, longitude)

            if not bus.is_active:
                self._trails[bus_id] = []          # a new trip starts a new trail
            bus.move_to(latitude, longitude, speed_kmh, heading_deg, trip_status)
            self._add_trail_point(bus_id, latitude, longitude)
            self._update_next_stop(bus)
            self._bump()
            return bus.to_dict()

    def start_trip(self, bus_id: str) -> dict | None:
        """Driver went online: the bus shows on the maps from its next GPS position."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None
            if not bus.is_active:
                self._trails[bus_id] = []
            bus.is_active = True
            bus.trip_status = "EN_ROUTE"
            self._bump()
            return bus.to_dict()

    def stop_trip(self, bus_id: str) -> dict | None:
        """Driver went offline (or logged out): hide the bus, clear its trail, end any test drive."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None
            self._simulation_runs.pop(bus_id, None)
            bus.is_active = bus.is_simulating = False
            bus.trip_status = "IDLE"
            bus.speed_kmh = 0.0
            self._trails.pop(bus_id, None)
            self._bump()
            return bus.to_dict()

    def _update_next_stop(self, bus: Bus) -> None:
        """Work out which stop the bus is heading for (the nearest one, or the one after it if already there)."""
        route = self._routes.get(bus.assigned_route_id)
        if route is None or not route.stops:
            return
        distances = [geo.distance_km(bus.current_latitude, bus.current_longitude, s.latitude, s.longitude)
                     for s in route.stops]
        nearest = min(range(len(distances)), key=distances.__getitem__)
        if distances[nearest] < AT_STOP_RADIUS_KM and nearest + 1 < len(route.stops):
            nearest += 1
        bus.current_stop_index = nearest
        bus.next_stop_name = route.stops[nearest].stop_name

    def _park_at_route_start(self, bus: Bus) -> None:
        """Place an idle bus at the first point of its route."""
        route = self._routes.get(bus.assigned_route_id)
        if route and route.stops:
            first = route.stops[0]
            bus.current_latitude, bus.current_longitude = first.latitude, first.longitude
            bus.current_stop_index = 0
            bus.next_stop_name = first.stop_name

    def _bus_dict(self, bus: Bus) -> dict:
        """A bus as JSON, with its route's name/colour and (while live) its trail."""
        data = bus.to_dict()
        route = self._routes.get(bus.assigned_route_id)
        data["route_name"] = route.route_name if route else None
        data["route_code"] = route.route_code if route else None
        data["route_color"] = route.color_hex if route else None
        data["trail"] = list(self._trails.get(bus.bus_id, [])) if bus.is_active else []
        return data

    # =====================================================================
    # Trail: the red line a bus leaves behind on its current trip
    # =====================================================================
    def _add_trail_point(self, bus_id: str, lat: float, lng: float) -> None:
        """Add a GPS point to the red trail behind a bus (skips tiny GPS wobbles, keeps the newest points)."""
        trail = self._trails.setdefault(bus_id, [])
        if trail and geo.distance_km(trail[-1][0], trail[-1][1], lat, lng) < TRAIL_MIN_STEP_KM:
            return
        trail.append([round(lat, 6), round(lng, 6)])
        del trail[:-TRAIL_MAX_POINTS]

    # =====================================================================
    # Live updates for open maps
    # =====================================================================
    def _bump(self) -> None:
        """Note that something changed and wake every waiting live stream (lock must be held)."""
        self._version += 1
        self._changed.notify_all()

    def get_version(self) -> int:
        """Current change counter (goes up by one on every bus or route change)."""
        with self._lock:
            return self._version

    def wait_for_change(self, since_version: int, timeout: float = 15.0) -> int:
        """Block until something changes after `since_version` (or `timeout` seconds). Returns the new version."""
        with self._changed:
            if self._version == since_version:
                self._changed.wait(timeout)
            return self._version

    # =====================================================================
    # Test drive (admin): move a bus along its route without a phone
    # =====================================================================
    def start_simulation(self, bus_id: str, speed_multiplier: float = 1.0) -> bool:
        """Start a background test drive from the route's start to Hadi Chattar. False if not possible."""
        with self._lock:
            bus = self._buses.get(bus_id)
            route = self._routes.get(bus.assigned_route_id) if bus else None
            if bus is None or route is None or len(route.polyline_waypoints) < 2:
                return False
            run_id = uuid.uuid4().hex                 # replaces any test drive already running
            self._simulation_runs[bus_id] = run_id
            bus.is_simulating = bus.is_active = True
            bus.trip_status = "EN_ROUTE"
            self._park_at_route_start(bus)
            self._trails[bus_id] = [[bus.current_latitude, bus.current_longitude]]
            self._bump()
            line = [(p["lat"], p["lng"]) for p in route.polyline_waypoints]
            thread = threading.Thread(target=self._drive_along, args=(bus_id, line, speed_multiplier, run_id),
                                      daemon=True, name=f"test-drive-{bus_id}")
            self._simulation_threads[bus_id] = thread
            thread.start()
            return True

    def _drive_along(self, bus_id: str, line: list[tuple[float, float]], speed_multiplier: float,
                     run_id: str) -> None:
        """
        Background thread of a test drive: moves the bus along `line` at a steady
        speed, one update per tick, then parks it at the end (Hadi Chattar).
        Stops early if the trip is stopped or a newer test drive starts.
        """
        def still_running() -> bool:
            return self._simulation_runs.get(bus_id) == run_id

        step_km = SIMULATION_SPEED_KMH / 3600.0 * SIMULATION_TICK_S * max(0.1, speed_multiplier)
        carry_km = 0.0                                # distance already gone into the next segment
        for i, ((lat1, lng1), (lat2, lng2)) in enumerate(pairwise(line)):
            segment_km = geo.distance_km(lat1, lng1, lat2, lng2)
            if segment_km <= 0:
                continue
            heading = geo.bearing_deg(lat1, lng1, lat2, lng2)
            position_km = carry_km
            while position_km < segment_km:
                if not still_running():
                    return
                t = position_km / segment_km
                self.update_location(bus_id, lat1 + (lat2 - lat1) * t, lng1 + (lng2 - lng1) * t,
                                     speed_kmh=SIMULATION_SPEED_KMH + (i % 4) * 2.0, heading_deg=heading)
                time.sleep(SIMULATION_TICK_S)
                position_km += step_km
            carry_km = position_km - segment_km

        with self._lock:
            if not still_running():
                return
            end_lat, end_lng = line[-1]
            self.update_location(bus_id, end_lat, end_lng, speed_kmh=0.0, trip_status="ARRIVED")
            self._buses[bus_id].is_simulating = False
            self._simulation_runs.pop(bus_id, None)
            self._bump()

    # =====================================================================
    # Helpers
    # =====================================================================
    @staticmethod
    def _next_free_id(prefix: str, taken: dict) -> str:
        """Next unused ID such as KU-BUS-05 (never reuses an ID that is still in use)."""
        n = 1
        while f"{prefix}{n:02d}" in taken:
            n += 1
        return f"{prefix}{n:02d}"


def _first_unused(palette: list[str], used: set[str]) -> str:
    """First colour of the palette not used yet (or the first colour if all are used)."""
    return next((c for c in palette if c.upper() not in used), palette[0])


def _clean_color(value, message: str) -> str:
    """A colour like "#2563EB", or ValueError(message) if it isn't one."""
    color = str(value).strip()
    if not HEX_COLOR_RE.match(color):
        raise ValueError(message)
    return color.upper()


def _clean_position(lat, lng, label: str) -> tuple[float, float]:
    """Turn a latitude/longitude pair into floats, refusing missing or out-of-country values."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        raise ValueError(say("{place} needs a map position.", place=label)) from None
    if not geo.in_bangladesh(lat, lng):
        raise ValueError(say("{place} is outside Bangladesh.", place=label))
    return lat, lng


def _clean_path(path) -> list[dict] | None:
    """Check the road line from the route editor: [[lat, lng], ...] -> [{"lat", "lng"}, ...]."""
    if not path:
        return None
    if not isinstance(path, list) or not 2 <= len(path) <= 20000:
        raise ValueError(say("The route line is not valid."))
    clean = []
    for point in path:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(say("The route line is not valid."))
        lat, lng = _clean_position(point[0], point[1], say("The route line"))
        clean.append({"lat": round(lat, 6), "lng": round(lng, 6)})
    return clean
