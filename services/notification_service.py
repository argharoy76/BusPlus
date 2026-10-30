"""
Khulna University Bus Tracker (BusPlus)
Proximity Alert and Notification Service
"""

from typing import Dict, Any, Optional
from models.bus import Bus
from models.route import BusStop, BusRoute
from services.eta_service import ETAService

class NotificationService:
    """Evaluates bus proximity against student boarding stops to generate timely alerts."""

    DEFAULT_THRESHOLD_MINUTES = 5.0

    @classmethod
    def evaluate_stop_proximity_alert(
        cls,
        bus: Bus,
        route: BusRoute,
        target_stop: BusStop,
        custom_threshold_minutes: float = 5.0
    ) -> Dict[str, Any]:
        """
        Determines whether an alert should be triggered for a passenger waiting at target_stop.
        Returns a rich alert payload for both audio and visual notifications.
        """
        # If bus is not actively broadcasting GPS, return IDLE state (no false alerts)
        if not bus.is_active:
            return {
                "bus_id": bus.bus_id,
                "bus_number": bus.bus_number,
                "bus_name": bus.bus_name,
                "is_active": False,
                "target_stop_name": target_stop.stop_name if target_stop else "Your Stop",
                "eta_minutes": None,
                "distance_km": None,
                "bus_speed_kmh": 0.0,
                "estimated_arrival_clock_time": "--",
                "is_alert_triggered": False,
                "urgency_level": "IDLE",
                "alert_title": f"{bus.bus_name} Offline",
                "alert_message": "Driver has not turned on GPS broadcast yet.",
                "should_play_chime": False
            }

        # Determine intermediate stops between bus and target stop
        bus_stop_idx = bus.current_stop_index          # index of the bus's NEXT stop
        target_stop_idx = target_stop.sequence_order - 1
        intermediate_stops = max(0, target_stop_idx - bus_stop_idx - 1)

        # Bus has already gone past this stop (its next stop is further along the route):
        # it is not coming here any more, so no countdown and no alert.
        distance_now_km = ETAService.calculate_haversine_distance_km(
            bus.current_latitude, bus.current_longitude, target_stop.latitude, target_stop.longitude)
        # (0.25 km: beyond the 0.2 km "at the stop" radius used for next-stop tracking)
        if bus_stop_idx > target_stop_idx and distance_now_km > 0.25:
            return {
                "bus_id": bus.bus_id,
                "bus_number": bus.bus_number,
                "bus_name": bus.bus_name,
                "is_active": True,
                "has_passed_stop": True,
                "route_name": route.route_name,
                "target_stop_name": target_stop.stop_name,
                "is_alert_triggered": False,
                "urgency_level": "PASSED",
                "alert_title": f"{bus.bus_name} has passed {target_stop.stop_name}",
                "alert_message": "",
                "should_play_chime": False,
                "eta_minutes": None,
                "distance_km": round(distance_now_km, 2),
                "estimated_arrival_clock_time": "--",
                "scheduled_morning_time": target_stop.scheduled_morning_time,
                "bus_speed_kmh": bus.speed_kmh,
                "bus_trip_status": bus.trip_status
            }

        eta_info = ETAService.estimate_eta(
            current_lat=bus.current_latitude,
            current_lng=bus.current_longitude,
            target_lat=target_stop.latitude,
            target_lng=target_stop.longitude,
            current_speed_kmh=bus.speed_kmh,
            intermediate_stops_count=intermediate_stops
        )

        eta_minutes = eta_info["eta_minutes"]
        distance_km = eta_info["distance_km"]
        arrival_time = eta_info["estimated_arrival_clock_time"]

        is_alert_triggered = False
        urgency_level = "NORMAL"
        alert_title = ""
        alert_message = ""
        should_play_chime = False

        if distance_km <= 0.15:
            # Bus has arrived at the stop
            is_alert_triggered = True
            urgency_level = "ARRIVED"
            alert_title = f"Bus Arrived at {target_stop.stop_name}!"
            alert_message = f"{bus.bus_name} has reached your boarding stop. Please board now!"
            should_play_chime = True
        elif eta_minutes <= 2.0:
            # Bus is pulling up in 1-2 minutes
            is_alert_triggered = True
            urgency_level = "CRITICAL"
            alert_title = f"Bus Arriving in ~{int(eta_minutes)} Min!"
            alert_message = (
                f"{bus.bus_name} is only {distance_km} km away from {target_stop.stop_name}. "
                f"Be ready at the curb! Expected at {arrival_time}."
            )
            should_play_chime = True
        elif eta_minutes <= custom_threshold_minutes:
            # The classic 5-minute alert specifically highlighted by the user!
            is_alert_triggered = True
            urgency_level = "WARNING"
            alert_title = f"{bus.bus_name} Approaching {target_stop.stop_name} (~{int(eta_minutes)} min away)"
            alert_message = (
                f"Your bus is approximately {round(eta_minutes, 1)} minutes away ({distance_km} km). "
                f"It is estimated to reach {target_stop.stop_name} at {arrival_time}."
            )
            should_play_chime = True
        else:
            urgency_level = "INFO"
            alert_title = f"{bus.bus_name} on the way"
            alert_message = (
                f"Bus is running en-route to {target_stop.stop_name}. "
                f"ETA is {round(eta_minutes, 1)} mins ({arrival_time})."
            )
            should_play_chime = False

        return {
            "bus_id": bus.bus_id,
            "bus_number": bus.bus_number,
            "bus_name": bus.bus_name,
            "is_active": True,
            "route_name": route.route_name,
            "target_stop_name": target_stop.stop_name,
            "is_alert_triggered": is_alert_triggered,
            "urgency_level": urgency_level,
            "alert_title": alert_title,
            "alert_message": alert_message,
            "should_play_chime": should_play_chime,
            "eta_minutes": eta_minutes,
            "distance_km": distance_km,
            "estimated_arrival_clock_time": arrival_time,
            "scheduled_morning_time": target_stop.scheduled_morning_time,
            "bus_speed_kmh": bus.speed_kmh,
            "bus_trip_status": bus.trip_status
        }
