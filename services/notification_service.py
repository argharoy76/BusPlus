"""
"Your bus is coming" alerts for students and teachers.

The rider's map asks every few seconds how far the bus is from their home
stop. `arrival_alert()` answers with an ETA and, when the bus is within the
rider's chosen number of minutes, an alert that makes the phone chime.
"""

from models.bus import Bus
from models.route import BusRoute, BusStop
from services import geo
from services.words import say

ARRIVED_RADIUS_KM = 0.15      # this close to the stop = the bus is here
PASSED_MARGIN_KM = 0.25       # a bus past the stop and further than this has gone by
CRITICAL_MINUTES = 2.0        # "be ready at the curb"


def arrival_alert(bus: Bus, route: BusRoute, stop: BusStop, notify_minutes: float) -> dict:
    """
    How far `bus` is from `stop`, and whether to alert the rider.

    urgency_level is one of:
      IDLE      the bus is offline (no ETA)
      PASSED    the bus already went past this stop (no ETA, no alert)
      ARRIVED   the bus is at the stop                       -> alert
      CRITICAL  about 2 minutes away                         -> alert
      WARNING   within the rider's `notify_minutes`          -> alert
      INFO      on the way, further than that
    """
    base = {
        "bus_id": bus.bus_id,
        "bus_number": bus.bus_number,
        "bus_name": bus.bus_name,
        "route_id": route.route_id,
        "route_name": route.route_name,
        "target_stop_name": stop.stop_name,
        "is_active": bus.is_active,
        "bus_speed_kmh": round(bus.speed_kmh, 1),
        "eta_minutes": None,
        "distance_km": None,
        "estimated_arrival_clock_time": "--",
        "is_alert_triggered": False,
        "should_play_chime": False,
        "alert_message": "",
    }

    if not bus.is_active:
        return {**base, "urgency_level": "IDLE", "alert_title": say("{bus} is offline", bus=bus.bus_name)}

    distance_now = geo.distance_km(bus.current_latitude, bus.current_longitude, stop.latitude, stop.longitude)
    stop_index = stop.sequence_order - 1
    if bus.current_stop_index > stop_index and distance_now > PASSED_MARGIN_KM:
        return {**base, "urgency_level": "PASSED", "distance_km": round(distance_now, 2),
                "alert_title": say("{bus} has passed {stop}", bus=bus.bus_name, stop=stop.stop_name)}

    eta = geo.estimate_eta(bus.current_latitude, bus.current_longitude, stop.latitude, stop.longitude,
                           bus_speed_kmh=bus.speed_kmh,
                           stops_between=max(0, stop_index - bus.current_stop_index - 1))
    minutes, km, clock = eta["eta_minutes"], eta["distance_km"], eta["estimated_arrival_clock_time"]

    if km <= ARRIVED_RADIUS_KM:
        level, title = "ARRIVED", say("{bus} is at {stop}!", bus=bus.bus_name, stop=stop.stop_name)
        message = say("Your bus has reached your stop. Please board now.")
    elif minutes <= CRITICAL_MINUTES:
        level, title = "CRITICAL", say("{bus} arrives in ~{minutes} min!", bus=bus.bus_name,
                                        minutes=max(1, int(minutes)))
        message = say("Only {km} km from {stop}. Be ready at the curb (about {clock}).", km=km, stop=stop.stop_name,
                      clock=clock)
    elif minutes <= notify_minutes:
        level, title = "WARNING", say("{bus} is ~{minutes} min from {stop}", bus=bus.bus_name, minutes=int(minutes),
                                      stop=stop.stop_name)
        message = say("About {minutes} minutes away ({km} km). Expected at {clock}.", minutes=round(minutes, 1), km=km,
                      clock=clock)
    else:
        level, title = "INFO", say("{bus} is on the way", bus=bus.bus_name)
        message = say("Heading to {stop}. ETA {minutes} min ({clock}).", stop=stop.stop_name, minutes=round(minutes, 1),
                      clock=clock)

    triggered = level != "INFO"
    return {**base, "urgency_level": level, "alert_title": title, "alert_message": message,
            "eta_minutes": minutes, "distance_km": km, "estimated_arrival_clock_time": clock,
            "is_alert_triggered": triggered, "should_play_chime": triggered}
