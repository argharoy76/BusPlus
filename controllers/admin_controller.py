"""
The backend admin panel (/backend). Only the signed-in admin can use anything here.

Pages:  /backend/login, /backend
API:    /api/admin/drivers   add / edit / unlock / delete drivers
        /api/admin/buses     add / edit / delete buses, set today's route, test drive
        /api/admin/routes    add / edit / delete routes
        /api/admin/schedules each route's bus schedule
        /api/admin/road-path snap a route to the roads (route editor)
"""

import re

from flask import Blueprint, redirect, render_template, request, session, url_for

from config import Config
from content import rules
from content.site_text import DAY_NAMES
from controllers.helpers import fail, json_body, ok
from services import schedule_service, store, tracking, users
from services.road_router import RoadRouterError, road_path
from services.tracking_service import BUS_COLOR_PALETTE

admin_bp = Blueprint("admin", __name__)

PIN_RE = re.compile(rf"^\d{{{rules.PIN_MIN_DIGITS},{rules.PIN_MAX_DIGITS}}}$")   # PIN length: content/rules.py
TEST_DRIVE_SPEED = rules.TEST_DRIVE_SPEED


@admin_bp.before_request
def require_admin():
    """Everything in this blueprint needs the admin. API calls get 401, pages go to the login page."""
    if request.endpoint == "admin.login_page" or session.get("is_admin"):
        return None
    if request.path.startswith("/api/"):
        return fail("Admin sign-in required.", 401)
    return redirect(url_for("admin.login_page"))


@admin_bp.get("/backend/login")
def login_page():
    """The admin sign-in page (already signed-in admins go straight to the panel)."""
    if session.get("is_admin"):
        return redirect(url_for("admin.portal"))
    return render_template("admin_login.html")


@admin_bp.get("/backend")
def portal():
    """The admin panel with the Drivers, Routes, Buses and Users tabs."""
    return render_template(
        "admin_dashboard.html",
        drivers=[d.to_dict() for d in users.all_drivers()],
        riders=store.list_riders(),
        routes=tracking.all_routes(),
        buses=tracking.all_buses(),
        final_destination=Config.FINAL_DESTINATION,
        bus_color_palette=BUS_COLOR_PALETTE,
        admin_username=Config.ADMIN_USERNAME,
        schedules=schedule_service.all_timetables(),
        day_names=DAY_NAMES,
        today=schedule_service.today_key(),
        default_bus_seats=rules.DEFAULT_BUS_SEATS,
        max_bus_seats=rules.MAX_BUS_SEATS,
    )


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
def _clean_driver_form(data: dict, creating: bool, driver_id: str | None = None) -> tuple[dict, str | None]:
    """
    Check the driver form. Returns (clean_fields, error_message).
    When editing, a missing or empty PIN keeps the current PIN.
    """
    clean: dict = {}
    if creating or "full_name" in data:
        name = str(data.get("full_name") or "").strip()[:60]
        if not name:
            return {}, "Driver name is required."
        if users.name_taken(name, except_driver_id=driver_id):
            return {}, f"There is already a driver called {name}. Use a different name so they can log in."
        clean["full_name"] = name
    if "phone" in data:
        clean["phone"] = str(data.get("phone") or "").strip()[:30]
    pin = str(data.get("pin") or "").strip()
    if creating or pin:
        if not PIN_RE.match(pin):
            return {}, f"PIN must be {rules.PIN_MIN_DIGITS} to {rules.PIN_MAX_DIGITS} digits."
        clean["pin"] = pin
    if creating or "assigned_bus_id" in data:
        bus_id = str(data.get("assigned_bus_id") or "").strip()
        if not tracking.get_bus(bus_id):
            return {}, "Please choose the driver's bus."
        clean["bus_id"] = bus_id
    return clean, None


@admin_bp.post("/api/admin/drivers")
def create_driver():
    """Add a driver. Body: {full_name, pin, assigned_bus_id, phone?}."""
    clean, error = _clean_driver_form(json_body(), creating=True)
    if error:
        return fail(error)
    driver = users.create_driver(**clean)
    tracking.show_driver_on_bus(driver.driver_id, driver.full_name, driver.assigned_bus_id)
    return ok(message=f"Driver '{driver.full_name}' added.", driver=driver.to_dict())


@admin_bp.put("/api/admin/drivers/<driver_id>")
def update_driver(driver_id: str):
    """Edit a driver; also moves their name onto their (new) bus."""
    if users.get_driver(driver_id) is None:
        return fail(f"Driver {driver_id} not found.", 404)
    clean, error = _clean_driver_form(json_body(), creating=False, driver_id=driver_id)
    if error:
        return fail(error)
    driver = users.update_driver(driver_id, **clean)
    tracking.show_driver_on_bus(driver.driver_id, driver.full_name, driver.assigned_bus_id)
    return ok(message=f"Driver '{driver.full_name}' updated.", driver=driver.to_dict())


@admin_bp.post("/api/admin/drivers/<driver_id>/unlock")
def unlock_driver(driver_id: str):
    """Free a driver account that is stuck on another phone."""
    if not users.unlock(driver_id):
        return fail(f"Driver {driver_id} not found.", 404)
    return ok(message=f"Driver {driver_id} can now sign in on any phone.")


