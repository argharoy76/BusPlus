"""
Positions from the GPS tracker boxes (ESP32 + NEO-6M) fitted to the buses.

  POST /api/device/location     one report from a device (JSON, see services/device_service.py)
                                header  X-Device-Key: <the device's secret key>
  POST /api/device/pair         a box without a key asks to join: {"chip_id", "token", "fw"}
                                (the admin approves it in the backend; then it receives its key here)

No sign-in cookie and no CSRF token here: the device is not a browser. The secret key is
its password, and each key may only send so many reports per minute (content/rules.py).

Answers are small JSON objects the firmware can read:
  200 {"ok": true, "bus_id": "KU-BUS-01", "send_every_s": 2, "on_map": true}
  4xx {"ok": false, "error": "..."}
A device the admin took off the map still reports (it shows as connected), but its bus stays off every map.
"""

import hashlib
import time

from flask import Blueprint, jsonify, request
from flask_limiter.util import get_remote_address

from content import rules
from extensions import csrf, limiter
from services import devices, tracking
from services.device_service import PAIR_ASK_EVERY_S, ReportError, parse_report
from services.words import say

device_bp = Blueprint("device", __name__)


def _presented_key() -> str:
    """The key the device sent: "X-Device-Key: <key>" (or "Authorization: Bearer <key>")."""
    key = request.headers.get("X-Device-Key", "")
    if not key:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            key = auth[7:]
    return key.strip()


def _limit_per_device() -> str:
    """Rate-limit each key on its own (many buses may share one mobile-network IP address)."""
    key = _presented_key()
    return "dev:" + hashlib.sha256(key.encode()).hexdigest()[:16] if key else "ip:" + get_remote_address()


def _limit_per_chip() -> str:
    """Rate-limit join requests per box (chip ID), falling back to the IP address."""
    data = request.get_json(silent=True)
    chip = str(data.get("chip_id") or "")[:20] if isinstance(data, dict) else ""
    return "pair:" + chip.upper() if chip else "ip:" + get_remote_address()


def _answer(http_status: int = 200, **payload):
    if http_status >= 400:
        return jsonify({"ok": False, **payload}), http_status
    return jsonify({"ok": True, **payload}), http_status


@device_bp.post("/api/device/location")
@csrf.exempt
@limiter.limit(rules.DEVICE_LIMIT, key_func=_limit_per_device)
def receive_report():
    """One report from a tracker box: moves its bus on every map (or just says "still searching")."""
    device = devices.by_key(_presented_key())
    if device is None:
        return _answer(401, error=say("Unknown device key."))
    try:
        report = parse_report(request.get_json(silent=True))
    except ReportError as err:
        return _answer(400, error=str(err))

    now = time.time()
    fix_time = report["fix_time"]
    if fix_time is None or abs(now - fix_time) > 300:            # no GPS time, or the device's clock is off
        fix_time = now - report["age_s"] if report["age_s"] is not None else None
    too_old = fix_time is not None and now - fix_time > rules.DEVICE_MAX_FIX_AGE_SECONDS
    has_fix = report["has_fix"] and not too_old
    device.note_report(report, has_fix, ip=request.remote_addr or "")

    bus = tracking.get_bus(device.bus_id)
    if bus is None:
        return _answer(409, error=say("This device is not fitted to a bus. Choose its bus in the backend."))
    if not device.show_on_map:                    # the admin took this bus off the map: note the report only
        if bus.is_active and not bus.is_simulating:
            tracking.stop_trip(bus.bus_id)
        return _answer(bus_id=bus.bus_id, send_every_s=rules.DEVICE_SEND_EVERY_SECONDS, on_map=False)
    if has_fix:
        if bus.is_simulating:                     # real GPS wins over an admin test drive
            tracking.stop_trip(bus.bus_id)
        if not bus.is_active:
            tracking.start_trip(bus.bus_id)
        hdop = report["hdop"]
        tracking.update_location(
            bus.bus_id, report["latitude"], report["longitude"],
            speed_kmh=report["speed_kmh"], heading_deg=report["heading_deg"],
            accuracy_m=hdop * rules.GPS_HDOP_TO_METERS if hdop is not None else None,
            fix_time=fix_time)
    return _answer(bus_id=bus.bus_id, send_every_s=rules.DEVICE_SEND_EVERY_SECONDS, on_map=True)


@device_bp.post("/api/device/pair")
@csrf.exempt
@limiter.limit(rules.DEVICE_PAIR_LIMIT, key_func=_limit_per_chip)
def ask_to_join():
    """
    A box without a key asks to join. Answers (the box asks again every retry_s seconds while waiting):
      200 {"ok": true, "status": "waiting",  "code": "483920", "retry_s": 5}
      200 {"ok": true, "status": "approved", "key": "...", "send_every_s": 2}   - the key, this one time
      403 {"ok": false, "status": "rejected", "error": "..."}
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _answer(400, error=say("Send the report as JSON."))
    try:
        result = devices.ask_to_join(data.get("chip_id"), data.get("token"), data.get("fw") or "",
                                     ip=request.remote_addr or "")
    except ReportError as err:
        return _answer(400, error=str(err))
    if result["status"] == "rejected":
        return _answer(403, status="rejected", error=say("The admin did not approve this box."))
    if result["status"] == "approved":
        return _answer(status="approved", key=result["key"], device_id=result["device_id"],
                       send_every_s=rules.DEVICE_SEND_EVERY_SECONDS)
    return _answer(status="waiting", code=result["code"], retry_s=PAIR_ASK_EVERY_S)
