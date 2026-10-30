"""
Sign-in and sign-out for everyone.

  * Admin:    username + password, only for the backend (/backend).
  * Driver:   name + their bus's route + PIN set by the admin; front end only.
  * Student / teacher: name + ID (no password), to open their live map.

Login endpoints are rate-limited per IP address (Flask-Limiter) to stop
password/PIN guessing.
"""

import hmac

from flask import Blueprint, current_app, redirect, request, session, url_for

from config import Config
from controllers.helpers import fail, json_body, ok
from extensions import limiter
from services import store, tracking, users
from services.user_service import LoginError, new_session_token

auth_bp = Blueprint("auth", __name__)


def _start_fresh_session(keep_admin: bool = True) -> None:
    """
    Forget any previous sign-in in this browser. Keeps the page's CSRF token (so
    the open page keeps working) and, unless told otherwise, the backend admin sign-in.
    """
    kept = {key: session[key] for key in ("csrf_token", "is_admin") if key in session}
    if not keep_admin:
        kept.pop("is_admin", None)
    session.clear()
    session.update(kept)


# ---------------------------------------------------------------------------
# Admin (backend only)
# ---------------------------------------------------------------------------
@auth_bp.post("/api/auth/admin/login")
@limiter.limit("5 per minute; 30 per hour")
def admin_login():
    """Sign the admin in. Compares in constant time so the password can't be guessed by timing."""
    data = json_body()
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    expected_password = current_app.config["ADMIN_PASSWORD"] or ""
    good_user = hmac.compare_digest(username.encode(), current_app.config["ADMIN_USERNAME"].encode())
    good_pass = hmac.compare_digest(password.encode(), expected_password.encode())
    if not (good_user and good_pass and expected_password):
        return fail("Wrong username or password.", 401)
    _start_fresh_session(keep_admin=False)
    session["is_admin"] = True
    return ok(redirect_url=url_for("admin.portal"))


@auth_bp.route("/backend/logout", methods=["GET", "POST"])
def admin_logout():
    """Sign the admin out of the backend."""
    session.pop("is_admin", None)
    return redirect(url_for("admin.login_page"))


# ---------------------------------------------------------------------------
# Drivers (front end)
# ---------------------------------------------------------------------------
@auth_bp.get("/api/drivers/search")
@limiter.limit("60 per minute")
def search_drivers():
    """Name suggestions while a driver types on the login page: /api/drivers/search?q=raf"""
    matches = users.search_drivers(request.args.get("q", ""))
    for match in matches:
        bus = tracking.get_bus(match.pop("assigned_bus_id"))
        route = tracking.get_route(bus.assigned_route_id) if bus else None
        match["route_id"] = route.route_id if route else None
        match["route_name"] = route.route_name if route else None
    return ok(count=len(matches), drivers=matches)


@auth_bp.post("/api/auth/driver/login")
@limiter.limit("10 per minute; 60 per hour")
def driver_login():
    """
    Sign a driver in. Body: {"driver_id" or "driver_name", "route_id", "pin"}.
    The account is then locked to this phone until the driver logs out.
    """
    data = json_body()
    name_or_id = str(data.get("driver_id") or data.get("driver_name") or "").strip()
    if not name_or_id:
        return fail("Please enter or select your driver name.")

    driver = users.find_driver(name_or_id)
    bus = tracking.get_bus(driver.assigned_bus_id) if driver else None
    token = session.get("session_token") or new_session_token()
    try:
        driver = users.sign_in(
            name_or_id=name_or_id,
            route_id=str(data.get("route_id") or "").strip(),
            pin=str(data.get("pin") or "").strip(),
            session_token=token,
            bus_route_id=bus.assigned_route_id if bus else None,
            lock_minutes=Config.DRIVER_SESSION_TIMEOUT_MINUTES,
        )
    except LoginError as err:
        return fail(str(err), err.status)

    _start_fresh_session()
    session.update(role="driver", driver_id=driver.driver_id, session_token=token)
    return ok(message=f"Welcome, {driver.full_name}", redirect_url=url_for("views.driver_dashboard"))


# ---------------------------------------------------------------------------
# Students and teachers (front end)
# ---------------------------------------------------------------------------
def _rider_login(role: str):
    """Shared sign-in for students and teachers: just a name and an ID."""
    data = json_body()
    rider_id = str(data.get(f"{role}_id") or "").strip()[:40]
    full_name = str(data.get("full_name") or "").strip()[:60]
    if not rider_id or not full_name:
        return fail(f"Please enter your name and {role} ID.")
    store.record_rider(role, rider_id, full_name)
    _start_fresh_session()
    session.permanent = True
    session.update(role=role, rider_id=rider_id, rider_name=full_name)
    return ok(message=f"Welcome, {full_name}", redirect_url=url_for(f"views.{role}_dashboard"))


@auth_bp.post("/api/auth/student/login")
@limiter.limit("20 per minute")
def student_login():
    """Student sign-in. Body: {full_name, student_id}."""
    return _rider_login("student")


@auth_bp.post("/api/auth/teacher/login")
@limiter.limit("20 per minute")
def teacher_login():
    """Teacher sign-in. Body: {full_name, teacher_id}."""
    return _rider_login("teacher")


# ---------------------------------------------------------------------------
# Sign out (everyone except the backend admin, see /backend/logout)
# ---------------------------------------------------------------------------
@auth_bp.post("/api/auth/logout")
def logout():
    """Sign out. A driver also goes offline and frees the account for their next login."""
    driver_id = session.get("driver_id")
    if driver_id:
        driver = users.get_driver(driver_id)
        token = session.get("session_token")
        if driver and driver.session_token == token and driver.assigned_bus_id:
            tracking.stop_trip(driver.assigned_bus_id)
        users.sign_out(driver_id, token)
    _start_fresh_session()
    return ok(message="Logged out.", redirect_url=url_for("views.landing"))