@admin_bp.delete("/api/admin/drivers/<driver_id>")
def delete_driver(driver_id: str):
    """Remove a driver and take their name off their bus."""
    if not users.delete_driver(driver_id):
        return fail(f"Driver {driver_id} not found.", 404)
    tracking.show_driver_on_bus(driver_id, None, None)
    return ok(message=f"Driver {driver_id} deleted.")


# ---------------------------------------------------------------------------
# Buses
# ---------------------------------------------------------------------------
@admin_bp.post("/api/admin/buses")
def create_bus():
    """Add a bus. Body: {bus_number, bus_name?, license_plate?, assigned_route_id, capacity?, color_hex?, audience?}."""
    try:
        bus = tracking.create_bus(json_body())
    except ValueError as err:
        return fail(str(err))
    return ok(message=f"{bus['bus_number']} added.", bus=bus)


@admin_bp.put("/api/admin/buses/<bus_id>")
def update_bus(bus_id: str):
    """Edit a bus, or send it on another route today. Its drivers then see "Changed today"."""
    before = tracking.get_bus(bus_id)
    old_route = before.assigned_route_id if before else None
    try:
        bus = tracking.update_bus(bus_id, json_body())
    except ValueError as err:
        return fail(str(err))
    if bus is None:
        return fail(f"Bus {bus_id} not found.", 404)
    if bus["assigned_route_id"] != old_route:
        for driver in users.drivers_of_bus(bus_id):
            users.mark_duty_changed(driver.driver_id)
    return ok(message=f"{bus['bus_number']} updated.", bus=bus)


@admin_bp.delete("/api/admin/buses/<bus_id>")
def delete_bus(bus_id: str):
    """Delete a bus. Not allowed while it is on a live trip or still has a driver."""
    drivers = users.drivers_of_bus(bus_id)
    if drivers:
        names = ", ".join(d.full_name for d in drivers)
        return fail(f"{names} is assigned to this bus. Move them to another bus in Drivers first.")
    try:
        deleted = tracking.delete_bus(bus_id)
    except ValueError as err:
        return fail(str(err))
    if not deleted:
        return fail(f"Bus {bus_id} not found.", 404)
    return ok(message=f"Bus {bus_id} deleted.")


@admin_bp.post("/api/admin/buses/<bus_id>/simulate")
def simulate_bus(bus_id: str):
    """Test drive: move the bus along its route to Hadi Chattar without a phone. {"action": "stop"} ends it."""
    bus = tracking.get_bus(bus_id)
    if bus is None:
        return fail(f"Bus {bus_id} not found.", 404)
    action = json_body().get("action")            # "start", "stop", or nothing = toggle
    if action == "stop" or (action != "start" and bus.is_simulating):
        tracking.stop_trip(bus_id)
        return ok(simulating=False, message=f"{bus.bus_number} test drive stopped.")
    if not tracking.start_simulation(bus_id, speed_multiplier=TEST_DRIVE_SPEED):
        return fail(f"{bus.bus_number}'s route has no line to drive along.")
    return ok(simulating=True, message=f"{bus.bus_number} is test-driving its route to "
                                       f"{Config.FINAL_DESTINATION['stop_name']}.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@admin_bp.post("/api/admin/road-path")
def snap_to_roads():
    """Road line through the clicked points. Body: {"points": [[lat, lng], ...]} (2 to 60 points)."""
    try:
        points = [(float(p[0]), float(p[1])) for p in json_body().get("points") or []]
    except (TypeError, ValueError, IndexError):
        return fail("Points are not valid.")
    if not 2 <= len(points) <= 60 or not all(20 <= lat <= 27 and 88 <= lng <= 93 for lat, lng in points):
        return fail("Use 2 to 60 points inside Bangladesh.")
    try:
        path, distance = road_path(points)
    except RoadRouterError as err:
        return fail(str(err), 502)
    return ok(path=path, distance_km=distance)


@admin_bp.post("/api/admin/routes")
def create_route():
    """Add a route from the route editor (name, colour, clicked points and road line)."""
    try:
        route = tracking.create_route(json_body())
    except ValueError as err:
        return fail(str(err))
    return ok(message=f"Route '{route['route_name']}' added.", route=route)


@admin_bp.put("/api/admin/routes/<route_id>")
def update_route(route_id: str):
    """Edit a route's name, colour and/or line."""
    try:
        route = tracking.update_route(route_id, json_body())
    except ValueError as err:
        return fail(str(err))
    if route is None:
        return fail(f"Route {route_id} not found.", 404)
    return ok(message=f"Route '{route['route_name']}' updated.", route=route)


@admin_bp.put("/api/admin/schedules/<route_id>")
def save_schedule(route_id: str):
    """Save a route's weekly timetable: per day, morning (reach campus) and afternoon (leave campus) buses."""
    try:
        schedule = schedule_service.save_timetable(route_id, json_body())
    except LookupError as err:
        return fail(str(err), 404)
    except ValueError as err:
        return fail(str(err))
    return ok(message=f"Schedule of '{schedule['route_name']}' saved.", schedule=schedule)


@admin_bp.delete("/api/admin/routes/<route_id>")
def delete_route(route_id: str):
    """Remove a route. Refused while any bus still uses it."""
    try:
        deleted = tracking.delete_route(route_id)
    except ValueError as err:
        return fail(str(err))
    if not deleted:
        return fail(f"Route {route_id} not found.", 404)
    schedule_service.delete_timetable(route_id)
    return ok(message="Route deleted.")
