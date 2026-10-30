"""
Khulna University Bus Tracker (BusPlus)
ETA and Geolocation Calculation Service
"""

import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

class ETAService:
    """Provides distance, bearing, and estimated arrival time calculations."""

    EARTH_RADIUS_KM = 6371.0088

    @classmethod
    def calculate_haversine_distance_km(
        cls,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculates the great-circle distance between two points on the Earth
        using the Haversine formula in kilometers.
        """
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2.0) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

        return cls.EARTH_RADIUS_KM * c

    @classmethod
    def calculate_bearing_degrees(
        cls,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """Calculates initial compass heading (bearing in degrees 0-360) from point 1 to point 2."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_lambda = math.radians(lon2 - lon1)

        y = math.sin(delta_lambda) * math.cos(phi2)
        x = (math.cos(phi1) * math.sin(phi2) -
             math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))

        theta = math.atan2(y, x)
        bearing = (math.degrees(theta) + 360.0) % 360.0
        return round(bearing, 1)

    @classmethod
    def estimate_eta(
        cls,
        current_lat: float,
        current_lng: float,
        target_lat: float,
        target_lng: float,
        current_speed_kmh: float = 0.0,
        intermediate_stops_count: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates estimated travel time and estimated time of arrival (ETA).
        Accounts for road tortuosity factor (~1.25 for city roads) and stop dwell times (~1.5 min/stop).
        """
        direct_dist_km = cls.calculate_haversine_distance_km(
            current_lat, current_lng, target_lat, target_lng
        )

        # Approximate road distance factoring traffic bends and intersections
        road_distance_km = direct_dist_km * 1.25

        # Speed estimation: If bus is actively moving > 10 km/h, blend with live speed;
        # otherwise use standard urban bus average (25 km/h).
        if current_speed_kmh >= 12.0:
            effective_speed_kmh = (current_speed_kmh * 0.4) + (25.0 * 0.6)
        else:
            effective_speed_kmh = 24.0

        # Transit time in minutes
        transit_minutes = (road_distance_km / effective_speed_kmh) * 60.0

        # Add ~1.5 minutes dwell time per intermediate stop
        dwell_minutes = intermediate_stops_count * 1.5

        total_minutes = round(transit_minutes + dwell_minutes, 1)

        # Arrival clock time based on local current time
        now = datetime.now()
        arrival_datetime = now + timedelta(minutes=total_minutes)
        arrival_time_formatted = arrival_datetime.strftime("%I:%M %p")

        # Proximity category
        if direct_dist_km < 0.15:
            proximity_status = "ARRIVED"
        elif total_minutes <= 5.0 or direct_dist_km <= 1.5:
            proximity_status = "APPROACHING"
        elif total_minutes <= 15.0:
            proximity_status = "IN_TRANSIT"
        else:
            proximity_status = "SCHEDULED"

        return {
            "distance_km": round(direct_dist_km, 2),
            "estimated_road_km": round(road_distance_km, 2),
            "eta_minutes": total_minutes,
            "estimated_arrival_clock_time": arrival_time_formatted,
            "effective_speed_kmh": round(effective_speed_kmh, 1),
            "proximity_status": proximity_status
        }
