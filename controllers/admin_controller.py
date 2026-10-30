"""
Khulna University Bus Tracker (BusPlus)
Backend Administration Controller (Driver Setup & Student Setup with Sidebar)
"""

import json
import re
import urllib.error
import urllib.request
from flask import Blueprint, request, jsonify, render_template, session, redirect
from config import AppConfig
from services.user_service import UserService
from services.tracking_service import TrackingService, BUS_COLOR_PALETTE

admin_bp = Blueprint("admin_bp", __name__)
user_service = UserService()
tracking_service = TrackingService()

PIN_RE = re.compile(r"^\d{4,8}$")


@admin_bp.before_request
def require_admin():
    """Only the signed-in admin can use the backend. Drivers and students are sent away."""
    if request.endpoint == "admin_bp.admin_login_page":
        return None
    if session.get("is_admin"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": "Admin sign-in required."}), 401
    return redirect("/backend/login")


@admin_bp.route("/backend/login", methods=["GET"])
def admin_login_page():
    if session.get("is_admin"):
        return redirect("/backend")
    return render_template("admin_login.html")

@admin_bp.route("/backend", methods=["GET"])
@admin_bp.route("/admin", methods=["GET"])
def admin_portal():
    """Renders the backend administration portal with Driver Setup and Student Setup."""
    drivers = user_service.get_all_drivers(include_pin=True)
    students = user_service.get_all_students()
    routes = tracking_service.get_all_routes()
    buses = tracking_service.get_all_buses()

    return render_template(
        "admin_dashboard.html",
        drivers=drivers,
        students=students,
        routes=routes,
        buses=buses,
        final_destination=AppConfig.FINAL_DESTINATION,
        bus_color_palette=BUS_COLOR_PALETTE,
        admin_username=AppConfig.ADMIN_USERNAME
    )


def _sync_bus_driver(driver: dict) -> None:
    """Shows this driver on the bus they're assigned to (and nowhere else)."""
    tracking_service.clear_driver_from_buses(driver["driver_id"])
    if driver.get("assigned_bus_id"):
        tracking_service.set_bus_driver(driver["assigned_bus_id"], driver)


def _clean_driver_form(data: dict, creating: bool):
    """Checks the driver form. Returns (clean_data, error_message)."""
    clean = {}
    if "full_name" in data or creating:
        name = str(data.get("full_name") or "").strip()
        if not name:
            return None, "Driver name is required."
        clash = [d for d in user_service.get_all_drivers()
                 if d["full_name"].lower() == name.lower() and d["driver_id"] != data.get("_driver_id")]
        if clash:
            return None, f"There is already a driver called {name}. Use a different name so they can log in."
        clean["full_name"] = name[:60]
    if "phone" in data:
        clean["phone"] = str(data.get("phone") or "").strip()[:30]
    if "pin" in data or creating:
        pin = str(data.get("pin") or "").strip()
        if not PIN_RE.match(pin):
            return None, "PIN must be 4 to 8 digits."
        clean["pin"] = pin
    if "assigned_bus_id" in data or creating:
        bus_id = str(data.get("assigned_bus_id") or "").strip()
        bus = tracking_service.get_bus_by_id(bus_id)
        if not bus:
            return None, "Please choose the driver's bus."
        clean["assigned_bus_id"] = bus_id
        clean["assigned_route_id"] = bus.assigned_route_id   # a driver's route = their bus's route
    return clean, None


# -------------------------------------------------------------------------
# Driver Setup API Endpoints
# -------------------------------------------------------------------------
@admin_bp.route("/api/admin/drivers", methods=["GET"])
def list_drivers():
    """Returns all drivers for the backend admin table."""
    drivers = user_service.get_all_drivers(include_pin=True)
    return jsonify({"success": True, "count": len(drivers), "drivers": drivers})


@admin_bp.route("/api/admin/drivers", methods=["POST"])
def create_driver():
    """Creates a new driver record from the backend admin portal."""
    data = request.get_json(silent=True) or request.form.to_dict()
    clean, error = _clean_driver_form(data, creating=True)
    if error:
        return jsonify({"success": False, "message": error}), 400

    new_driver = user_service.create_driver(clean)
    user_service.mark_assignment_changed(new_driver["driver_id"])
    _sync_bus_driver(new_driver)
    return jsonify({
        "success": True,
        "message": f"Driver '{new_driver['full_name']}' created successfully.",
        "driver": new_driver
    })


@admin_bp.route("/api/admin/drivers/<driver_id>", methods=["PUT"])
def update_driver(driver_id: str):
    """Updates driver details (Name, Phone, Assigned Bus, PIN). The route follows the bus."""
    data = request.get_json(silent=True) or request.form.to_dict()
    if not user_service.get_driver_by_id(driver_id):
        return jsonify({"success": False, "message": f"Driver {driver_id} not found."}), 404
    clean, error = _clean_driver_form({**data, "_driver_id": driver_id}, creating=False)
    if error:
        return jsonify({"success": False, "message": error}), 400
    before = user_service.get_driver_by_id(driver_id)
    duty_changed = (clean.get("assigned_bus_id", before.assigned_bus_id) != before.assigned_bus_id or
                    clean.get("assigned_route_id", before.assigned_route_id) != before.assigned_route_id)
    updated = user_service.update_driver(driver_id, clean)
    if duty_changed:
        user_service.mark_assignment_changed(driver_id)
    if not updated:
        return jsonify({"success": False, "message": f"Driver {driver_id} not found."}), 404

    _sync_bus_driver(updated)
    return jsonify({
        "success": True,
        "message": f"Driver '{updated['full_name']}' updated successfully.",
        "driver": updated
    })


@admin_bp.route("/api/admin/drivers/<driver_id>/unlock", methods=["POST"])
def unlock_driver(driver_id: str):
    """Force unlocks an active driver session from the backend admin portal."""
    success = user_service.unlock_driver_session(driver_id)
    if not success:
        return jsonify({"success": False, "message": f"Driver {driver_id} not found."}), 404

    return jsonify({
        "success": True,
        "message": f"Driver account {driver_id} has been unlocked and session cleared."
    })


@admin_bp.route("/api/admin/drivers/<driver_id>", methods=["DELETE"])
def delete_driver(driver_id: str):
    """Deletes a driver from the backend admin portal."""
    success = user_service.delete_driver(driver_id)
    if not success:
        return jsonify({"success": False, "message": f"Driver {driver_id} not found."}), 404
    tracking_service.clear_driver_from_buses(driver_id)

    return jsonify({
        "success": True,
        "message": f"Driver {driver_id} deleted successfully."
    })


# -------------------------------------------------------------------------
# Bus Setup API Endpoints (every bus's route ends at Hadi Chattar)
# -------------------------------------------------------------------------
@admin_bp.route("/api/admin/buses", methods=["GET"])
def list_buses():
    """Returns all buses for the backend Bus Setup table."""
    buses = tracking_service.get_all_buses()
    return jsonify({
        "success": True,
        "count": len(buses),
        "final_destination": AppConfig.FINAL_DESTINATION,
        "buses": buses
    })


@admin_bp.route("/api/admin/buses", methods=["POST"])
def create_bus():
    """Adds a new bus (number, name, plate, route, colour, capacity)."""
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        bus = tracking_service.create_bus(data)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    return jsonify({"success": True, "message": f"{bus['bus_number']} added.", "bus": bus})


@admin_bp.route("/api/admin/buses/<bus_id>", methods=["PUT"])
def update_bus(bus_id: str):
    """Edits a bus's details."""
    data = request.get_json(silent=True) or request.form.to_dict()
    try:
        bus = tracking_service.update_bus(bus_id, data)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    if not bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404
    # Drivers of this bus follow its route
    for d in user_service.get_all_drivers():
        if d.get("assigned_bus_id") == bus_id and d.get("assigned_route_id") != bus["assigned_route_id"]:
            user_service.update_driver(d["driver_id"], {"assigned_route_id": bus["assigned_route_id"]})
            user_service.mark_assignment_changed(d["driver_id"])   # they'll see "Changed today"
    return jsonify({"success": True, "message": f"{bus['bus_number']} updated.", "bus": bus})


@admin_bp.route("/api/admin/buses/<bus_id>/simulate", methods=["POST"])
def simulate_bus(bus_id: str):
    """Admin test drive: moves the bus along its route to Hadi Chattar (or stops it)."""
    bus = tracking_service.get_bus_by_id(bus_id)
    if not bus:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404
    data = request.get_json(silent=True) or {}
    if data.get("action") == "stop" or (data.get("action") != "start" and bus.is_simulating):
        tracking_service.set_trip_status(bus_id, is_active=False, trip_status="IDLE")
        return jsonify({"success": True, "simulating": False, "message": f"{bus.bus_number} test drive stopped."})
    ok = tracking_service.start_bus_simulation(bus_id, speed_multiplier=2.0)
    return jsonify({"success": ok, "simulating": ok,
                    "message": f"{bus.bus_number} is test-driving its route to {AppConfig.FINAL_DESTINATION['stop_name']}."})


# -------------------------------------------------------------------------
# Route Setup API Endpoints (every route ends at Hadi Chattar)
# -------------------------------------------------------------------------
ROAD_ROUTER_URL = "https://router.project-osrm.org/route/v1/driving/"


@admin_bp.route("/api/admin/road-path", methods=["POST"])
def road_path():
    """
    Driving route along the roads through the given points (route editor).
    Body: {"points": [[lat, lng], ...]}  ->  {"path": [[lat, lng], ...], "distance_km": 8.0}
    Uses the public OSRM road router (OpenStreetMap data); needs an internet connection.
    """
    data = request.get_json(silent=True) or {}
    pts = data.get("points") or []
    try:
        pts = [(float(p[0]), float(p[1])) for p in pts]
    except (TypeError, ValueError, IndexError):
        return jsonify({"success": False, "message": "Points are not valid."}), 400
    if not (2 <= len(pts) <= 60) or not all(20 <= la <= 27 and 88 <= ln <= 93 for la, ln in pts):
        return jsonify({"success": False, "message": "Use 2 to 60 points inside Bangladesh."}), 400

    url = ROAD_ROUTER_URL + ";".join(f"{ln:.6f},{la:.6f}" for la, ln in pts) + "?overview=full&geometries=geojson"
    req = urllib.request.Request(url, headers={"User-Agent": "BusPlus-KU/1.0 (route editor)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        return jsonify({"success": False, "message": f"Road map not reachable ({err.__class__.__name__})."}), 502
    if result.get("code") != "Ok" or not result.get("routes"):
        return jsonify({"success": False, "message": "No road route found between these points."}), 502

    route = result["routes"][0]
    path = [[round(c[1], 6), round(c[0], 6)] for c in route["geometry"]["coordinates"]]
    return jsonify({"success": True, "path": path, "distance_km": round(route.get("distance", 0) / 1000, 2)})


@admin_bp.route("/api/admin/routes", methods=["GET"])
def list_routes():
    return jsonify({"success": True, "routes": tracking_service.get_all_routes(),
                    "final_destination": AppConfig.FINAL_DESTINATION})


@admin_bp.route("/api/admin/routes", methods=["POST"])
def create_route():
    data = request.get_json(silent=True) or {}
    try:
        route = tracking_service.create_route(data)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    return jsonify({"success": True, "message": f"Route '{route['route_name']}' added.", "route": route})


@admin_bp.route("/api/admin/routes/<route_id>", methods=["PUT"])
def update_route(route_id: str):
    data = request.get_json(silent=True) or {}
    try:
        route = tracking_service.update_route(route_id, data)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    if not route:
        return jsonify({"success": False, "message": f"Route {route_id} not found."}), 404
    return jsonify({"success": True, "message": f"Route '{route['route_name']}' updated.", "route": route})


@admin_bp.route("/api/admin/routes/<route_id>", methods=["DELETE"])
def delete_route(route_id: str):
    try:
        deleted = tracking_service.delete_route(route_id)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    if not deleted:
        return jsonify({"success": False, "message": f"Route {route_id} not found."}), 404
    return jsonify({"success": True, "message": "Route deleted."})


@admin_bp.route("/api/admin/buses/<bus_id>", methods=["DELETE"])
def delete_bus(bus_id: str):
    """Deletes a bus. Not allowed while it's on a live trip or still assigned to a driver."""
    assigned = [d for d in user_service.get_all_drivers() if d.get("assigned_bus_id") == bus_id]
    if assigned:
        names = ", ".join(d["full_name"] for d in assigned)
        return jsonify({
            "success": False,
            "message": f"{names} is assigned to this bus. Move them to another bus in Driver Setup first."
        }), 400
    try:
        deleted = tracking_service.delete_bus(bus_id)
    except ValueError as err:
        return jsonify({"success": False, "message": str(err)}), 400
    if not deleted:
        return jsonify({"success": False, "message": f"Bus {bus_id} not found."}), 404
    return jsonify({"success": True, "message": f"Bus {bus_id} deleted."})


# -------------------------------------------------------------------------
# Student Setup API Endpoints
# -------------------------------------------------------------------------
@admin_bp.route("/api/admin/students", methods=["GET"])
def list_students():
    """Returns all students for the backend admin portal."""
    students = user_service.get_all_students()
    return jsonify({"success": True, "count": len(students), "students": students})


@admin_bp.route("/api/admin/students/<student_id>", methods=["PUT"])
def update_student(student_id: str):
    """Updates student setup details from the backend admin portal."""
    data = request.get_json(silent=True) or request.form.to_dict()
    updated = user_service.update_student(student_id, data)
    return jsonify({
        "success": True,
        "message": f"Student {student_id} updated successfully.",
        "student": updated
    })
