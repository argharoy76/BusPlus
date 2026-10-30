"""
Map maths: distances, compass directions and arrival-time estimates.

All positions are latitude/longitude in degrees (WGS-84, what phones' GPS gives).
"""

import math
from datetime import datetime, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from config import Config

EARTH_RADIUS_KM = 6371.0088          # mean Earth radius
ROAD_FACTOR = 1.25                   # roads bend: real road distance ≈ straight line × 1.25
CITY_BUS_SPEED_KMH = 24.0            # typical bus speed in Khulna traffic
DWELL_MINUTES_PER_STOP = 1.5         # time lost at each stop on the way
LOCAL_TZ = ZoneInfo(Config.TIMEZONE)

# Rough box around Bangladesh, used to reject positions that are obviously wrong.
BANGLADESH_BOUNDS = {"lat": (20.0, 27.0), "lng": (88.0, 93.0)}


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line ("as the crow flies") distance between two points, in km (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compass direction from point 1 to point 2: 0 = north, 90 = east, 180 = south, 270 = west."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lng2 - lng1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return round((math.degrees(math.atan2(y, x)) + 360.0) % 360.0, 1)


def path_length_km(points: list[dict]) -> float:
    """Total length of a line given as [{"lat": .., "lng": ..}, ...], in km."""
    return sum(distance_km(a["lat"], a["lng"], b["lat"], b["lng"]) for a, b in pairwise(points))


def in_bangladesh(lat: float, lng: float) -> bool:
    """True if the point is inside the rough Bangladesh box (catches typos and 0,0 positions)."""
    (lat_min, lat_max), (lng_min, lng_max) = BANGLADESH_BOUNDS["lat"], BANGLADESH_BOUNDS["lng"]
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def local_now() -> datetime:
    """The current time in Bangladesh (the server itself may run on UTC)."""
    return datetime.now(LOCAL_TZ)


def estimate_eta(bus_lat: float, bus_lng: float, target_lat: float, target_lng: float,
                 bus_speed_kmh: float = 0.0, stops_between: int = 0) -> dict:
    """
    Estimate how long a bus needs to reach a point.

    The straight-line distance is stretched by ROAD_FACTOR to approximate the road,
    the bus's live speed is blended with a normal city speed (so one fast or slow
    moment doesn't swing the answer), and every stop in between adds a short wait.

    Returns:
        distance_km:                   straight-line distance now
        eta_minutes:                   estimated minutes until arrival
        estimated_arrival_clock_time:  local clock time of arrival, e.g. "08:42 AM"
    """
    direct_km = distance_km(bus_lat, bus_lng, target_lat, target_lng)
    road_km = direct_km * ROAD_FACTOR

    # Moving: blend the live speed with a normal speed. Standing or crawling: use the normal speed.
    speed = bus_speed_kmh * 0.4 + 25.0 * 0.6 if bus_speed_kmh >= 12.0 else CITY_BUS_SPEED_KMH

    minutes = round(road_km / speed * 60.0 + stops_between * DWELL_MINUTES_PER_STOP, 1)
    arrival = local_now() + timedelta(minutes=minutes)
    return {
        "distance_km": round(direct_km, 2),
        "eta_minutes": minutes,
        "estimated_arrival_clock_time": arrival.strftime("%I:%M %p"),
    }
