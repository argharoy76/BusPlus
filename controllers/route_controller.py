"""
Khulna University Bus Tracker (BusPlus)
Route & ETA API Controller
"""

from flask import Blueprint, request, jsonify
from services.tracking_service import TrackingService
from services.notification_service import NotificationService
from services.eta_service import ETAService

route_bp = Blueprint("route_bp", __name__)
tracking_service = TrackingService()

@route_bp.route("/api/routes", methods=["GET"])
def get_all_routes():
    """Returns all pre-configured Khulna University bus routes."""
    routes = tracking_service.get_all_routes()
    return jsonify({
        "success": True,
        "count": len(routes),
        "routes": routes
    })


@route_bp.route("/api/routes/<route_id>", methods=["GET"])
def get_route_details(route_id: str):
    """Returns a specific route including its stops and road polyline waypoints."""
    route = tracking_service.get_route_by_id(route_id)
    if not route:
        return jsonify({"success": False, "message": f"Route {route_id} not found."}), 404

    return jsonify({"success": True, "route": route.to_dict()})


@route_bp.route("/api/eta", methods=["GET"])
def calculate_eta():
    """
    Calculates ETA and distance from the active bus to a requested stop or student GPS.
    Query parameters:
      - route_id (optional, defaults to KU-R01)
      - stop_name or stop_id (e.g. "Malabotha Bazar")
      - student_lat, student_lng (optional live coordinates)
    """
    route_id = request.args.get("route_id", "KU-R01")
    stop_name = request.args.get("stop_name", "Malabotha Bazar")
    stop_id = request.args.get("stop_id")
    student_lat = request.args.get("student_lat", type=float)
    student_lng = request.args.get("student_lng", type=float)

    route = tracking_service.get_route_by_id(route_id)
    if not route:
        return jsonify({"success": False, "message": f"Route {route_id} not found."}), 404

    # Locate target stop
    target_stop = None
    if stop_id:
        target_stop = route.get_stop_by_id(stop_id)
    if not target_stop and stop_name:
        target_stop = route.get_stop_by_name(stop_name)

    if not target_stop and not (student_lat and student_lng):
        return jsonify({"success": False, "message": "Could not identify stop or student coordinates."}), 400

    # Find the bus serving this route
    target_bus = None
    all_buses = tracking_service.get_all_buses()
    for b in all_buses:
        if b.get("assigned_route_id") == route_id:
            target_bus = tracking_service.get_bus_by_id(b["bus_id"])
            break

    if not target_bus:
        target_bus = tracking_service.get_bus_by_id("KU-BUS-01")

    # If student provided live GPS coordinates directly, calculate direct ETA
    if student_lat is not None and student_lng is not None:
        if not target_bus.is_active:
            return jsonify({
                "success": True,
                "target": "student_gps",
                "bus": target_bus.to_dict(),
                "eta": {
                    "is_active": False,
                    "eta_minutes": None,
                    "distance_km": None,
                    "estimated_arrival_clock_time": "--",
                    "is_alert_triggered": False,
                    "urgency_level": "IDLE"
                }
            })
        eta_result = ETAService.estimate_eta(
            current_lat=target_bus.current_latitude,
            current_lng=target_bus.current_longitude,
            target_lat=student_lat,
            target_lng=student_lng,
            current_speed_kmh=target_bus.speed_kmh
        )
        return jsonify({
            "success": True,
            "target": "student_gps",
            "bus": target_bus.to_dict(),
            "eta": eta_result
        })

    # Stop-based ETA
    alert_info = NotificationService.evaluate_stop_proximity_alert(
        bus=target_bus,
        route=route,
        target_stop=target_stop,
        custom_threshold_minutes=5.0
    )

    return jsonify({
        "success": True,
        "target_stop": target_stop.to_dict(),
        "bus": target_bus.to_dict(),
        "eta": alert_info
    })


def _pick_best_bus_for_stop(route_id, target_stop, audience=None):
    """
    Chooses which bus to watch for a stop when the student hasn't picked one:
    the live bus on that route closest to the stop, otherwise the first bus on the route.
    """
    candidates = [
        tracking_service.get_bus_by_id(b["bus_id"])
        for b in tracking_service.get_all_buses(audience)
        if b.get("assigned_route_id") == route_id
    ]
    candidates = [b for b in candidates if b]
    live = [b for b in candidates if b.is_active]
    if live and target_stop:
        # Prefer buses that are still on their way to the stop (haven't passed it yet)
        target_idx = target_stop.sequence_order - 1
        coming = [b for b in live if b.current_stop_index <= target_idx]
        live = coming or live
        return min(live, key=lambda b: ETAService.calculate_haversine_distance_km(
            b.current_latitude, b.current_longitude, target_stop.latitude, target_stop.longitude))
    if candidates:
        return candidates[0]
    if audience:
        return None   # no student/teacher bus on this route
    return tracking_service.get_bus_by_id("KU-BUS-01")


@route_bp.route("/api/notification/check", methods=["GET"])
def check_proximity_notification():
    """
    Evaluates whether the arrival notification should fire for a student's stop.
    Query parameters:
      - route_id, stop_name: the student's stop
      - bus_id (optional): watch this specific bus (its own route is used)
      - alert_threshold_minutes (optional, default 5)
    """
    route_id = request.args.get("route_id", "KU-R01")
    stop_name = request.args.get("stop_name", "Malabotha More")
    bus_id = request.args.get("bus_id")
    audience = request.args.get("audience")
    audience = audience if audience in ("student", "teacher") else None
    try:
        threshold_minutes = float(request.args.get("alert_threshold_minutes", 5.0))
    except (TypeError, ValueError):
        threshold_minutes = 5.0

    bus = tracking_service.get_bus_by_id(bus_id) if bus_id else None
    if bus:
        route_id = bus.assigned_route_id

    route = tracking_service.get_route_by_id(route_id)
    if not route:
        return jsonify({"success": False, "message": "Route not found"}), 404

    target_stop = route.get_stop_by_name(stop_name) if stop_name else None
    if not target_stop and route.stops:
        target_stop = route.stops[0]

    if not bus:
        bus = _pick_best_bus_for_stop(route_id, target_stop, audience)
    if not bus:
        return jsonify({"success": True, "alert": None})

    alert_payload = NotificationService.evaluate_stop_proximity_alert(
        bus=bus,
        route=route,
        target_stop=target_stop,
        custom_threshold_minutes=threshold_minutes
    )
    alert_payload["route_id"] = route.route_id

    return jsonify({
        "success": True,
        "alert": alert_payload
    })
