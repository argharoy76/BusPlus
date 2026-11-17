"""Small helpers shared by the controllers (request parsing, JSON replies)."""

import math

from flask import jsonify, request

from models.bus import BUS_AUDIENCES


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
    """The ?audience= query value if it is a rider type (student, teacher, ...), else None (= all buses)."""
    value = request.args.get("audience")
    return value if value in BUS_AUDIENCES else None


def optional_float(value) -> float | None:
    """float(value), or None when the value is missing, not a number, or not finite (nan, inf)."""
    try:
        number = None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None
    return number if number is not None and math.isfinite(number) else None
