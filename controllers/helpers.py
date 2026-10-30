"""Small helpers shared by the controllers (request parsing, JSON replies, sign-in checks)."""

from functools import wraps

from flask import jsonify, request, session

from models.bus import BUS_AUDIENCES
from services import tracking, users


def json_body() -> dict:
    """The request's JSON body as a dict ({} if missing or not JSON)."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def ok(**payload):
    """A successful JSON reply: {"success": true, ...}."""
    return jsonify({"success": True, **payload})


def fail(message: str, status: int = 400):
    """A failed JSON reply with a message the page can show: {"success": false, "message": ...}."""
    return jsonify({"success": False, "message": message}), status


def audience_arg() -> str | None:
    """The ?audience= query value if it is "student" or "teacher", else None (= all buses)."""
    value = request.args.get("audience")
    return value if value in BUS_AUDIENCES else None


def optional_float(value) -> float | None:
    """float(value), or None when the value is missing or not a number."""
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def driver_required(view):
    """
    Only for the signed-in driver's phone. Passes the driver's own bus ID to the view
    as `bus_id` (taken from the account, never from the request).

    Answers 401 if nobody is signed in as a driver, 409 if another phone took the
    account over, and 404 if the admin hasn't given the driver a bus.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        driver_id = session.get("driver_id")
        if session.get("role") != "driver" or not driver_id:
            return fail("Please log in as a driver.", 401)
        if not users.touch(driver_id, session.get("session_token")):
            return fail("This account was signed in on another device. Please log in again.", 409)
        driver = users.get_driver(driver_id)
        if not driver or not tracking.get_bus(driver.assigned_bus_id):
            return fail("No bus is assigned to you. Ask the admin.", 404)
        return view(*args, bus_id=driver.assigned_bus_id, **kwargs)
    return wrapper
