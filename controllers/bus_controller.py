"""
Live buses: the public bus feed for maps, and the driver's phone API.

Public (no sign-in, read only):
  GET  /api/buses            every bus right now (?audience=student|teacher)
  GET  /api/buses/stream     the same, pushed live as Server-Sent Events

Driver's phone (signed-in driver only, always their own bus):
  POST /api/driver/location          GPS position, about once a second
  POST /api/driver/trip/start        go online
  POST /api/driver/trip/stop         go offline
  GET  /api/driver/assignment        today's bus and route (duty card)
  POST /api/driver/assignment/seen   duty card was read
"""

import json
import time
from datetime import datetime

from flask import Blueprint, Response, session, stream_with_context

from config import Config
from content.words.bus_schedule import DAY_NAMES, MONTH_NAMES
from controllers.helpers import audience_arg, driver_required, fail, json_body, ok, optional_float
from services import geo, schedule_service, tracking, users
from services.words import say

bus_bp = Blueprint("buses", __name__)

STREAM_KEEPALIVE_S = 15.0    # send a comment line this often so proxies keep the connection open
STREAM_COALESCE_S = 0.25     # group rapid changes: at most ~4 pushes per second


@bus_bp.get("/api/buses")
def list_buses():
    """Every bus (or only student / teacher buses) with live position, route and trail."""
    buses = tracking.all_buses(audience_arg())
    return ok(count=len(buses), buses=buses)


@bus_bp.get("/api/buses/stream")
def stream_buses():
    """
    Live bus feed (Server-Sent Events). The browser's EventSource keeps this open;
    every time any bus changes the full list is pushed at once.
    """
    audience = audience_arg()

    def events():
        yield "retry: 2000\n\n"                      # browser reconnects after 2 s if the line drops
        version = -1
        while True:
            new_version = tracking.wait_for_change(version, timeout=STREAM_KEEPALIVE_S)
            if new_version == version:
                yield ": keep-alive\n\n"
                continue
            version = new_version
            payload = {"timestamp": time.time(), "buses": tracking.all_buses(audience)}
            yield f"data: {json.dumps(payload)}\n\n"
            time.sleep(STREAM_COALESCE_S)

    return Response(stream_with_context(events()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Driver's phone
# ---------------------------------------------------------------------------
@bus_bp.post("/api/driver/location")
@driver_required
def driver_location(bus_id: str):
    """GPS position from the driver's phone: {"latitude", "longitude", "speed_kmh"?, "heading_deg"?}."""
    data = json_body()
    latitude, longitude = optional_float(data.get("latitude")), optional_float(data.get("longitude"))
    if latitude is None or longitude is None:
        return fail(say("Valid latitude and longitude are required."))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return fail(say("Latitude/longitude out of range."))
    bus = tracking.update_location(bus_id, latitude, longitude,
                                   speed_kmh=optional_float(data.get("speed_kmh")),
                                   heading_deg=optional_float(data.get("heading_deg")))
    return ok(bus=bus)


@bus_bp.post("/api/driver/trip/start")
@driver_required
def start_trip(bus_id: str):
    """The driver switched to Online."""
    return ok(bus=tracking.start_trip(bus_id))


@bus_bp.post("/api/driver/trip/stop")
@driver_required
def stop_trip(bus_id: str):
    """The driver switched to Offline: the bus disappears from every map."""
    return ok(bus=tracking.stop_trip(bus_id))


@bus_bp.get("/api/driver/assignment")
@driver_required
def driver_assignment(bus_id: str):
    """
    Today's duty for the driver's bus-icon menu: which bus, which route, where it starts,
    and whether the admin changed it today (shown until the driver has read it).
    """
    driver = users.get_driver(session["driver_id"])
    bus = tracking.get_bus(bus_id)
    route = tracking.get_route(bus.assigned_route_id)
    stops = route.stops if route else []
    today = geo.local_now().date()
    changed_at = _local_date(driver.assignment_updated_at)
    unseen = bool(driver.assignment_updated_at) and (
        not driver.assignment_seen_at or driver.assignment_seen_at < driver.assignment_updated_at)
    return ok(assignment={
        "date_label": say("{day}, {date} {month}", day=DAY_NAMES[schedule_service.today_key()],
                          date=geo.local_now().day, month=MONTH_NAMES[geo.local_now().month - 1]),
        "bus_id": bus.bus_id,
        "bus_number": bus.bus_number,
        "bus_name": bus.bus_name,
        "bus_color": bus.color_hex,
        "license_plate": bus.license_plate,
        "route_id": route.route_id if route else None,
        "route_name": route.route_name if route else None,
        "route_color": route.color_hex if route else None,
        # Routes drawn in the backend may have no named start: then only the route name is shown.
        "from_stop": stops[0].stop_name if len(stops) > 1 else None,
        "from_time": stops[0].scheduled_morning_time if len(stops) > 1 else None,
        "to_stop": stops[-1].stop_name if stops else Config.FINAL_DESTINATION["stop_name"],
        "changed_today": changed_at == today,
        "unseen": unseen,
    })


@bus_bp.post("/api/driver/assignment/seen")
@driver_required
def driver_assignment_seen(bus_id: str):
    """The driver opened the duty card: clear the "new" dot."""
    users.mark_duty_seen(session["driver_id"])
    return ok()


def _local_date(iso_text: str | None):
    """The Bangladesh calendar date of a saved UTC timestamp (None if missing or unreadable)."""
    try:
        return datetime.fromisoformat(iso_text).astimezone(geo.LOCAL_TZ).date() if iso_text else None
    except ValueError:
        return None
