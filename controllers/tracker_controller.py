"""
Background GPS from the Traccar Client app (see services/tracker_service.py).

  GET or POST /api/tracker     one position from a driver's phone; the "device identifier"
                               set in the app is the driver's secret key from the backend.

No sign-in cookie and no CSRF token here: the app is not a browser. The secret key is the
password, and the number of requests per IP is limited.
"""

import time

from flask import Blueprint, request

from content import rules
from extensions import csrf, limiter
from services import trackers, tracking, users
from services.tracker_service import parse_fix

tracker_bp = Blueprint("tracker", __name__)

TOO_OLD_S = 120          # positions the app saved while offline and sends later: too old to show live


@tracker_bp.route("/api/tracker", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit(rules.TRACKER_LIMIT)
def receive_position():
    """One GPS position from Traccar Client: moves the driver's bus like the driver page does."""
    body = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    fix = parse_fix(request.args.to_dict(), body)
    if fix is None:
        return "No position", 400
    driver = users.get_driver(trackers.driver_for(fix["key"]))
    if driver is None:
        return "Unknown device identifier", 403
    bus_id = driver.assigned_bus_id
    if not bus_id or tracking.get_bus(bus_id) is None:
        return "This driver has no bus", 404

    if fix["fix_time"] is not None and time.time() - fix["fix_time"] > TOO_OLD_S:
        return "OK (old position skipped)", 200          # a 2xx makes the app drop it from its queue
    bus = tracking.get_bus(bus_id)
    if not bus.is_active:
        tracking.start_trip(bus_id)
    tracking.update_location(bus_id, fix["latitude"], fix["longitude"], speed_kmh=fix["speed_kmh"],
                             heading_deg=fix["heading_deg"], accuracy_m=fix["accuracy_m"],
                             fix_time=fix["fix_time"])
    return "OK", 200
