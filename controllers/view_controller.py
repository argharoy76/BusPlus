"""
The front-end pages (HTML).

  /                      start page: one button per rider type
  /<type>/login          rider sign-in, e.g. /student/login, /teacher/login
  /<type>/dashboard      rider live map with only that type's buses, e.g. /student/dashboard
                         (rider types are listed in content/user_types.py)
"""

from flask import Blueprint, Response, abort, redirect, render_template, session, url_for
from markupsafe import escape

from config import Config
from content import branding, colors
from extensions import talisman
from models.rider_types import rider_info
from services import tracking

view_bp = Blueprint("views", __name__)

@view_bp.get("/")
def landing():
    """Start page: one button per rider type (content/user_types.py)."""
    return render_template("landing.html")


@view_bp.get("/favicon.svg")
def favicon():
    """Browser-tab icon: the logo emoji on a rounded square in the brand colour (content/branding.py, colors.py)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="16" fill="{escape(colors.THEME["brand"])}"/>'
        f'<text x="32" y="44" font-size="36" text-anchor="middle">{escape(branding.LOGO_EMOJI)}</text></svg>'
    )
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "public, max-age=3600"})


@view_bp.get("/health")
@talisman(force_https=False)          # local health checks use plain http
def health():
    """Used by the deploy script and uptime monitors to check the app is running."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Riders: students, teachers and any other type from content/user_types.py
# (templates student_login.html / student_dashboard.html serve every rider type)
# ---------------------------------------------------------------------------
@view_bp.get("/<rider_type>/login")
def rider_login(rider_type: str):
    """Sign-in page of a rider type, e.g. /student/login or /teacher/login."""
    info = rider_info(rider_type)
    if info is None:
        abort(404)
    return render_template("student_login.html", portal=rider_type, portal_info=info)


@view_bp.get("/<rider_type>/dashboard")
def rider_dashboard(rider_type: str):
    """Live map of a rider type, e.g. /student/dashboard. Shows only the buses meant for that type."""
    info = rider_info(rider_type)
    if info is None:
        abort(404)
    if session.get("role") != rider_type or not session.get("rider_id"):
        return redirect(url_for("views.rider_login", rider_type=rider_type))
    return render_template(
        "student_dashboard.html",
        audience=rider_type,
        portal_info=info,
        rider_id=session["rider_id"],
        rider_name=session.get("rider_name", info["label"]),
        routes=tracking.all_routes(),
        buses=tracking.all_buses(rider_type),
        alert_lead_minutes=Config.DEFAULT_ALERT_MINUTES,
        map_center=Config.UNIVERSITY_LOCATION,
    )
