"""
Turns the starting data in content/starting_data.py into routes, buses and drivers.
Used once, when the database is empty (see services/store.py: seed_defaults).
"""

from content.starting_data import BUSES, DEMO_DRIVER_PIN, DEMO_DRIVERS, ROUTES
from models.bus import Bus
from models.rider_types import DEFAULT_RIDER_KEY
from models.route import BusRoute, BusStop
from models.route_paths import ROAD_PATHS
from models.user import DriverUser


def default_routes() -> list[BusRoute]:
    """The built-in KU routes, drawn along the real roads (see route_paths.py)."""
    routes = []
    for spec in ROUTES:
        stops = [
            BusStop(stop_name=name, latitude=lat, longitude=lng, sequence_order=i,
                    scheduled_morning_time=time_txt, landmark_hint=hint)
            for i, (name, lat, lng, time_txt, hint) in enumerate(spec["stops"], start=1)
        ]
        # Road line from route_paths.py; a route without one gets straight lines between its stops.
        line = ROAD_PATHS.get(spec["route_id"]) or [(s.latitude, s.longitude) for s in stops]
        route = BusRoute(
            route_id=spec["route_id"],
            route_name=spec["route_name"],
            route_code=spec["route_code"],
            color_hex=spec["color_hex"],
            stops=stops,
            polyline_waypoints=[{"lat": lat, "lng": lng} for lat, lng in line],
            via_points=[{"lat": s.latitude, "lng": s.longitude, "name": s.stop_name} for s in stops],
        )
        route.end_at_final_destination()
        routes.append(route)
    return routes


def default_buses() -> list[Bus]:
    """The built-in KU buses (all for the first rider type, e.g. students, to begin with)."""
    return [
        Bus(bus_id=bus_id, bus_number=number, bus_name=name, license_plate=plate,
            assigned_route_id=route_id, color_hex=color, capacity=capacity, audience=DEFAULT_RIDER_KEY)
        for bus_id, number, name, plate, route_id, color, capacity in BUSES
    ]


def demo_drivers() -> list[DriverUser]:
    """Four demo drivers, one per bus, all with PIN 1234 (for trying the app out only)."""
    drivers = []
    for driver_id, username, full_name, phone, bus_id in DEMO_DRIVERS:
        driver = DriverUser(driver_id=driver_id, username=username, full_name=full_name,
                            pin_hash="", phone=phone, assigned_bus_id=bus_id)
        driver.set_pin(DEMO_DRIVER_PIN)
        drivers.append(driver)
    return drivers
