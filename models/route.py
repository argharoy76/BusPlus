"""
Khulna University Bus Tracker (BusPlus)
Route & Stop Data Models
"""

import math
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from config import AppConfig

@dataclass
class BusStop:
    """Represents a designated bus stop along a university route."""
    stop_id: str
    stop_name: str
    latitude: float
    longitude: float
    sequence_order: int
    scheduled_morning_time: str   # e.g., "08:35 AM"
    scheduled_afternoon_time: str # e.g., "02:15 PM"
    landmark_hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class BusRoute:
    """Represents a complete university bus route with ordered stops and waypoints."""
    route_id: str
    route_name: str
    route_code: str
    color_hex: str
    description: str
    stops: List[BusStop] = field(default_factory=list)
    polyline_waypoints: List[Dict[str, float]] = field(default_factory=list)
    # Points the admin clicked to steer the route (the line follows the roads between them)
    via_points: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "route_name": self.route_name,
            "route_code": self.route_code,
            "color_hex": self.color_hex,
            "description": self.description,
            "total_stops": len(self.stops),
            "stops": [stop.to_dict() for stop in self.stops],
            "polyline_waypoints": self.polyline_waypoints,
            "via_points": self.via_points,
            "length_km": round(self.length_km(), 2)
        }

    def length_km(self) -> float:
        """Length of the route line in km."""
        km = 0.0
        pts = self.polyline_waypoints
        for a, b in zip(pts, pts[1:]):
            p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
            dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
            h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
            km += 2 * 6371.0088 * math.asin(math.sqrt(h))
        return km

    def get_stop_by_name(self, stop_name: str) -> Optional[BusStop]:
        """Finds a stop by matching name (case-insensitive substring match)."""
        normalized = stop_name.strip().lower()
        for stop in self.stops:
            s_name = stop.stop_name.lower()
            if normalized in s_name or s_name in normalized:
                return stop
            # Fallback for Malabotha / PTI variants
            if "malabotha" in normalized and "malabotha" in s_name:
                return stop
            if "pti" in normalized and "pti" in s_name:
                return stop
        return None

    def get_stop_by_id(self, stop_id: str) -> Optional[BusStop]:
        """Finds a stop by ID."""
        for stop in self.stops:
            if stop.stop_id == stop_id:
                return stop
        return None


def final_destination_stop(stop_id: str, sequence_order: int,
                           scheduled_morning_time: str, scheduled_afternoon_time: str) -> BusStop:
    """The last stop of every route: Hadi Chattar (set in AppConfig.FINAL_DESTINATION)."""
    dest = AppConfig.FINAL_DESTINATION
    return BusStop(
        stop_id=stop_id,
        stop_name=dest["stop_name"],
        latitude=dest["latitude"],
        longitude=dest["longitude"],
        sequence_order=sequence_order,
        scheduled_morning_time=scheduled_morning_time,
        scheduled_afternoon_time=scheduled_afternoon_time,
        landmark_hint=dest.get("landmark_hint", "")
    )


FINAL_DESTINATION_WAYPOINT = {
    "lat": AppConfig.FINAL_DESTINATION["latitude"],
    "lng": AppConfig.FINAL_DESTINATION["longitude"]
}


