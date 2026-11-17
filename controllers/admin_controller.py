"""
The backend admin panel (/backend). Only the signed-in admin can use anything here.

Pages:  /backend/login, /backend
API:    /api/admin/devices   add / edit / delete GPS tracker boxes, make a new key, quick add,
                             show a device's bus on the maps or take it off,
                             approve / reject boxes that ask to join by themselves
        /api/admin/buses     add / edit / delete buses, set today's route, test drive
        /api/admin/routes    add / edit / delete routes
        /api/admin/schedules each route's bus schedule
        /api/admin/road-path snap a route to the roads (route editor)
"""

import ipaddress
import os
import socket
import time

from flask import Blueprint, redirect, render_template, request, url_for

from config import Config
from content import rules
from content.words.bus_schedule import DAY_NAMES
from controllers.auth_controller import admin_signed_in
from controllers.helpers import fail, json_body, ok
from models.rider_types import DEFAULT_RIDER_KEY
from services import devices, schedule_service, store, tracking
from services.road_router import RoadRouterError, road_path
from services.tracking_service import BUS_COLOR_PALETTE
from services.words import say

admin_bp = Blueprint("admin", __name__)

TEST_DRIVE_SPEED = rules.TEST_DRIVE_SPEED


@admin_bp.before_request
def require_admin():
    """Everything in this blueprint needs the admin. API calls get 401, pages go to the login page."""
    if request.endpoint == "admin.login_page" or admin_signed_in():
        return None
    if request.path.startswith("/api/"):
        return fail(say("Admin sign-in required."), 401)
    return redirect(url_for("admin.login_page"))


@admin_bp.get("/backend/login")
def login_page():
    """The admin sign-in page (already signed-in admins go straight to the panel)."""
    if admin_signed_in():
        return redirect(url_for("admin.portal"))
    return render_template("admin_login.html", password_file=_local_password_file())


def _local_password_file() -> str | None:
    """
    On your own computer only: the full path of the file that holds this copy's admin password,
    so it is clear which password to use. None on the live server or when .env sets the password.
    """
    if Config.IS_PRODUCTION or os.environ.get("BUSPLUS_ADMIN_PASSWORD"):
        return None
    path = Config.ADMIN_PASSWORD_FILE
    return str(path) if path.exists() else None


@admin_bp.get("/backend")
def portal():
    """The admin panel with the Live map, GPS devices, Routes, Buses, Schedules and Users tabs."""
    return render_template(
        "admin_dashboard.html",
        devices=[d.to_dict() for d in devices.all_devices()],
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
        map_center=Config.UNIVERSITY_LOCATION,
        device_send_every_s=rules.DEVICE_SEND_EVERY_SECONDS,
        default_rider_type=DEFAULT_RIDER_KEY,
        server_now=time.time(),
    )


# ---------------------------------------------------------------------------
# GPS devices (ESP32 + NEO-6M tracker boxes, one per bus)
# ---------------------------------------------------------------------------
def _clean_device_form(data: dict, creating: bool, device_id: str | None = None) -> tuple[dict, str | None]:
    """Check the device form. Returns (clean_fields, error_message). An empty bus = not fitted to a bus."""
    clean: dict = {}
    if creating or "name" in data:
        name = str(data.get("name") or "").strip()[:60]
        if not name:
            return {}, say("Device name is required.")
        clean["name"] = name
    if creating or "bus_id" in data:
        bus_id = str(data.get("bus_id") or "").strip() or None
        if bus_id:
            bus = tracking.get_bus(bus_id)
            if bus is None:
                return {}, say("Bus {id} not found.", id=bus_id)
            other = devices.on_bus(bus_id)
            if other and other.device_id != device_id:
                return {}, say("{bus} already has {device}. Take that device off the bus first.",
                               bus=bus.bus_number, device=other.name)
        clean["bus_id"] = bus_id
    return clean, None


def _device_settings(key: str) -> dict:
    """What goes into the device's firmware (firmware/busplus_tracker/secrets.h)."""
    server_url = url_for("device.receive_report", _external=True)
    return {"key": key, "server_url": server_url, "lan_url": _lan_url(server_url),
            "send_every_s": rules.DEVICE_SEND_EVERY_SECONDS}


def _lan_url(server_url: str) -> str | None:
    """
    On your own computer the page says "localhost", which an ESP32 can't reach. Then this is the
    same address with the computer's Wi-Fi/LAN IP instead (None when the site has a real address).
    """
    host = request.host.split(":")[0]
    if host not in ("localhost", "127.0.0.1", "::1"):
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))                 # sends nothing: only picks the outgoing interface
            ip = probe.getsockname()[0]
    except OSError:
        return None
    if ipaddress.ip_address(ip).is_loopback:
        return None
    return server_url.replace(f"//{host}", f"//{ip}", 1)


