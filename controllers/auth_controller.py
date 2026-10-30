"""
Khulna University Bus Tracker (BusPlus)
Authentication Controller (Driver and Student sessions with concurrency control)
"""

import hmac
import uuid
from flask import Blueprint, request, jsonify, session, redirect, url_for
from config import AppConfig
from services.user_service import UserService
from services.tracking_service import TrackingService

auth_bp = Blueprint("auth_bp", __name__)
user_service = UserService()
tracking_service = TrackingService()


# -------------------------------------------------------------------------
# Backend admin sign-in (separate from driver/student sign-in)
# -------------------------------------------------------------------------
@auth_bp.route("/api/auth/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or request.form.to_dict()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    ok_user = hmac.compare_digest(username, AppConfig.ADMIN_USERNAME)
    ok_pass = hmac.compare_digest(password, AppConfig.ADMIN_PASSWORD)
    if not (ok_user and ok_pass):
        return jsonify({"success": False, "message": "Wrong username or password."}), 401
    session["is_admin"] = True
    return jsonify({"success": True, "redirect_url": "/backend"})


@auth_bp.route("/backend/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/backend/login")

@auth_bp.route("/api/drivers/search", methods=["GET"])
def search_drivers():
    """
    Returns list of matching drivers as the user types their name.
    Query parameter: q (e.g. /api/drivers/search?q=raf)
    """
    query = request.args.get("q", "")
    matches = user_service.search_drivers(query)
    for m in matches:
        route = tracking_service.get_route_by_id(m.get("assigned_route_id") or "")
        m["route_name"] = route.route_name if route else None
    return jsonify({
        "success": True,
        "count": len(matches),
        "drivers": matches
    })


@auth_bp.route("/api/auth/driver/login", methods=["POST"])
def driver_login():
    """
    Authenticates a driver using:
      1. Driver name (or driver_id)
      2. Selected route
      3. PIN
    Enforces strict single-session concurrency:
    No other driver or device can log in to the same account while it is active!
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    # Prefer the exact driver_id chosen from the name suggestions
    name_or_id = (data.get("driver_id") or data.get("driver_name") or data.get("username") or "").strip()
    route_id = (data.get("route_id") or "").strip()
    pin = (data.get("pin") or "").strip()

    if not name_or_id:
        return jsonify({"success": False, "message": "Please enter or select your driver name."}), 400

    # Ensure this browser session has a unique session token
    if "session_token" not in session:
        session["session_token"] = str(uuid.uuid4())
    session_token = session["session_token"]

    # The driver's route is the route of the bus the admin assigned to them
    bus_route_id = None
    for d in user_service.get_all_drivers():
        if name_or_id.lower() in (d["driver_id"].lower(), d["full_name"].lower(), d["username"].lower()):
            bus = tracking_service.get_bus_by_id(d.get("assigned_bus_id") or "")
            bus_route_id = bus.assigned_route_id if bus else None
            break

    success, message, driver_dict = user_service.authenticate_driver(
        name_or_id=name_or_id,
        route_id=route_id,
        pin=pin,
        session_token=session_token,
        bus_route_id=bus_route_id,
        lock_timeout_minutes=AppConfig.DRIVER_SESSION_TIMEOUT_MINUTES
    )

    if not success:
        status_code = 409 if "already logged in" in message else 401
        return jsonify({"success": False, "message": message}), status_code

    # Establish session
    session["role"] = "driver"
    session["driver_id"] = driver_dict["driver_id"]
    session["driver_name"] = driver_dict["full_name"]
    session["bus_id"] = driver_dict["assigned_bus_id"]
    session["route_id"] = driver_dict["assigned_route_id"]

    return jsonify({
        "success": True,
        "message": f"Welcome, {driver_dict['full_name']}",
        "driver": driver_dict,
        "bus_id": session["bus_id"],
        "redirect_url": "/driver/dashboard"
    })


@auth_bp.route("/api/auth/student/login", methods=["POST"])
def student_login():
    """Registers or logs in a student with their preferred boarding stop."""
    data = request.get_json(silent=True) or request.form.to_dict()
    student_id = (data.get("student_id") or "KU-STUDENT-GUEST").strip()
    full_name = (data.get("full_name") or "KU Student").strip()
    department = (data.get("department") or "Computer Science & Engineering").strip()
    preferred_stop = (data.get("preferred_stop") or "Malabotha More").strip()
    preferred_route_id = data.get("preferred_route_id") or "KU-R01"
    try:
        alert_lead_minutes = max(1, min(120, int(data.get("alert_lead_minutes") or 5)))
    except (TypeError, ValueError):
        alert_lead_minutes = 5

    # Save/update in student store
    student_dict = user_service.update_student(student_id, {
        "full_name": full_name,
        "department": department,
        "preferred_route_id": preferred_route_id,
        "preferred_stop_name": preferred_stop,
        "alert_lead_minutes": alert_lead_minutes
    })

    session.permanent = True
    session["role"] = "student"
    session["student_id"] = student_id
    session["student_name"] = full_name
    session["preferred_stop"] = preferred_stop
    session["preferred_route_id"] = preferred_route_id
    session["alert_lead_minutes"] = alert_lead_minutes

    return jsonify({
        "success": True,
        "message": f"Welcome, {full_name}",
        "student": student_dict,
        "redirect_url": "/student/dashboard"
    })


@auth_bp.route("/api/auth/teacher/login", methods=["POST"])
def teacher_login():
    """Teacher signs in with name + teacher ID (sees teacher buses only)."""
    data = request.get_json(silent=True) or request.form.to_dict()
    teacher_id = str(data.get("teacher_id") or data.get("student_id") or "").strip()[:40]
    full_name = str(data.get("full_name") or "").strip()[:60]
    if not teacher_id or not full_name:
        return jsonify({"success": False, "message": "Please enter your name and teacher ID."}), 400
    session.permanent = True
    for key in ("student_id", "student_name"):
        session.pop(key, None)
    session["role"] = "teacher"
    session["teacher_id"] = teacher_id
    session["teacher_name"] = full_name
    return jsonify({"success": True, "message": f"Welcome, {full_name}", "redirect_url": "/teacher/dashboard"})


@auth_bp.route("/api/auth/logout", methods=["GET", "POST"])
def logout():
    """Clears active session and releases driver session lock."""
    driver_id = session.get("driver_id")
    session_token = session.get("session_token")
    if driver_id:
        # Turn the bus's GPS trip off, then free the account for the next login
        bus_id = session.get("bus_id")
        if bus_id:
            tracking_service.set_trip_status(bus_id=bus_id, is_active=False, trip_status="IDLE")
        user_service.logout_driver(driver_id, session_token)

    was_admin = session.get("is_admin")
    session.clear()
    if was_admin:
        session["is_admin"] = True  # signing out of the app doesn't sign the admin out of /backend
    if request.is_json:
        return jsonify({"success": True, "message": "Logged out successfully", "redirect_url": "/"})
    return redirect(url_for("view_bp.landing_page"))


@auth_bp.route("/api/auth/session", methods=["GET"])
def get_current_session():
    """Returns information on the current user session."""
    return jsonify({
        "role": session.get("role"),
        "driver_id": session.get("driver_id"),
        "driver_name": session.get("driver_name"),
        "bus_id": session.get("bus_id"),
        "route_id": session.get("route_id"),
        "student_id": session.get("student_id"),
        "student_name": session.get("student_name"),
        "preferred_stop": session.get("preferred_stop"),
        "preferred_route_id": session.get("preferred_route_id"),
        "alert_lead_minutes": session.get("alert_lead_minutes", 5)
    })
