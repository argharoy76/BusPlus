"""
Starting data written to an empty database on the very first start.

After that, everything is managed by the admin in the backend (/backend):
these routes and buses can be edited or removed there like any other.
The demo drivers are only created when `Config.SEED_DEMO_DRIVERS` is on.
"""

from models.bus import Bus
from models.route import BusRoute, BusStop
from models.route_paths import ROAD_PATHS
from models.user import DriverUser

# (name, latitude, longitude, morning time, landmark) for each named place; Hadi Chattar is added automatically.
_ROUTES = [
    {
        "route_id": "KU-R01", "route_name": "Malabotha - Rupsha - KU Line", "route_code": "R1", "color_hex": "#2563EB",
        "stops": [
            ("Malabotha More", 22.7725, 89.5855, "08:35 AM", "Malabotha More / Bazar Bus Stand"),
            ("Rupsha Bridge Toll Plaza", 22.7840, 89.5780, "08:42 AM", "Khan Jahan Ali Bridge West Toll Booth"),
            ("Labanchara Ghat", 22.7935, 89.5695, "08:48 AM", "Labanchara Main Road Intersection"),
            ("Rupsha Traffic Mor", 22.8020, 89.5630, "08:54 AM", "Rupsha Ferry Ghat Crossing"),
            ("PTI More", 22.8125, 89.5585, "08:59 AM", "Primary Teachers Training Institute (PTI) Junction"),
            ("Royal Mor", 22.8222, 89.5605, "09:03 AM", "Hotel Royal International Square"),
            ("Moylapota Mor", 22.8185, 89.5535, "09:08 AM", "Moylapota Square / Ahsan Ahmed Road Junction"),
            ("Sonadanga Bus Terminal Mor", 22.8225, 89.5420, "09:14 AM", "Sonadanga Inter-district Terminal Gate"),
            ("Gollamari Mor", 22.8090, 89.5398, "09:20 AM", "Gollamari Bridge Approach / Memorial"),
        ],
    },
    {
        "route_id": "KU-R02", "route_name": "Phultala - Daulatpur - Shibbari Line", "route_code": "R2",
        "color_hex": "#059669",
        "stops": [
            ("Phultala Super Market", 22.9780, 89.4620, "08:15 AM", "Phultala Bazar Bus Stand"),
            ("Shiromoni Cantonment Gate", 22.9250, 89.4880, "08:28 AM", "Shiromoni Bazar Junction"),
            ("Daulatpur Bus Stand", 22.8750, 89.5160, "08:40 AM", "Daulatpur BL College Mor"),
            ("Khalishpur Notun Rasta", 22.8580, 89.5290, "08:48 AM", "BIDC Road Intersection"),
            ("Boyra Dakbangla Mor", 22.8420, 89.5380, "08:58 AM", "Boyra Police Line Road"),
            ("Shibbari Mor", 22.8285, 89.5535, "09:08 AM", "Shibbari Public Hall Crossing"),
            ("Gollamari Mor", 22.8090, 89.5398, "09:20 AM", "Gollamari Memorial Bridge"),
        ],
    },
    {
        "route_id": "KU-R03", "route_name": "Dumuria - Zero Point Line", "route_code": "R3", "color_hex": "#D97706",
        "stops": [
            ("Dumuria Hospital Mor", 22.8105, 89.4250, "08:40 AM", "Dumuria Upazila Complex"),
            ("Gutudia Bazar", 22.8055, 89.4720, "08:55 AM", "Gutudia High School Stand"),
            ("Zero Point Crossing", 22.7985, 89.5312, "09:15 AM", "Khulna Bypass Intersection"),
        ],
    },
]

_BUSES = [
    # bus_id, number, name, plate, route, colour, capacity
    ("KU-BUS-01", "KU Bus #01", "Khan Jahan Ali Express", "Khulna-Cha 11-2041", "KU-R01", "#E11D48", 52),
    ("KU-BUS-02", "KU Bus #02", "Sundarban Pioneer", "Khulna-Cha 11-3052", "KU-R02", "#0891B2", 52),
    ("KU-BUS-03", "KU Bus #03", "Moyur Express", "Khulna-Cha 11-4019", "KU-R03", "#EA580C", 52),
    ("KU-BUS-04", "KU Bus #04", "Bhairab Shuttle", "Khulna-Cha 11-5088", "KU-R01", "#7C3AED", 40),
]

_DEMO_DRIVERS = [
    # driver_id, username, full name, phone, bus
    ("DRV-01", "rafiqul", "Md. Rafiqul Islam", "+880 1712-890123", "KU-BUS-01"),
    ("DRV-02", "mannan", "Abdul Mannan", "+880 1715-456789", "KU-BUS-02"),
    ("DRV-03", "kamal", "Kamal Hossain", "+880 1819-123987", "KU-BUS-03"),
    ("DRV-04", "siraj", "Siraj Uddin", "+880 1913-654321", "KU-BUS-04"),
]
DEMO_DRIVER_PIN = "1234"


def default_routes() -> list[BusRoute]:
    """The three built-in KU routes, drawn along the real roads (see route_paths.py)."""
    routes = []
    for spec in _ROUTES:
        stops = [
            BusStop(stop_name=name, latitude=lat, longitude=lng, sequence_order=i,
                    scheduled_morning_time=time_txt, landmark_hint=hint)
            for i, (name, lat, lng, time_txt, hint) in enumerate(spec["stops"], start=1)
        ]
        route = BusRoute(
            route_id=spec["route_id"],
            route_name=spec["route_name"],
            route_code=spec["route_code"],
            color_hex=spec["color_hex"],
            stops=stops,
            polyline_waypoints=[{"lat": lat, "lng": lng} for lat, lng in ROAD_PATHS[spec["route_id"]]],
            via_points=[{"lat": s.latitude, "lng": s.longitude, "name": s.stop_name} for s in stops],
        )
        route.end_at_final_destination()
        routes.append(route)
    return routes


def default_buses() -> list[Bus]:
    """The four built-in KU buses (all for students to begin with)."""
    return [
        Bus(bus_id=bus_id, bus_number=number, bus_name=name, license_plate=plate,
            assigned_route_id=route_id, color_hex=color, capacity=capacity)
        for bus_id, number, name, plate, route_id, color, capacity in _BUSES
    ]


def demo_drivers() -> list[DriverUser]:
    """Four demo drivers, one per bus, all with PIN 1234 (for trying the app out only)."""
    drivers = []
    for driver_id, username, full_name, phone, bus_id in _DEMO_DRIVERS:
        driver = DriverUser(driver_id=driver_id, username=username, full_name=full_name,
                            pin_hash="", phone=phone, assigned_bus_id=bus_id)
        driver.set_pin(DEMO_DRIVER_PIN)
        drivers.append(driver)
    return drivers