def _take_bus_offline(bus_id: str | None) -> None:
    """The device was taken off a bus: that bus stops showing as live straight away."""
    bus = tracking.get_bus(bus_id)
    if bus is not None and bus.is_active and not bus.is_simulating:
        tracking.stop_trip(bus_id)


def _first_bus_without_device() -> str | None:
    """The first bus (in the Buses tab's order) that has no GPS device yet, or None."""
    return next((b["bus_id"] for b in tracking.all_buses() if devices.on_bus(b["bus_id"]) is None), None)


def _default_name(bus_id: str | None) -> str:
    bus = tracking.get_bus(bus_id)
    return devices.next_name(bus.bus_number if bus else None)


@admin_bp.get("/api/admin/devices")
def list_devices():
    """Every device with its latest report, and the boxes asking to join (the GPS devices tab refreshes with this)."""
    return ok(devices=[d.to_dict() for d in devices.all_devices()], waiting=devices.waiting_boxes(),
              next_free_bus=_first_bus_without_device(), now=time.time())


@admin_bp.post("/api/admin/devices")
def create_device():
    """Add a device by hand. Body: {name, bus_id?}. Answers with its secret key - shown this one time only."""
    clean, error = _clean_device_form(json_body(), creating=True)
    if error:
        return fail(error)
    device, key = devices.create(clean["name"], clean["bus_id"])
    return ok(message=say("Device '{name}' added.", name=device.name), device=device.to_dict(),
              settings=_device_settings(key))


@admin_bp.post("/api/admin/devices/quick")
def quick_add_device():
    """Quick add: name and bus filled in automatically (the first bus without a device). Answers with its key."""
    bus_id = _first_bus_without_device()
    device, key = devices.create(_default_name(bus_id), bus_id)
    return ok(message=say("Device '{name}' added.", name=device.name), device=device.to_dict(),
              settings=_device_settings(key))


@admin_bp.put("/api/admin/devices/<device_id>/map")
def set_device_on_map(device_id: str):
    """Body {"show": true|false}: put the device's bus on every map, or take it off (the box stays connected)."""
    show = json_body().get("show")
    if not isinstance(show, bool):
        return fail(say("Say whether to show the bus on the map."))
    device = devices.set_show_on_map(device_id, show)
    if device is None:
        return fail(say("Device {id} not found.", id=device_id), 404)
    if not show:
        _take_bus_offline(device.bus_id)
        message = say("{name} is off the map. Its bus is hidden on every map.", name=device.name)
    else:
        message = say("{name} is on the map. Its bus shows with its next GPS position.", name=device.name)
    return ok(message=message, device=device.to_dict())


@admin_bp.post("/api/admin/devices/waiting/<chip_id>/approve")
def approve_box(chip_id: str):
    """Approve a box that asked to join. Body: {name?, bus_id?} (empty = filled in automatically)."""
    data = json_body()
    known = devices.by_chip(chip_id)
    if "bus_id" not in data:
        data["bus_id"] = known.bus_id if known else _first_bus_without_device()
    if not str(data.get("name") or "").strip():
        data["name"] = known.name if known else _default_name(data["bus_id"])
    clean, error = _clean_device_form(data, creating=True, device_id=known.device_id if known else None)
    if error:
        return fail(error)
    device = devices.approve_box(chip_id, clean["name"], clean["bus_id"])
    if device is None:
        return fail(say("That box is no longer waiting. It may have stopped asking."), 404)
    return ok(message=say("{name} approved. The box gets its key in a few seconds.", name=device.name),
              device=device.to_dict())


@admin_bp.post("/api/admin/devices/waiting/<chip_id>/reject")
def reject_box(chip_id: str):
    """Say no to a box that asked to join (it is ignored for an hour)."""
    if not devices.reject_box(chip_id):
        return fail(say("That box is no longer waiting. It may have stopped asking."), 404)
    return ok(message=say("Box {chip} rejected.", chip=chip_id.upper()))


@admin_bp.put("/api/admin/devices/<device_id>")
def update_device(device_id: str):
    """Rename a device or fit it to another bus. Body: {name?, bus_id?} (bus_id "" = take it off its bus)."""
    device = devices.get(device_id)
    if device is None:
        return fail(say("Device {id} not found.", id=device_id), 404)
    data = json_body()
    clean, error = _clean_device_form(data, creating=False, device_id=device_id)
    if error:
        return fail(error)
    old_bus = device.bus_id
    device = devices.update(device_id, name=clean.get("name"), bus_id=clean.get("bus_id"),
                            change_bus="bus_id" in clean)
    if device.bus_id != old_bus:
        _take_bus_offline(old_bus)
    return ok(message=say("Device '{name}' updated.", name=device.name), device=device.to_dict())


