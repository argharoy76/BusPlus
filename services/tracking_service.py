"""
Routes, buses and live bus tracking.

`TrackingService` keeps every route and bus in memory so the live map is fast:
  * Admin changes (add/edit/delete a route or bus) are written to the database
    straight away (services/store.py) and survive restarts.
  * Live data (GPS position, speed, trail, online/offline) is memory only.

Open maps follow the buses through a "version" number: every bus change bumps
it and wakes up `wait_for_change()`, which the live stream (/api/buses/stream)
uses to push updates within milliseconds. Each change is also written to a short
change log (`_frames`), so a map that is up to date only gets what changed
(`feed_message()`: a few hundred bytes) instead of every bus with its whole trail;
the JSON of each message is made once and shared by every open map.

Live positions are cleaned up on the way in (`update_location()`): GPS wobble is
filtered (services/speedometer.py), the bus is put back on its road and its
distance along the route is smoothed (services/route_geometry.py), and gaps in
the red trail are filled along the road instead of a straight line.

All public methods are thread-safe (one re-entrant lock guards the state).
"""

import json
import re
import threading
import time
import uuid
from collections import OrderedDict, deque
from itertools import pairwise

from content import colors, rules
from models.bus import BUS_AUDIENCES, Bus
from models.records import BusRecord, RouteRecord
from models.route import FINAL_STOP_NAME, BusRoute, BusStop
from services import geo, store
from services.road_router import RoadRouterError, road_path
from services.route_geometry import AlongTrack, RoutePath
from services.speedometer import Speedometer
from services.words import say

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
TIME_RE = re.compile(r"^(0?[1-9]|1[0-2]):[0-5]\d\s?(AM|PM)$", re.IGNORECASE)

# Colours offered to new buses and new routes (the first unused one is picked): content/colors.py
BUS_COLOR_PALETTE = colors.BUS_COLORS
ROUTE_COLOR_PALETTE = colors.ROUTE_COLORS

