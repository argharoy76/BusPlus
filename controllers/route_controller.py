"""
Routes and arrival alerts for the students' and teachers' map (public, read only).

  GET /api/routes               every route with its road line and stops
  GET /api/schedules            today's bus schedule of every route
  GET /api/notification/check   how far the bus is from the rider's stop, and whether to alert
"""

from flask import Blueprint, request

from config import Config
from controllers.helpers import audience_arg, ok, optional_float
from models.bus import Bus
from models.route import BusStop
from services import geo, schedule_service, tracking
from services.notification_service import arrival_alert

route_bp = Blueprint("routes", __name__)


@route_bp.get("/api/routes")
def list_routes():
    """Every route with its road line, stops and colour."""
    routes = tracking.all_routes()
    return ok(count=len(routes), routes=routes)


@route_bp.get("/api/schedules")
def list_schedules():
    """
    TODAY's timetable of every route for the "Bus schedule" pop-up: morning buses with the
    time they reach the campus, afternoon buses with the time they leave it.
    ?audience=student|teacher|... leaves out buses meant for another group (drivers see all).
    """
    return ok(**schedule_service.todays_schedules(audience_arg()))


@route_bp.get("/api/notification/check")
def check_arrival():
    """
    Arrival check for the rider's home stop.

    Query: route_id, stop_name - the rider's stop
           bus_id (optional)   - watch this bus (its own route is then used)
           audience (optional) - only consider student or teacher buses
           alert_threshold_minutes (optional) - "notify me N minutes before"
    Answers {"alert": null} when that rider type has no bus on the route.
    """
    notify_minutes = optional_float(request.args.get("alert_threshold_minutes"))
    notify_minutes = min(max(notify_minutes or Config.DEFAULT_ALERT_MINUTES, 1), 120)
    audience = audience_arg()

    bus = tracking.get_bus(request.args.get("bus_id"))
    route = tracking.get_route(bus.assigned_route_id if bus else request.args.get("route_id"))
    if route is None:
        return ok(alert=None)

    stop = route.get_stop_by_name(request.args.get("stop_name", "")) or route.stops[0]
    bus = bus or _best_bus_for_stop(route.route_id, stop, audience)
    if bus is None:
        return ok(alert=None)
    return ok(alert=arrival_alert(bus, route, stop, notify_minutes))


def _best_bus_for_stop(route_id: str, stop: BusStop, audience: str | None) -> Bus | None:
    """
    Which bus to watch when the rider hasn't picked one: the live bus on the route
    that is still coming to the stop and nearest to it; if none is live, the first bus.
    """
    candidates = tracking.buses_on_route(route_id, audience)
    live = [b for b in candidates if b.is_active]
    if not live:
        return candidates[0] if candidates else None
    coming = [b for b in live if b.current_stop_index <= stop.sequence_order - 1] or live
    return min(coming, key=lambda b: geo.distance_km(b.current_latitude, b.current_longitude,
                                                     stop.latitude, stop.longitude))