def get_predefined_khulna_university_routes() -> Dict[str, BusRoute]:
    """
    Initializes official Khulna University bus routes.
    Includes Route 1 specifically serving Malabotha as requested by student.
    """
    routes: Dict[str, BusRoute] = {}

    # -------------------------------------------------------------
    # Route 1: Malabotha & Rupsha - Khulna University Express
    # -------------------------------------------------------------
    route_1_stops = [
        BusStop(
            stop_id="r1_s1",
            stop_name="Malabotha More",
            latitude=22.7725,
            longitude=89.5855,
            sequence_order=1,
            scheduled_morning_time="08:35 AM",
            scheduled_afternoon_time="02:10 PM",
            landmark_hint="Malabotha More / Bazar Bus Stand"
        ),
        BusStop(
            stop_id="r1_s2",
            stop_name="Rupsha Bridge Toll Plaza",
            latitude=22.7840,
            longitude=89.5780,
            sequence_order=2,
            scheduled_morning_time="08:42 AM",
            scheduled_afternoon_time="02:18 PM",
            landmark_hint="Khan Jahan Ali Bridge West Toll Booth"
        ),
        BusStop(
            stop_id="r1_s3",
            stop_name="Labanchara Ghat",
            latitude=22.7935,
            longitude=89.5695,
            sequence_order=3,
            scheduled_morning_time="08:48 AM",
            scheduled_afternoon_time="02:25 PM",
            landmark_hint="Labanchara Main Road Intersection"
        ),
        BusStop(
            stop_id="r1_s4",
            stop_name="Rupsha Traffic Mor",
            latitude=22.8020,
            longitude=89.5630,
            sequence_order=4,
            scheduled_morning_time="08:54 AM",
            scheduled_afternoon_time="02:32 PM",
            landmark_hint="Rupsha Ferry Ghat Crossing"
        ),
        BusStop(
            stop_id="r1_s5",
            stop_name="PTI More",
            latitude=22.8125,
            longitude=89.5585,
            sequence_order=5,
            scheduled_morning_time="08:59 AM",
            scheduled_afternoon_time="02:37 PM",
            landmark_hint="Primary Teachers Training Institute (PTI) Junction"
        ),
        BusStop(
            stop_id="r1_s6",
            stop_name="Royal Mor",
            latitude=22.8222,
            longitude=89.5605,
            sequence_order=6,
            scheduled_morning_time="09:03 AM",
            scheduled_afternoon_time="02:41 PM",
            landmark_hint="Hotel Royal International Square"
        ),
        BusStop(
            stop_id="r1_s7",
            stop_name="Moylapota Mor",
            latitude=22.8185,
            longitude=89.5535,
            sequence_order=7,
            scheduled_morning_time="09:08 AM",
            scheduled_afternoon_time="02:46 PM",
            landmark_hint="Moylapota Square / Ahsan Ahmed Road Junction"
        ),
        BusStop(
            stop_id="r1_s8",
            stop_name="Sonadanga Bus Terminal Mor",
            latitude=22.8225,
            longitude=89.5420,
            sequence_order=8,
            scheduled_morning_time="09:14 AM",
            scheduled_afternoon_time="02:53 PM",
            landmark_hint="Sonadanga Inter-district Terminal Gate"
        ),
        BusStop(
            stop_id="r1_s9",
            stop_name="Gollamari Mor",
            latitude=22.8090,
            longitude=89.5398,
            sequence_order=9,
            scheduled_morning_time="09:20 AM",
            scheduled_afternoon_time="02:58 PM",
            landmark_hint="Gollamari Bridge Approach / Memorial"
        ),
        # Route 1 goes straight from Gollamari into campus and ends at Hadi Chattar
        # (it no longer runs past KU to Zero Point and back).
        final_destination_stop(
            stop_id="r1_s10",
            sequence_order=10,
            scheduled_morning_time="09:30 AM",
            scheduled_afternoon_time="03:10 PM"
        )
    ]

    # Detailed polyline waypoints along the road for Route 1
    route_1_waypoints = [
        {"lat": 22.7725, "lng": 89.5855}, # Malabotha More
        {"lat": 22.7780, "lng": 89.5815},
        {"lat": 22.7840, "lng": 89.5780}, # Rupsha Bridge
        {"lat": 22.7890, "lng": 89.5740},
        {"lat": 22.7935, "lng": 89.5695}, # Labanchara
        {"lat": 22.8020, "lng": 89.5630}, # Rupsha Mor
        {"lat": 22.8125, "lng": 89.5585}, # PTI More
        {"lat": 22.8222, "lng": 89.5605}, # Royal Mor
        {"lat": 22.8205, "lng": 89.5570},
        {"lat": 22.8185, "lng": 89.5535}, # Moylapota
        {"lat": 22.8210, "lng": 89.5475},
        {"lat": 22.8225, "lng": 89.5420}, # Sonadanga
        {"lat": 22.8150, "lng": 89.5408},
        {"lat": 22.8090, "lng": 89.5398}, # Gollamari
        {"lat": 22.8040, "lng": 89.5350},
        FINAL_DESTINATION_WAYPOINT  # Hadi Chattar (final destination)
    ]

    route_1 = BusRoute(
        route_id="KU-R01",
        route_name="Malabotha - Rupsha - KU Line",
        route_code="R1-MALABOTHA",
        color_hex="#2563EB", # Modern Royal Blue
        description="Connects Malabotha, Rupsha Bridge, Royal Mor, Moylapota, and Gollamari to Hadi Chattar, Khulna University.",
        stops=route_1_stops,
        polyline_waypoints=route_1_waypoints
    )
    routes[route_1.route_id] = route_1

    # -------------------------------------------------------------
    # Route 2: Phultala - Daulatpur - Shibbari - KU Campus
    # -------------------------------------------------------------
    route_2_stops = [
        BusStop(
            stop_id="r2_s1",
            stop_name="Phultala Super Market",
            latitude=22.9780,
            longitude=89.4620,
            sequence_order=1,
            scheduled_morning_time="08:15 AM",
            scheduled_afternoon_time="02:00 PM",
            landmark_hint="Phultala Bazar Bus Stand"
        ),
        BusStop(
            stop_id="r2_s2",
            stop_name="Shiromoni Cantonment Gate",
            latitude=22.9250,
            longitude=89.4880,
            sequence_order=2,
            scheduled_morning_time="08:28 AM",
            scheduled_afternoon_time="02:15 PM",
            landmark_hint="Shiromoni Bazar Junction"
        ),
        BusStop(
            stop_id="r2_s3",
            stop_name="Daulatpur Bus Stand",
            latitude=22.8750,
            longitude=89.5160,
            sequence_order=3,
            scheduled_morning_time="08:40 AM",
            scheduled_afternoon_time="02:30 PM",
            landmark_hint="Daulatpur BL College Mor"
        ),
        BusStop(
            stop_id="r2_s4",
            stop_name="Khalishpur Notun Rasta",
            latitude=22.8580,
            longitude=89.5290,
            sequence_order=4,
            scheduled_morning_time="08:48 AM",
            scheduled_afternoon_time="02:40 PM",
            landmark_hint="BIDC Road Intersection"
        ),
        BusStop(
            stop_id="r2_s5",
            stop_name="Boyra Dakbangla Mor",
            latitude=22.8420,
            longitude=89.5380,
            sequence_order=5,
            scheduled_morning_time="08:58 AM",
            scheduled_afternoon_time="02:48 PM",
            landmark_hint="Boyra Police Line Road"
        ),
        BusStop(
            stop_id="r2_s6",
            stop_name="Shibbari Mor",
            latitude=22.8285,
            longitude=89.5535,
            sequence_order=6,
            scheduled_morning_time="09:08 AM",
            scheduled_afternoon_time="02:56 PM",
            landmark_hint="Shibbari Public Hall Crossing"
        ),
        BusStop(
            stop_id="r2_s7",
            stop_name="Gollamari Mor",
            latitude=22.8090,
            longitude=89.5398,
            sequence_order=7,
            scheduled_morning_time="09:20 AM",
            scheduled_afternoon_time="03:05 PM",
            landmark_hint="Gollamari Memorial Bridge"
        ),
        final_destination_stop(
            stop_id="r2_s8",
            sequence_order=8,
            scheduled_morning_time="09:28 AM",
            scheduled_afternoon_time="03:12 PM"
        )
    ]

    route_2_waypoints = [
        {"lat": 22.9780, "lng": 89.4620}, # Phultala
        {"lat": 22.9250, "lng": 89.4880}, # Shiromoni
        {"lat": 22.8750, "lng": 89.5160}, # Daulatpur
        {"lat": 22.8580, "lng": 89.5290}, # Khalishpur
        {"lat": 22.8420, "lng": 89.5380}, # Boyra
        {"lat": 22.8285, "lng": 89.5535}, # Shibbari
        {"lat": 22.8185, "lng": 89.5460},
        {"lat": 22.8090, "lng": 89.5398}, # Gollamari
        FINAL_DESTINATION_WAYPOINT  # Hadi Chattar (final destination)
    ]

    route_2 = BusRoute(
        route_id="KU-R02",
        route_name="Phultala - Daulatpur - Shibbari Line",
        route_code="R2-NORTH",
        color_hex="#059669", # Emerald Green
        description="Covers North Khulna from Phultala through Daulatpur, Boyra, and Shibbari to Khulna University.",
        stops=route_2_stops,
        polyline_waypoints=route_2_waypoints
    )
    routes[route_2.route_id] = route_2

    # -------------------------------------------------------------
    # Route 3: Dumuria - Chuknagar - Zero Point - KU Campus
    # -------------------------------------------------------------
    route_3_stops = [
        BusStop(
            stop_id="r3_s1",
            stop_name="Dumuria Hospital Mor",
            latitude=22.8105,
            longitude=89.4250,
            sequence_order=1,
            scheduled_morning_time="08:40 AM",
            scheduled_afternoon_time="02:20 PM",
            landmark_hint="Dumuria Upazila Complex"
        ),
        BusStop(
            stop_id="r3_s2",
            stop_name="Gutudia Bazar",
            latitude=22.8055,
            longitude=89.4720,
            sequence_order=2,
            scheduled_morning_time="08:55 AM",
            scheduled_afternoon_time="02:35 PM",
            landmark_hint="Gutudia High School Stand"
        ),
        BusStop(
            stop_id="r3_s3",
            stop_name="Zero Point Crossing",
            latitude=22.7985,
            longitude=89.5312,
            sequence_order=3,
            scheduled_morning_time="09:15 AM",
            scheduled_afternoon_time="02:55 PM",
            landmark_hint="Khulna Bypass Intersection"
        ),
        final_destination_stop(
            stop_id="r3_s4",
            sequence_order=4,
            scheduled_morning_time="09:25 AM",
            scheduled_afternoon_time="03:05 PM"
        )
    ]

    route_3_waypoints = [
        {"lat": 22.8105, "lng": 89.4250},
        {"lat": 22.8055, "lng": 89.4720},
        {"lat": 22.7985, "lng": 89.5312},
        FINAL_DESTINATION_WAYPOINT  # Hadi Chattar (final destination)
    ]

    route_3 = BusRoute(
        route_id="KU-R03",
        route_name="Dumuria - Zero Point Line",
        route_code="R3-WEST",
        color_hex="#D97706", # Amber Orange
        description="Covers West Khulna from Dumuria along Satkhira highway to Khulna University.",
        stops=route_3_stops,
        polyline_waypoints=route_3_waypoints
    )
    routes[route_3.route_id] = route_3

    # Draw the built-in routes along the real roads, and remember their stops as the
    # points the route editor starts from
    from models.route_paths import ROAD_PATHS
    for route in routes.values():
        if route.route_id in ROAD_PATHS:
            route.polyline_waypoints = [{"lat": lat, "lng": lng} for lat, lng in ROAD_PATHS[route.route_id]]
        route.via_points = [
            {"lat": s.latitude, "lng": s.longitude, "name": s.stop_name}
            for s in route.stops if s.stop_name != AppConfig.FINAL_DESTINATION["stop_name"]
        ]
        ensure_route_ends_at_final_destination(route)

    return routes


def ensure_route_ends_at_final_destination(route: BusRoute) -> None:
    """Makes sure a route's last stop and last waypoint are the final destination (Hadi Chattar)."""
    dest = AppConfig.FINAL_DESTINATION
    if not route.stops or route.stops[-1].stop_name != dest["stop_name"]:
        last = route.stops[-1] if route.stops else None
        route.stops.append(final_destination_stop(
            stop_id=f"{route.route_id.lower()}_dest",
            sequence_order=len(route.stops) + 1,
            scheduled_morning_time=last.scheduled_morning_time if last else "",
            scheduled_afternoon_time=last.scheduled_afternoon_time if last else ""
        ))
    if not route.polyline_waypoints or route.polyline_waypoints[-1] != FINAL_DESTINATION_WAYPOINT:
        route.polyline_waypoints.append(dict(FINAL_DESTINATION_WAYPOINT))