TRAIL_MIN_STEP_KM = rules.TRAIL_MIN_STEP_KM   # ignore GPS wobble smaller than this when drawing the trail
TRAIL_MAX_POINTS = rules.TRAIL_MAX_POINTS     # keep at most this many trail points per bus
AT_STOP_RADIUS_KM = 0.2       # closer than this to a stop = "at the stop"
ROUTE_SNAP_M = rules.ROUTE_SNAP_METERS        # GPS this close to the route line is put on the road
TRAIL_GAP_M = rules.TRAIL_FILL_GAP_METERS     # trail jumps longer than this are filled along the road
HEARTBEAT_S = 10.0            # a parked bus still tells open maps "I'm here" this often
FEED_LOG_SIZE = 5000          # changes remembered for maps catching up (older ones get a full snapshot)
FEED_CACHE_SIZE = 64          # ready-made JSON messages kept for the open maps

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
        self._speedometers: dict[str, Speedometer] = {}   # bus_id -> recent GPS fixes and speed
        self._along: dict[str, AlongTrack] = {}           # bus_id -> smoothed distance along its route
        self._paths: dict[str, tuple[tuple, RoutePath]] = {}   # route_id -> (version key, measurable line)
        self._clocks: dict[str, tuple[float, float]] = {}  # bus_id -> (phone-to-server clock offset, set at)
        self._trail_progress: dict[str, float | None] = {}  # bus_id -> route distance of its last trail point
        self._last_push: dict[str, float] = {}            # bus_id -> when open maps last heard of it
        self._gap_fills: set[str] = set()                 # buses with a road look-up for a trail gap running
        self._frames: deque = deque(maxlen=FEED_LOG_SIZE)  # (version, bus_id or None = "everything", trail points)
        self._feed_cache: OrderedDict = OrderedDict()     # (from, to, audience) -> JSON text
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
            for state in (self._trails, self._speedometers, self._along, self._paths, self._clocks,
                          self._trail_progress, self._last_push):
                state.clear()
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
                        trip_status: str = "EN_ROUTE", accuracy_m: float | None = None,
                        fix_time: float | None = None) -> dict | None:
        """
        Record a GPS position from the driver's phone (or a test drive). Returns the bus, or None.

          1. When the fix was taken, on the server's clock (`_sample_time`), so maps can
             move the bus at its real pace even if the network delivers fixes unevenly.
          2. Phone fixes go through the bus's Speedometer: very inaccurate fixes are ignored,
             a parked bus shows 0 km/h and keeps still, otherwise a smoothed speed.
          3. Near its route (ROUTE_SNAP_METERS) the bus is put on the road line and its
             distance along the route is smoothed, so it glides along the road.
          4. The red trail grows; a gap (e.g. the phone was off for a minute) is filled
             along the road instead of a straight line.
        """
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None
            new_trip = not bus.is_active
            if new_trip:
                self._forget_trip(bus_id)
            sample_t = self._sample_time(bus_id, fix_time, bus.sample_t)

            stopped = False
            if not bus.is_simulating:
                reading = self._speedometer(bus_id).update(
                    latitude, longitude, accuracy_m=accuracy_m, phone_speed_kmh=speed_kmh,
                    phone_heading=heading_deg if speed_kmh is None or speed_kmh >= rules.SPEED_MIN_KMH else None,
                    fix_time=sample_t)
                if not reading.use_fix:
                    bus.last_update_ts = time.time()   # the phone is still there, just inaccurate
                    return bus.to_dict()
                latitude, longitude = reading.latitude, reading.longitude
                speed_kmh, heading_deg, stopped = reading.speed_kmh, reading.heading_deg, reading.stopped
            elif heading_deg is None and (bus.current_latitude, bus.current_longitude) != (latitude, longitude):
                heading_deg = geo.bearing_deg(bus.current_latitude, bus.current_longitude, latitude, longitude)

            # Keep it on the road and measure how far along the route it is
            progress = None
            path = self._route_path(bus.assigned_route_id)
            if path is not None:
                on_road = path.project(latitude, longitude, near_m=bus.progress_m)
                if on_road.distance_m <= ROUTE_SNAP_M:
                    if bus.is_simulating:
                        progress = on_road.progress_m
                    else:
                        along = self._along.setdefault(bus_id, AlongTrack())
                        progress = along.update(on_road.progress_m, sample_t, stopped)
                    latitude, longitude, road_heading = path.point_at(progress)
                    if not stopped and (speed_kmh or 0) > 0 and not bus.is_simulating:
                        backwards = self._along[bus_id].velocity < -0.3
                        heading_deg = (road_heading + 180) % 360 if backwards else road_heading
                else:
                    self._along.pop(bus_id, None)

            # A parked bus sends the same thing every second: tell the maps only now and then
            same = (not new_trip and round(latitude, 7) == round(bus.current_latitude, 7)
                    and round(longitude, 7) == round(bus.current_longitude, 7)
                    and speed_kmh == bus.speed_kmh and trip_status == bus.trip_status)
            if same and time.time() - self._last_push.get(bus_id, 0) < HEARTBEAT_S:
                bus.last_update_ts = time.time()
                return bus.to_dict()

            bus.move_to(latitude, longitude, speed_kmh, heading_deg, trip_status,
                        sample_t=sample_t, progress_m=progress)
            added = self._add_trail_point(bus_id, latitude, longitude, progress, path)
            self._update_next_stop(bus)
            self._last_push[bus_id] = time.time()
            if new_trip:
                self._bump()                       # a new trip: maps reload this bus completely
            else:
                self._bump(bus_id, added)
            return bus.to_dict()

    def _speedometer(self, bus_id: str) -> Speedometer:
        """The speed filter of one bus (created on first use)."""
        return self._speedometers.setdefault(bus_id, Speedometer())

    def _forget_trip(self, bus_id: str) -> None:
        """A new trip starts (or one ended): empty trail, fresh speed and road filters."""
        self._trails[bus_id] = []
        self._speedometer(bus_id).reset()
        for state in (self._along, self._clocks, self._trail_progress, self._last_push):
            state.pop(bus_id, None)

    def _sample_time(self, bus_id: str, fix_time: float | None, previous: float) -> float:
        """
        When a fix was taken, on the server's clock. The phone's own fix times are exact but
        its clock may be a little off, so they are shifted by the smallest delay seen so far
        (which slowly follows any drift). Without a phone time: the moment it arrived.
        """
        now = time.time()
        sample = now
        if fix_time is not None and abs(fix_time - now) < 300:
            seen = now - fix_time
            offset, set_at = self._clocks.get(bus_id, (seen, now))
            offset = min(seen, offset + 0.02 * (now - set_at))
            self._clocks[bus_id] = (offset, now)
            sample = min(now, fix_time + offset)
        return max(sample, previous + 0.001) if previous else sample

    def _route_path(self, route_id: str | None) -> RoutePath | None:
        """The measurable road line of a route (rebuilt when the admin changes the route)."""
        route = self._routes.get(route_id or "")
        points = route.polyline_waypoints if route else []
        if len(points) < 2:
            return None
        key = (id(points), len(points), points[0]["lat"], points[-1]["lng"])
        cached = self._paths.get(route.route_id)
        if cached is None or cached[0] != key:
            cached = (key, RoutePath([(p["lat"], p["lng"]) for p in points]))
            self._paths[route.route_id] = cached
        return cached[1]

    def start_trip(self, bus_id: str) -> dict | None:
        """Driver went online: the bus shows on the maps from its next GPS position."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if bus is None:
                return None
            if not bus.is_active:
                self._forget_trip(bus_id)
                bus.last_update_ts = time.time()      # the auto-offline clock starts now
            bus.is_active = True
            bus.trip_status = "EN_ROUTE"
            self._bump()
            return bus.to_dict()

    def start_auto_offline(self) -> None:
        """
        Background check, every 30 s: a live bus with no GPS for AUTO_OFFLINE_MINUTES goes offline
        (its phone app was switched off, the battery died ...). Started once by create_app().
        """
        if rules.AUTO_OFFLINE_MINUTES <= 0 or getattr(self, "_auto_offline_started", False):
            return
        self._auto_offline_started = True

        def check() -> None:
            while True:
                time.sleep(30)
                limit = time.time() - rules.AUTO_OFFLINE_MINUTES * 60
                with self._lock:
                    silent = [b.bus_id for b in self._buses.values()
                              if b.is_active and not b.is_simulating and b.last_update_ts < limit]
                for bus_id in silent:
                    self.stop_trip(bus_id)

        threading.Thread(target=check, daemon=True, name="auto-offline").start()

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
            self._forget_trip(bus_id)
            self._trails.pop(bus_id, None)
            self._speedometers.pop(bus_id, None)
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
    def _add_trail_point(self, bus_id: str, lat: float, lng: float, progress: float | None,
                         path: RoutePath | None) -> list[list[float]]:
        """
        Grow the red trail behind a bus; returns the points added (sent to the open maps).
        Tiny GPS wobbles are skipped. A jump longer than TRAIL_FILL_GAP_METERS is filled
        along the route line, or (off the route) by asking the road router in the background.
        """
        trail = self._trails.setdefault(bus_id, [])
        point = [round(lat, 6), round(lng, 6)]
        added: list[list[float]] = []
        if trail:
            gap_m = geo.distance_km(trail[-1][0], trail[-1][1], lat, lng) * 1000
            if gap_m < TRAIL_MIN_STEP_KM * 1000:
                return []
            last_progress = self._trail_progress.get(bus_id)
            if gap_m > TRAIL_GAP_M:
                if progress is not None and last_progress is not None and path is not None:
                    added.extend(path.between(last_progress, progress))
                elif gap_m > 150:
                    self._fill_gap_by_road(bus_id, trail[-1], point)
        added.append(point)
        trail.extend(added)
        self._trail_progress[bus_id] = progress
        del trail[:-TRAIL_MAX_POINTS]
        return added

    def _fill_gap_by_road(self, bus_id: str, start: list[float], end: list[float]) -> None:
        """Off the route: ask the road router for the road between two trail points, in the background."""
        if bus_id in self._gap_fills:
            return
        self._gap_fills.add(bus_id)

        def fill() -> None:
            try:
                road, _ = road_path([tuple(start), tuple(end)])
            except RoadRouterError:
                road = []
            with self._lock:
                self._gap_fills.discard(bus_id)
                trail = self._trails.get(bus_id) or []
                for i in range(len(trail) - 1, 0, -1):
                    if trail[i] == end and trail[i - 1] == start:
                        trail[i:i] = road[1:-1]
                        del trail[:-TRAIL_MAX_POINTS]
                        self._bump()           # maps reload the trail
                        break

        threading.Thread(target=fill, daemon=True, name=f"trail-gap-{bus_id}").start()

    # =====================================================================
    # Live updates for open maps
    # =====================================================================
    def _bump(self, bus_id: str | None = None, trail_added: list | None = None) -> None:
        """
        Note that something changed and wake every waiting live stream (lock must be held).
        bus_id: only this bus moved (trail_added = its new trail points); None: anything else
        changed (a bus or route was added / edited, a trip started or ended ...).
        """
        self._version += 1
        self._frames.append((self._version, bus_id, trail_added or []))
        self._changed.notify_all()

    def feed_message(self, since_version: int, audience: str | None = None) -> tuple[int, str | None]:
        """
        What a live map that has seen `since_version` needs next: (new version, JSON text).
          {"type": "snapshot", "now", "trail_max", "buses": [every bus, complete]}  - first message,
              after a bus or route was changed, or when the map fell too far behind
          {"type": "delta", "now", "buses": [only the moved buses, small, with "trail_add"]}
        The text is None when nothing changed (or only buses for another audience moved).
        Messages are cached, so a thousand open maps cost one json.dumps().
        """
        with self._lock:
            version = self._version
            if version == since_version:
                return version, None
            key = (since_version, version, audience)
            if key in self._feed_cache:
                self._feed_cache.move_to_end(key)
                return version, self._feed_cache[key]

            frames = [f for f in self._frames if f[0] > since_version]
            complete = (since_version < 0 or not frames or frames[0][0] != since_version + 1
                        or any(f[1] is None or f[1] not in self._buses for f in frames))
            if complete:
                message = {"type": "snapshot", "now": time.time(), "trail_max": TRAIL_MAX_POINTS,
                           "buses": [self._bus_dict(b) for b in self._buses.values()
                                     if audience is None or b.audience == audience]}
            else:
                trail_added: dict[str, list] = {}
                for _, bus_id, points in frames:
                    trail_added.setdefault(bus_id, []).extend(points)
                buses = []
                for bus_id, points in trail_added.items():
                    bus = self._buses[bus_id]
                    if audience is None or bus.audience == audience:
                        buses.append({**bus.live_dict(), "trail_add": points})
                message = {"type": "delta", "now": time.time(), "buses": buses} if buses else None

            text = json.dumps(message, separators=(",", ":")) if message else None
            self._feed_cache[key] = text
            while len(self._feed_cache) > FEED_CACHE_SIZE:
                self._feed_cache.popitem(last=False)
            return version, text

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
            self._forget_trip(bus_id)
            self._trails[bus_id] = [[bus.current_latitude, bus.current_longitude]]
            self._trail_progress[bus_id] = 0.0
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
