"""
Khulna University Bus Tracker (BusPlus)
Bus Tracking and Driver Telemetry API Controller
"""

import json
import time
from flask import Blueprint, request, jsonify, session, Response
from services.tracking_service import TrackingService
from services.user_service import UserService

bus_bp = Blueprint("bus_bp", __name__)
tracking_service = TrackingService()
user_service = UserService()


def _driver_bus_or_error():
    """
    Returns (bus_id, None) for the signed-in driver's own bus, or (None, error_response).
    The bus always comes from the driver's session, never from the request.
    """
    if session.get("role") != "driver" or not session.get("driver_id"):
        return None, (jsonify({"success": False, "message": "Please log in as a driver."}), 401)
    if not user_service.touch_driver(session["driver_id"], session.get("session_token")):
        return None, (jsonify({"success": False, "message": "This account was signed in on another device. Please log in again."}), 409)
    driver = user_service.get_driver_by_id(session["driver_id"])
    bus_id = (driver.assigned_bus_id if driver else None) or session.get("bus_id")
    if not bus_id or not tracking_service.get_bus_by_id(bus_id):
        return None, (jsonify({"success": False, "message": "No bus is assigned to you. Ask the admin."}), 404)
    session["bus_id"] = bus_id
    return bus_id, None


def _optional_float(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None

@bus_bp.route("/api/buses", methods=["GET"])
def get_all_buses():
    """Returns real-time data for KU buses. ?audience=student or ?audience=teacher shows only those buses."""
    audience = request.args.get("audience")
    buses = tracking_service.get_all_buses(audience if audience in ("student", "teacher") else None)
    return jsonify({
        "success": True,
        "count": len(buses),
        "buses": buses
    })


@bus_bp.route("/api/buses/active", methods=["GET"])
def get_active_buses():
    """Returns only buses currently broadcasting GPS coordinates."""
    buses = tracking_service.get_active_buses()
    return jsonify({
        "success": True,
        "count": len(buses),
        "buses": buses
    })


@bus_bp.route("/api/buses/<bus_id>", methods=["GET"])
def get_bus_details(bus_id: str):
    """Returns telemetry and route status for a specific bus."""
    bus = tracking_service.get_bus_by_id(bus_id)
    if not bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404

    bus_dict = bus.to_dict()
    route = tracking_service.get_route_by_id(bus.assigned_route_id)
    if route:
        bus_dict["route_name"] = route.route_name
        bus_dict["route_code"] = route.route_code
        bus_dict["route_color"] = route.color_hex
        bus_dict["route_stops"] = [s.to_dict() for s in route.stops]

    return jsonify({"success": True, "bus": bus_dict})


@bus_bp.route("/api/driver/location", methods=["POST"])
def update_driver_location():
    """
    Called by driver web client (via HTML5 Geolocation API).
    Receives current GPS position, heading, and speed, then updates bus telemetry.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    bus_id, error = _driver_bus_or_error()
    if error:
        return error

    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Valid latitude and longitude are required."}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"success": False, "message": "Latitude/longitude out of range."}), 400

    speed_kmh = _optional_float(data.get("speed_kmh"))        # None = work it out from the movement
    heading_deg = _optional_float(data.get("heading_deg"))   # None = let the server work it out
    trip_status = "EN_ROUTE"

    updated_bus = tracking_service.update_bus_location(
        bus_id=bus_id,
        latitude=latitude,
        longitude=longitude,
        speed_kmh=speed_kmh,
        heading_deg=heading_deg,
        trip_status=trip_status
    )

    if not updated_bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404

    return jsonify({
        "success": True,
        "message": "Location updated successfully.",
        "bus": updated_bus
    })


@bus_bp.route("/api/driver/assignment", methods=["GET"])
def driver_assignment():
    """The signed-in driver's duty for today: which bus to drive on which route."""
    if session.get("role") != "driver" or not session.get("driver_id"):
        return jsonify({"success": False, "message": "Please log in as a driver."}), 401
    driver = user_service.get_driver_by_id(session["driver_id"])
    if not driver:
        return jsonify({"success": False, "message": "Driver not found."}), 404

    from datetime import datetime, timezone, timedelta
    from config import AppConfig
    local = timezone(timedelta(hours=AppConfig.LOCAL_UTC_OFFSET_HOURS))
    now_local = datetime.now(local)

    def local_date(iso):
        try:
            return datetime.fromisoformat(iso).astimezone(local).date() if iso else None
        except ValueError:
            return None

    bus = tracking_service.get_bus_by_id(driver.assigned_bus_id or "")
    route = tracking_service.get_route_by_id(bus.assigned_route_id) if bus else None
    stops = route.stops if route else []
    updated = driver.assignment_updated_at
    unseen = bool(updated) and (not driver.assignment_seen_at or driver.assignment_seen_at < updated)

    return jsonify({
        "success": True,
        "assignment": {
            "date_label": now_local.strftime("%A, %d %B"),
            "bus_id": bus.bus_id if bus else None,
            "bus_number": bus.bus_number if bus else None,
            "bus_name": bus.bus_name if bus else None,
            "bus_color": bus.color_hex if bus else None,
            "license_plate": bus.license_plate if bus else None,
            "route_id": route.route_id if route else None,
            "route_name": route.route_name if route else None,
            "route_color": route.color_hex if route else None,
            # Routes drawn in the backend may have no named start: then just show the route name
            "from_stop": stops[0].stop_name if len(stops) > 1 else None,
            "from_time": stops[0].scheduled_morning_time if len(stops) > 1 else None,
            "to_stop": stops[-1].stop_name if stops else None,
            "changed_today": local_date(updated) == now_local.date(),
            "unseen": unseen
        }
    })


@bus_bp.route("/api/driver/assignment/seen", methods=["POST"])
def driver_assignment_seen():
    if session.get("role") != "driver" or not session.get("driver_id"):
        return jsonify({"success": False}), 401
    user_service.mark_assignment_seen(session["driver_id"])
    return jsonify({"success": True})


@bus_bp.route("/api/driver/trip/start", methods=["POST"])
def start_trip():
    """Activates bus GPS broadcasting and sets status to EN_ROUTE."""
    bus_id, error = _driver_bus_or_error()
    if error:
        return error

    updated_bus = tracking_service.set_trip_status(bus_id=bus_id, is_active=True, trip_status="EN_ROUTE")
    if not updated_bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404

    return jsonify({"success": True, "message": "Trip started. GPS broadcasting enabled.", "bus": updated_bus})


@bus_bp.route("/api/driver/trip/stop", methods=["POST"])
def stop_trip():
    """Deactivates bus GPS broadcasting and sets status to IDLE."""
    bus_id, error = _driver_bus_or_error()
    if error:
        return error

    updated_bus = tracking_service.set_trip_status(bus_id=bus_id, is_active=False, trip_status="IDLE")
    if not updated_bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404

    return jsonify({"success": True, "message": "Trip stopped. GPS broadcasting disabled.", "bus": updated_bus})


@bus_bp.route("/api/driver/simulate/toggle", methods=["POST"])
def toggle_simulation():
    """
    Toggles simulated route drive mode.
    Useful for demonstration or testing when indoor/desktop.
    """
    data = request.get_json(silent=True) or {}
    if session.get("is_admin"):
        bus_id = data.get("bus_id")          # admin can test any bus
    else:
        bus_id, error = _driver_bus_or_error()
        if error:
            return error
    action = data.get("action", "start")  # "start", "stop" or "toggle"
    speed_multiplier = _optional_float(data.get("speed_multiplier")) or 1.5

    bus = tracking_service.get_bus_by_id(bus_id)
    if not bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404

    if action == "stop" or (action == "toggle" and bus.is_simulating):
        tracking_service.set_trip_status(bus_id=bus_id, is_active=False, trip_status="IDLE")
        return jsonify({"success": True, "simulating": False, "message": "Route simulation stopped."})
    else:
        success = tracking_service.start_bus_simulation(bus_id, speed_multiplier=speed_multiplier)
        return jsonify({
            "success": success,
            "simulating": success,
            "message": "Route simulation started. Bus is driving along official route waypoints."
        })


@bus_bp.route("/api/buses/stream", methods=["GET"])
def stream_buses():
    """
    Live bus feed (Server-Sent Events). Pushes the buses the moment any of them changes,
    at most ~4 times a second. ?audience=student|teacher limits it to those buses.
    """
    audience = request.args.get("audience")
    audience = audience if audience in ("student", "teacher") else None

    def event_generator():
        yield "retry: 2000\n\n"          # browser reconnects after 2 s if the line drops
        version = -1
        while True:
            new_version = tracking_service.wait_for_change(version, timeout=15.0)
            if new_version == version:
                yield ": keep-alive\n\n"    # nothing changed; keeps the connection open
                continue
            version = new_version
            buses = tracking_service.get_all_buses(audience)
            yield f"data: {json.dumps({'timestamp': time.time(), 'buses': buses})}\n\n"
            time.sleep(0.25)               # group very rapid changes together

    return Response(event_generator(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