@admin_bp.post("/api/admin/devices/<device_id>/key")
def renew_device_key(device_id: str):
    """Make a new secret key for a device. The old key stops working at once."""
    key = devices.new_key(device_id)
    if key is None:
        return fail(say("Device {id} not found.", id=device_id), 404)
    return ok(message=say("New key made. The old one no longer works."), device=devices.get(device_id).to_dict(),
              settings=_device_settings(key))


@admin_bp.delete("/api/admin/devices/<device_id>")
def delete_device(device_id: str):
    """Remove a device: its key stops working and its bus goes offline."""
    device = devices.get(device_id)
    if device is None or not devices.delete(device_id):
        return fail(say("Device {id} not found.", id=device_id), 404)
    _take_bus_offline(device.bus_id)
    return ok(message=say("Device {id} deleted.", id=device_id))


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
    return ok(message=say("{bus} added.", bus=bus["bus_number"]), bus=bus)


@admin_bp.put("/api/admin/buses/<bus_id>")
def update_bus(bus_id: str):
    """Edit a bus, or send it on another route today."""
    try:
        bus = tracking.update_bus(bus_id, json_body())
    except ValueError as err:
        return fail(str(err))
    if bus is None:
        return fail(say("Bus {id} not found.", id=bus_id), 404)
    return ok(message=say("{bus} updated.", bus=bus["bus_number"]), bus=bus)


@admin_bp.delete("/api/admin/buses/<bus_id>")
def delete_bus(bus_id: str):
    """Delete a bus. Not allowed while it is on a live trip or still has a GPS device fitted."""
    device = devices.on_bus(bus_id)
    if device:
        return fail(say("{device} is fitted to this bus. Move it to another bus in GPS devices first.",
                        device=device.name))
    try:
        deleted = tracking.delete_bus(bus_id)
    except ValueError as err:
        return fail(str(err))
    if not deleted:
        return fail(say("Bus {id} not found.", id=bus_id), 404)
    return ok(message=say("Bus {id} deleted.", id=bus_id))


@admin_bp.post("/api/admin/buses/<bus_id>/simulate")
def simulate_bus(bus_id: str):
    """Test drive: move the bus along its route to Hadi Chattar without a GPS box. {"action": "stop"} ends it."""
    bus = tracking.get_bus(bus_id)
    if bus is None:
        return fail(say("Bus {id} not found.", id=bus_id), 404)
    action = json_body().get("action")            # "start", "stop", or nothing = toggle
    if action == "stop" or (action != "start" and bus.is_simulating):
        tracking.stop_trip(bus_id)
        return ok(simulating=False, message=say("{bus} test drive stopped.", bus=bus.bus_number))
    if not tracking.start_simulation(bus_id, speed_multiplier=TEST_DRIVE_SPEED):
        return fail(say("{bus}'s route has no line to drive along.", bus=bus.bus_number))
    return ok(simulating=True, message=say("{bus} is test-driving its route to {stop}.", bus=bus.bus_number,
                                                     stop=Config.FINAL_DESTINATION["stop_name"]))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@admin_bp.post("/api/admin/road-path")
def snap_to_roads():
    """Road line through the clicked points. Body: {"points": [[lat, lng], ...]} (2 to 60 points)."""
    try:
        points = [(float(p[0]), float(p[1])) for p in json_body().get("points") or []]
    except (TypeError, ValueError, IndexError):
        return fail(say("Points are not valid."))
    if not 2 <= len(points) <= 60 or not all(20 <= lat <= 27 and 88 <= lng <= 93 for lat, lng in points):
        return fail(say("Use 2 to 60 points inside Bangladesh."))
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
    return ok(message=say("Route '{name}' added.", name=route["route_name"]), route=route)


@admin_bp.put("/api/admin/routes/<route_id>")
def update_route(route_id: str):
    """Edit a route's name, colour and/or line."""
    try:
        route = tracking.update_route(route_id, json_body())
    except ValueError as err:
        return fail(str(err))
    if route is None:
        return fail(say("Route {id} not found.", id=route_id), 404)
    return ok(message=say("Route '{name}' updated.", name=route["route_name"]), route=route)


@admin_bp.put("/api/admin/schedules/<route_id>")
def save_schedule(route_id: str):
    """Save a route's weekly timetable: per day, morning (reach campus) and afternoon (leave campus) buses."""
    try:
        schedule = schedule_service.save_timetable(route_id, json_body())
    except LookupError as err:
        return fail(str(err), 404)
    except ValueError as err:
        return fail(str(err))
    return ok(message=say("Schedule of '{name}' saved.", name=schedule["route_name"]), schedule=schedule)


@admin_bp.delete("/api/admin/routes/<route_id>")
def delete_route(route_id: str):
    """Remove a route. Refused while any bus still uses it."""
    try:
        deleted = tracking.delete_route(route_id)
    except ValueError as err:
        return fail(str(err))
    if not deleted:
        return fail(say("Route {id} not found.", id=route_id), 404)
    schedule_service.delete_timetable(route_id)
    return ok(message=say("Route deleted."))
