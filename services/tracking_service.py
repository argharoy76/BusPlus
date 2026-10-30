"""
Khulna University Bus Tracker (BusPlus)
Live Bus Fleet Tracking & Simulation Service
"""

import re
import threading
import time
import uuid
from typing import Dict, List, Optional, Any
from models.bus import Bus, get_default_khulna_university_buses
from config import AppConfig
from models.route import (BusRoute, BusStop, get_predefined_khulna_university_routes,
                          ensure_route_ends_at_final_destination)
from services.eta_service import ETAService

# Colours offered to new buses (each bus keeps its own colour on the student map)
BUS_COLOR_PALETTE = [
    "#E11D48", "#0891B2", "#EA580C", "#7C3AED", "#16A34A",
    "#DB2777", "#CA8A04", "#4F46E5", "#0D9488", "#9333EA"
]
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
BUS_AUDIENCES = ("student", "teacher")

class TrackingService:
    """Singleton service managing in-memory state of university bus tracking."""

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(TrackingService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._routes: Dict[str, BusRoute] = get_predefined_khulna_university_routes()
        self._buses: Dict[str, Bus] = get_default_khulna_university_buses()
        self._simulation_threads: Dict[str, threading.Thread] = {}
        self._simulation_flags: Dict[str, bool] = {}
        # Live updates: bumped on every bus change so open maps are pushed the news at once
        self._version = 0
        self._changed = threading.Condition(self._lock)
        self._simulation_runs: Dict[str, str] = {}  # bus_id -> id of the one simulation allowed to run
        # Where each bus has driven on its current trip (shown as a red trail to students)
        self._trails: Dict[str, List[List[float]]] = {}
        self._initialized = True

    # -------------------------------------------------------------------------
    # Route Methods
    # -------------------------------------------------------------------------
    def get_all_routes(self) -> List[Dict[str, Any]]:
        """Returns all predefined university bus routes."""
        with self._lock:
            return [route.to_dict() for route in self._routes.values()]

    def get_route_by_id(self, route_id: str) -> Optional[BusRoute]:
        """Finds a route by its ID."""
        with self._lock:
            return self._routes.get(route_id)

    # -------------------------------------------------------------------------
    # Bus Fleet Telemetry Methods
    # -------------------------------------------------------------------------
    def get_all_buses(self, audience: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all buses (or only the student / teacher buses) with current telemetry and route info."""
        with self._lock:
            result = []
            for bus in self._buses.values():
                if audience and bus.audience != audience:
                    continue
                bus_dict = self._bus_with_route(bus)
                # Trail of the current trip (only while the bus is live)
                bus_dict["trail"] = list(self._trails.get(bus.bus_id, [])) if bus.is_active else []
                result.append(bus_dict)
            return result

    def get_active_buses(self) -> List[Dict[str, Any]]:
        """Returns only buses currently broadcasting GPS or on active trip."""
        with self._lock:
            all_buses = self.get_all_buses()
            return [b for b in all_buses if b.get("is_active")]

    def get_bus_by_id(self, bus_id: str) -> Optional[Bus]:
        """Finds a bus by its identifier."""
        with self._lock:
            return self._buses.get(bus_id)

    def update_bus_location(
        self,
        bus_id: str,
        latitude: float,
        longitude: float,
        speed_kmh: Optional[float] = None,
        heading_deg: Optional[float] = None,
        trip_status: Optional[str] = "EN_ROUTE"
    ) -> Optional[Dict[str, Any]]:
        """
        Receives real-time GPS stream from driver device and updates bus status.
        Calculates heading if not supplied, finds closest upcoming stop.
        """
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return None

            # Speed not reported by the phone: estimate it from the distance since the last fix
            if speed_kmh is None and bus.is_active:
                try:
                    from datetime import datetime, timezone
                    last = datetime.fromisoformat(bus.last_updated_iso)
                    seconds = (datetime.now(timezone.utc) - last).total_seconds()
                    if 1.0 <= seconds <= 120.0:
                        km = ETAService.calculate_haversine_distance_km(
                            bus.current_latitude, bus.current_longitude, latitude, longitude)
                        speed_kmh = min(120.0, km / (seconds / 3600.0))
                except (TypeError, ValueError):
                    pass

            # Calculate bearing if previous coordinate exists and heading not given
            if heading_deg is None and (bus.current_latitude != latitude or bus.current_longitude != longitude):
                heading_deg = ETAService.calculate_bearing_degrees(
                    bus.current_latitude, bus.current_longitude,
                    latitude, longitude
                )

            was_active = bus.is_active
            bus.update_telemetry(
                latitude=latitude,
                longitude=longitude,
                speed_kmh=speed_kmh,
                heading_deg=heading_deg,
                trip_status=trip_status
            )
            bus.is_active = True
            if not was_active:
                self._trails[bus_id] = []   # a new trip starts a new trail
            self._add_trail_point(bus_id, latitude, longitude)

            # Determine closest/next stop along assigned route
            route = self._routes.get(bus.assigned_route_id)
            if route and route.stops:
                self._update_next_stop_and_eta(bus, route)

            self._bump()
            return bus.to_dict()

    def set_trip_status(self, bus_id: str, is_active: bool, trip_status: str = "IDLE") -> Optional[Dict[str, Any]]:
        """Allows driver to start or end a trip."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return None
            was_active = bus.is_active
            bus.is_active = is_active
            bus.trip_status = trip_status
            if is_active and not was_active:
                self._trails[bus_id] = []          # new trip, new trail
            if not is_active:
                bus.speed_kmh = 0.0
                self._trails.pop(bus_id, None)     # trip over: clear its trail
                # Stop simulation if active
                self.stop_bus_simulation(bus_id)
            self._bump()
            return bus.to_dict()

    # -------------------------------------------------------------------------
    # Route Setup (backend admin): add / edit / delete routes
    # Every route always ends at the final destination (Hadi Chattar).
    # -------------------------------------------------------------------------
    TIME_RE = re.compile(r"^(0?[1-9]|1[0-2]):[0-5]\d\s?(AM|PM)$", re.IGNORECASE)

    def _clean_route_fields(self, data: Dict[str, Any], creating: bool) -> Dict[str, Any]:
        clean: Dict[str, Any] = {}
        name = str(data.get("route_name") or "").strip()
        if creating and not name:
            raise ValueError("Route name is required.")
        if name:
            clean["route_name"] = name[:80]
        if data.get("route_code"):
            clean["route_code"] = str(data["route_code"]).strip()[:30]
        if data.get("description") is not None:
            clean["description"] = str(data.get("description") or "").strip()[:200]
        if data.get("color_hex"):
            color = str(data["color_hex"]).strip()
            if not HEX_COLOR_RE.match(color):
                raise ValueError("Route colour must look like #2563EB.")
            clean["color_hex"] = color.upper()

        # Route points: clicked on the map to steer the route along the right roads.
        # They don't need names (the route name is what everyone sees); built-in routes keep their place names.
        if "points" in data or "stops" in data or creating:
            raw = data.get("points") if "points" in data else data.get("stops")
            raw = raw or []
            if not isinstance(raw, list):
                raise ValueError("Route points must be a list.")
            dest = AppConfig.FINAL_DESTINATION
            points = []
            for i, pt in enumerate(raw, start=1):
                if not isinstance(pt, dict):
                    raise ValueError(f"Point {i} is not valid.")
                name = str(pt.get("name") or pt.get("stop_name") or "").strip()
                if name.lower() == dest["stop_name"].lower():
                    continue  # the final destination is added automatically
                try:
                    lat = float(pt.get("latitude", pt.get("lat")))
                    lng = float(pt.get("longitude", pt.get("lng")))
                except (TypeError, ValueError):
                    raise ValueError(f"Point {i} needs a map position.")
                if not (20.0 <= lat <= 27.0 and 88.0 <= lng <= 93.0):
                    raise ValueError(f"Point {i} is outside Bangladesh.")
                time_txt = str(pt.get("scheduled_morning_time") or "").strip().upper()
                if time_txt and not self.TIME_RE.match(time_txt):
                    raise ValueError(f"Time for point {i} must look like 08:35 AM.")
                points.append({"name": name[:60], "lat": lat, "lng": lng, "time": time_txt})
            if not points:
                raise ValueError("Click the map to draw the route.")
            clean["points"] = points

            # Road-following line drawn by the editor: [[lat, lng], ...]
            path = data.get("path")
            clean["path"] = None
            if path:
                if not isinstance(path, list) or not (2 <= len(path) <= 20000):
                    raise ValueError("The route line is not valid.")
                good = []
                for pt in path:
                    try:
                        plat, plng = float(pt[0]), float(pt[1])
                    except (TypeError, ValueError, IndexError):
                        raise ValueError("The route line is not valid.")
                    if not (20.0 <= plat <= 27.0 and 88.0 <= plng <= 93.0):
                        raise ValueError("The route line goes outside Bangladesh.")
                    good.append({"lat": round(plat, 6), "lng": round(plng, 6)})
                clean["path"] = good
        return clean

    def _apply_points(self, route: BusRoute, points: List[Dict[str, Any]], path: Optional[List[Dict[str, float]]]) -> None:
        """
        Rebuilds a route from the admin's points:
          - the line follows the given road path (or straight lines between points if there is none)
          - named points become the route's places (stops); Hadi Chattar is always the last one
        """
        prefix = route.route_id.lower().replace("-", "_")
        named = [pt for pt in points if pt["name"]]
        route.via_points = [{"lat": pt["lat"], "lng": pt["lng"], "name": pt["name"]} for pt in points]
        route.stops = [
            BusStop(
                stop_id=f"{prefix}_s{i}",
                stop_name=pt["name"],
                latitude=pt["lat"],
                longitude=pt["lng"],
                sequence_order=i,
                scheduled_morning_time=pt.get("time", ""),
                scheduled_afternoon_time="",
                landmark_hint=""
            )
            for i, pt in enumerate(named, start=1)
        ]
        route.polyline_waypoints = path if path else [{"lat": pt["lat"], "lng": pt["lng"]} for pt in points]
        ensure_route_ends_at_final_destination(route)

    def _next_route_id(self) -> str:
        n = 1
        while f"KU-R{n:02d}" in self._routes:
            n += 1
        return f"KU-R{n:02d}"

    def create_route(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            clean = self._clean_route_fields(data, creating=True)
            route_id = self._next_route_id()
            used = {r.color_hex.upper() for r in self._routes.values()}
            palette = ["#2563EB", "#059669", "#D97706", "#DB2777", "#7C3AED", "#0891B2", "#65A30D", "#DC2626"]
            route = BusRoute(
                route_id=route_id,
                route_name=clean["route_name"],
                route_code=clean.get("route_code") or f"R{route_id[-2:].lstrip('0') or '0'}",
                color_hex=clean.get("color_hex") or next((c for c in palette if c not in used), palette[0]),
                description=clean.get("description", ""),
            )
            self._apply_points(route, clean["points"], clean.get("path"))
            self._routes[route_id] = route
            return route.to_dict()

    def update_route(self, route_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            route = self._routes.get(route_id)
            if not route:
                return None
            clean = self._clean_route_fields(data, creating=False)
            for key in ("route_name", "route_code", "description", "color_hex"):
                if key in clean:
                    setattr(route, key, clean[key])
            if "points" in clean:
                self._apply_points(route, clean["points"], clean.get("path"))
            return route.to_dict()

    def delete_route(self, route_id: str) -> bool:
        with self._lock:
            if route_id not in self._routes:
                return False
            on_route = [b.bus_number for b in self._buses.values() if b.assigned_route_id == route_id]
            if on_route:
                raise ValueError(f"{', '.join(on_route)} use this route. Move them to another route in Buses first.")
            del self._routes[route_id]
            return True

    # -------------------------------------------------------------------------
    # Live updates
    # -------------------------------------------------------------------------
    def _bump(self) -> None:
        """Call while holding the lock after any bus change: wakes everyone waiting for news."""
        self._version += 1
        self._changed.notify_all()

    def get_version(self) -> int:
        with self._lock:
            return self._version

    def wait_for_change(self, since_version: int, timeout: float = 15.0) -> int:
        """Blocks until a bus changes after since_version (or the timeout). Returns the current version."""
        with self._changed:
            if self._version == since_version:
                self._changed.wait(timeout)
            return self._version

    # -------------------------------------------------------------------------
    # Trip trail (the red line a bus leaves behind it)
    # -------------------------------------------------------------------------
    TRAIL_MIN_STEP_KM = 0.012   # ignore GPS jitter smaller than ~12 m
    TRAIL_MAX_POINTS = 1500

    def _add_trail_point(self, bus_id: str, lat: float, lng: float) -> None:
        trail = self._trails.setdefault(bus_id, [])
        if trail:
            last_lat, last_lng = trail[-1]
            if ETAService.calculate_haversine_distance_km(last_lat, last_lng, lat, lng) < self.TRAIL_MIN_STEP_KM:
                return
        trail.append([round(lat, 6), round(lng, 6)])
        if len(trail) > self.TRAIL_MAX_POINTS:
            del trail[0: len(trail) - self.TRAIL_MAX_POINTS]

    def get_trail(self, bus_id: str) -> List[List[float]]:
        with self._lock:
            return list(self._trails.get(bus_id, []))

    # -------------------------------------------------------------------------
    # Bus Setup (backend admin): add / edit / delete buses
    # -------------------------------------------------------------------------
    def _next_bus_id(self) -> str:
        n = 1
        while f"KU-BUS-{n:02d}" in self._buses:
            n += 1
        return f"KU-BUS-{n:02d}"

    def _next_free_color(self) -> str:
        used = {b.color_hex.upper() for b in self._buses.values()}
        for color in BUS_COLOR_PALETTE:
            if color.upper() not in used:
                return color
        return BUS_COLOR_PALETTE[len(self._buses) % len(BUS_COLOR_PALETTE)]

    def _validate_bus_fields(self, data: Dict[str, Any], creating: bool) -> Dict[str, Any]:
        """Cleans and checks bus fields from the admin form. Raises ValueError with a readable message."""
        clean: Dict[str, Any] = {}

        for key in ("bus_number", "bus_name", "license_plate"):
            if key in data and data[key] is not None:
                clean[key] = str(data[key]).strip()
        if creating and not clean.get("bus_number"):
            raise ValueError("Bus number is required (e.g. KU Bus #05).")
        if "bus_number" in clean and not clean["bus_number"]:
            raise ValueError("Bus number can't be empty.")

        if data.get("assigned_route_id"):
            route_id = str(data["assigned_route_id"]).strip()
            if route_id not in self._routes:
                raise ValueError(f"Route {route_id} doesn't exist.")
            clean["assigned_route_id"] = route_id
        elif creating:
            raise ValueError("Please choose a route for the bus.")

        if data.get("color_hex"):
            color = str(data["color_hex"]).strip()
            if not HEX_COLOR_RE.match(color):
                raise ValueError("Colour must look like #E11D48.")
            clean["color_hex"] = color.upper()

        if data.get("audience"):
            audience = str(data["audience"]).strip().lower()
            if audience not in BUS_AUDIENCES:
                raise ValueError("A bus is either for students or for teachers.")
            clean["audience"] = audience

        if data.get("capacity") not in (None, ""):
            try:
                capacity = int(data["capacity"])
            except (TypeError, ValueError):
                raise ValueError("Capacity must be a whole number.")
            if not 1 <= capacity <= 120:
                raise ValueError("Capacity must be between 1 and 120.")
            clean["capacity"] = capacity

        return clean

    def _park_at_route_start(self, bus: Bus) -> None:
        route = self._routes.get(bus.assigned_route_id)
        if route and route.stops:
            first = route.stops[0]
            bus.current_latitude = first.latitude
            bus.current_longitude = first.longitude
            bus.current_stop_index = 0
            bus.next_stop_name = first.stop_name

    def create_bus(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Adds a bus. It is parked at the first stop of its route; every route ends at Hadi Chattar."""
        with self._lock:
            clean = self._validate_bus_fields(data, creating=True)
            bus_id = self._next_bus_id()
            bus = Bus(
                bus_id=bus_id,
                bus_number=clean["bus_number"],
                bus_name=clean.get("bus_name") or clean["bus_number"],
                license_plate=clean.get("license_plate", ""),
                assigned_route_id=clean["assigned_route_id"],
                color_hex=clean.get("color_hex") or self._next_free_color(),
                capacity=clean.get("capacity", 52),
                audience=clean.get("audience", "student"),
            )
            self._park_at_route_start(bus)
            self._buses[bus_id] = bus
            self._bump()
            return self._bus_with_route(bus)

    def update_bus(self, bus_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Edits a bus. Returns None if the bus doesn't exist."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return None
            clean = self._validate_bus_fields(data, creating=False)
            route_changed = "assigned_route_id" in clean and clean["assigned_route_id"] != bus.assigned_route_id
            if route_changed and bus.is_active:
                raise ValueError(f"{bus.bus_number} is on a live trip. Stop the trip before changing its route.")
            for key, value in clean.items():
                setattr(bus, key, value)
            if route_changed:
                self._park_at_route_start(bus)
            self._bump()
            return self._bus_with_route(bus)

    def delete_bus(self, bus_id: str) -> bool:
        """Removes a bus. Refuses (ValueError) while it is on a live trip."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return False
            if bus.is_active:
                raise ValueError(f"{bus.bus_number} is on a live trip. Stop the trip before deleting it.")
            self.stop_bus_simulation(bus_id)
            del self._buses[bus_id]
            self._bump()
            return True

    def set_bus_driver(self, bus_id: str, driver: Optional[Dict[str, Any]]) -> None:
        """Keeps the driver shown on a bus in step with Driver Setup."""
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return
            bus.driver_id = driver.get("driver_id") if driver else None
            bus.driver_name = driver.get("full_name") if driver else None
            bus.driver_phone = driver.get("phone") if driver else None

    def clear_driver_from_buses(self, driver_id: str) -> None:
        with self._lock:
            for bus in self._buses.values():
                if bus.driver_id == driver_id:
                    bus.driver_id = bus.driver_name = bus.driver_phone = None

    def _bus_with_route(self, bus: Bus) -> Dict[str, Any]:
        bus_dict = bus.to_dict()
        route = self._routes.get(bus.assigned_route_id)
        if route:
            bus_dict["route_name"] = route.route_name
            bus_dict["route_code"] = route.route_code
            bus_dict["route_color"] = route.color_hex
        return bus_dict

    # -------------------------------------------------------------------------
    # Route Stop Progress & ETA Helper
    # -------------------------------------------------------------------------
    def _update_next_stop_and_eta(self, bus: Bus, route: BusRoute) -> None:
        """Finds the upcoming stop on the route and estimates arrival minutes."""
        min_dist = float("inf")
        closest_stop_idx = 0

        for idx, stop in enumerate(route.stops):
            dist = ETAService.calculate_haversine_distance_km(
                bus.current_latitude, bus.current_longitude,
                stop.latitude, stop.longitude
            )
            if dist < min_dist:
                min_dist = dist
                closest_stop_idx = idx

        # If very close to closest stop, next stop is the following one
        if min_dist < 0.2 and closest_stop_idx + 1 < len(route.stops):
            next_idx = closest_stop_idx + 1
        else:
            next_idx = closest_stop_idx

        bus.current_stop_index = next_idx
        next_stop = route.stops[next_idx]
        bus.next_stop_name = next_stop.stop_name

        eta_res = ETAService.estimate_eta(
            bus.current_latitude, bus.current_longitude,
            next_stop.latitude, next_stop.longitude,
            bus.speed_kmh
        )
        bus.estimated_next_stop_minutes = eta_res["eta_minutes"]

    # -------------------------------------------------------------------------
    # Realistic GPS Simulation Engine (for testing & demo)
    # -------------------------------------------------------------------------
    def start_bus_simulation(self, bus_id: str, speed_multiplier: float = 1.0) -> bool:
        """
        Starts a background simulation thread that moves the bus along
        the exact waypoints of its assigned route.
        Essential for testing when driver is not physically in a moving bus!
        """
        with self._lock:
            bus = self._buses.get(bus_id)
            if not bus:
                return False

            route = self._routes.get(bus.assigned_route_id)
            if not route or not route.polyline_waypoints:
                return False

            # Stop existing simulation if already running
            self.stop_bus_simulation(bus_id)

            run_id = uuid.uuid4().hex
            self._simulation_runs[bus_id] = run_id
            self._simulation_flags[bus_id] = True
            bus.is_simulating = True
            bus.is_active = True
            bus.trip_status = "EN_ROUTE"
            self._park_at_route_start(bus)
            self._trails[bus_id] = [[bus.current_latitude, bus.current_longitude]]

            sim_thread = threading.Thread(
                target=self._run_simulation_loop,
                args=(bus_id, route, speed_multiplier, run_id),
                daemon=True,
                name=f"SimThread-{bus_id}"
            )
            self._simulation_threads[bus_id] = sim_thread
            sim_thread.start()
            return True

    def stop_bus_simulation(self, bus_id: str) -> bool:
        """Stops an ongoing GPS simulation."""
        with self._lock:
            if bus_id in self._simulation_flags:
                self._simulation_flags[bus_id] = False
            self._simulation_runs.pop(bus_id, None)
            bus = self._buses.get(bus_id)
            if bus:
                bus.is_simulating = False
            return True

    def _run_simulation_loop(self, bus_id: str, route: BusRoute, speed_multiplier: float, run_id: str) -> None:
        """
        Drives the bus once along the route line, from the start to the final destination
        (Hadi Chattar), at a steady speed, then parks it there.
        """
        line = [(wp["lat"], wp["lng"]) for wp in route.polyline_waypoints]
        if len(line) < 2:
            return
        try:
            speed_multiplier = max(0.1, float(speed_multiplier))
        except (TypeError, ValueError):
            speed_multiplier = 1.0

        def still_running() -> bool:
            # A stop, or a newer simulation for the same bus, ends this one
            return self._simulation_flags.get(bus_id, False) and self._simulation_runs.get(bus_id) == run_id

        tick_s = 1.0
        speed_kmh = 30.0
        step_km = speed_kmh / 3600.0 * tick_s * speed_multiplier   # distance covered per update
        travelled_in_segment = 0.0

        for i in range(len(line) - 1):
            (lat1, lng1), (lat2, lng2) = line[i], line[i + 1]
            seg_km = ETAService.calculate_haversine_distance_km(lat1, lng1, lat2, lng2)
            if seg_km <= 0:
                continue
            bearing = ETAService.calculate_bearing_degrees(lat1, lng1, lat2, lng2)
            pos = travelled_in_segment
            while pos < seg_km:
                if not still_running():
                    return
                t = pos / seg_km
                self.update_bus_location(
                    bus_id=bus_id,
                    latitude=lat1 + (lat2 - lat1) * t,
                    longitude=lng1 + (lng2 - lng1) * t,
                    speed_kmh=speed_kmh + (i % 4) * 2.0,
                    heading_deg=bearing,
                    trip_status="EN_ROUTE"
                )
                time.sleep(tick_s)
                pos += step_km
            travelled_in_segment = pos - seg_km

        if still_running():
            last_lat, last_lng = line[-1]
            self.update_bus_location(bus_id=bus_id, latitude=last_lat, longitude=last_lng,
                                     speed_kmh=0.0, heading_deg=None, trip_status="ARRIVED")

        # Reached the final destination: park at Hadi Chattar
        with self._lock:
            if not still_running():
                return
            bus = self._buses.get(bus_id)
            if bus:
                bus.speed_kmh = 0.0
                bus.trip_status = "ARRIVED"
                self._bump()
                bus.is_simulating = False
            self._simulation_flags[bus_id] = False
            self._simulation_runs.pop(bus_id, None)
