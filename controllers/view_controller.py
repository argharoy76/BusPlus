"""
The front-end pages (HTML).

  /                      start page: Driver, Student or Teacher
  /driver/login          driver sign-in
  /driver/dashboard      driver's full-screen map (signed-in driver only)
  /student/login         student sign-in
  /student/dashboard     student live map (student buses only)
  /teacher/login         teacher sign-in
  /teacher/dashboard     teacher live map (teacher buses only)
"""

from flask import Blueprint, redirect, render_template, session, url_for

from config import Config
from extensions import talisman
from services import tracking, users

view_bp = Blueprint("views", __name__)

# Wording for the shared student/teacher pages.
PORTALS = {
    "student": {"label": "Student", "id_label": "Student ID"},
    "teacher": {"label": "Teacher", "id_label": "Teacher ID"},
}


@view_bp.get("/")
def landing():
    """Start page with the Driver, Student and Teacher buttons."""
    return render_template("landing.html")


@view_bp.get("/health")
@talisman(force_https=False)          # local health checks use plain http
def health():
    """Used by the deploy script and uptime monitors to check the app is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _signed_in_driver():
    """The driver signed in on this phone, or None (also None if another phone took over)."""
    if session.get("role") != "driver":
        return None
    driver = users.get_driver(session.get("driver_id"))
    if driver is None or driver.session_token != session.get("session_token"):
        return None
    return driver


@view_bp.get("/driver/login")
def driver_login():
    """Driver sign-in page (a driver who is still signed in goes straight to the map)."""
    if _signed_in_driver():
        return redirect(url_for("views.driver_dashboard"))
    return render_template("driver_login.html", routes=tracking.all_routes())


@view_bp.get("/driver/dashboard")
def driver_dashboard():
    """The driver's full-screen map. Sends anyone else back to the sign-in page."""
    driver = _signed_in_driver()
    if driver is None:
        session.pop("role", None)
        session.pop("driver_id", None)
        return redirect(url_for("views.driver_login"))
    bus = tracking.get_bus(driver.assigned_bus_id)
    return render_template(
        "driver_dashboard.html",
        driver={"driver_id": driver.driver_id, "full_name": driver.full_name},
        bus=bus.to_dict() if bus else {},
        routes=tracking.all_routes(),
        map_center=Config.UNIVERSITY_LOCATION,
    )


# ---------------------------------------------------------------------------
# Students and teachers
# ---------------------------------------------------------------------------
def _rider_login_page(audience: str):
    return render_template("student_login.html", portal=audience, portal_info=PORTALS[audience])


def _rider_dashboard(audience: str):
    """Live map for a signed-in student or teacher; each only sees the buses meant for them."""
    if session.get("role") != audience or not session.get("rider_id"):
        return redirect(url_for(f"views.{audience}_login"))
    return render_template(
        "student_dashboard.html",
        audience=audience,
        rider_id=session["rider_id"],
        rider_name=session.get("rider_name", PORTALS[audience]["label"]),
        routes=tracking.all_routes(),
        buses=tracking.all_buses(audience),
        alert_lead_minutes=Config.DEFAULT_ALERT_MINUTES,
        map_center=Config.UNIVERSITY_LOCATION,
    )


@view_bp.get("/student/login")
def student_login():
    """Student sign-in page."""
    return _rider_login_page("student")


@view_bp.get("/teacher/login")
def teacher_login():
    """Teacher sign-in page."""
    return _rider_login_page("teacher")


@view_bp.get("/student/dashboard")
def student_dashboard():
    """Live map with the student buses."""
    return _rider_dashboard("student")


@view_bp.get("/teacher/dashboard")
def teacher_dashboard():
    """Live map with the teacher buses."""
    return _rider_dashboard("teacher")
