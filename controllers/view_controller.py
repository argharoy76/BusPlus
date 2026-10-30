"""
Khulna University Bus Tracker (BusPlus)
View Controller (Page Renderers)
"""

from flask import Blueprint, render_template, session, redirect, url_for
from config import AppConfig
from services.tracking_service import TrackingService
from services.user_service import UserService

view_bp = Blueprint("view_bp", __name__)
tracking_service = TrackingService()
user_service = UserService()

@view_bp.route("/", methods=["GET"])
def landing_page():
    """Renders the launching page."""
    routes = tracking_service.get_all_routes()
    buses = tracking_service.get_all_buses()
    student_logged_in = (session.get("role") == "student" and bool(session.get("student_id")))
    return render_template(
        "landing.html",
        routes=routes,
        buses=buses,
        student_logged_in=student_logged_in,
        university_name=AppConfig.UNIVERSITY_NAME,
        university_short_name=AppConfig.UNIVERSITY_SHORT_NAME,
        google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY
    )


@view_bp.route("/driver/login", methods=["GET"])
def driver_login_page():
    """Renders driver authentication page."""
    if session.get("role") == "driver" and session.get("driver_id"):
        driver = user_service.get_driver_by_id(session["driver_id"])
        if driver and driver.is_logged_in and driver.current_session_token == session.get("session_token"):
            return redirect(url_for("view_bp.driver_dashboard_page"))
    buses = tracking_service.get_all_buses()
    return render_template(
        "driver_login.html",
        buses=buses,
        routes=tracking_service.get_all_routes(),
        google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY
    )


@view_bp.route("/driver/dashboard", methods=["GET"])
def driver_dashboard_page():
    """Driver's full-screen map. Only a signed-in driver can open it."""
    if session.get("role") != "driver" or not session.get("driver_id"):
        return redirect(url_for("view_bp.driver_login_page"))

    driver = user_service.get_driver_by_id(session["driver_id"])
    if not driver or not driver.is_logged_in or driver.current_session_token != session.get("session_token"):
        # Account was unlocked by the admin or taken over by another device
        session.pop("role", None)
        session.pop("driver_id", None)
        return redirect(url_for("view_bp.driver_login_page"))

    bus = tracking_service.get_bus_by_id(driver.assigned_bus_id)
    return render_template(
        "driver_dashboard.html",
        driver=driver.to_dict(),
        bus=bus.to_dict() if bus else {},
        routes=tracking_service.get_all_routes(),
        google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY,
        university_location=AppConfig.UNIVERSITY_LOCATION
    )


PORTALS = {
    "student": {"label": "Student", "id_label": "Student ID", "accent": "emerald"},
    "teacher": {"label": "Teacher", "id_label": "Teacher ID", "accent": "violet"},
}


@view_bp.route("/student/login", methods=["GET"])
def student_login_page():
    """Student sign-in: name + student ID."""
    return render_template("student_login.html", portal="student", portal_info=PORTALS["student"],
                           google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY)


@view_bp.route("/teacher/login", methods=["GET"])
def teacher_login_page():
    """Teacher sign-in: name + teacher ID."""
    return render_template("student_login.html", portal="teacher", portal_info=PORTALS["teacher"],
                           google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY)


def _rider_dashboard(audience: str, rider_id: str, rider_name: str):
    """Live map for students or teachers. Each only sees the buses meant for them."""
    return render_template(
        "student_dashboard.html",
        audience=audience,
        portal_info=PORTALS[audience],
        routes=tracking_service.get_all_routes(),
        buses=tracking_service.get_all_buses(audience),
        student_name=rider_name,
        student_id=rider_id,
        preferred_stop=session.get("preferred_stop", "Malabotha More"),
        preferred_route_id=session.get("preferred_route_id", "KU-R01"),
        alert_lead_minutes=session.get("alert_lead_minutes", 5),
        google_maps_api_key=AppConfig.GOOGLE_MAPS_API_KEY,
        university_location=AppConfig.UNIVERSITY_LOCATION
    )


@view_bp.route("/student/dashboard", methods=["GET"])
def student_dashboard_page():
    """Student live map: student buses only."""
    return _rider_dashboard("student", session.get("student_id", "KU-2026-Guest"), session.get("student_name", "Student"))


@view_bp.route("/teacher/dashboard", methods=["GET"])
def teacher_dashboard_page():
    """Teacher live map: teacher buses only. Teachers sign in first."""
    if session.get("role") != "teacher" or not session.get("teacher_id"):
        return redirect(url_for("view_bp.teacher_login_page"))
    return _rider_dashboard("teacher", session["teacher_id"], session.get("teacher_name", "Teacher"))
