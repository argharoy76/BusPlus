"""
GPS tracker boxes (ESP32 + NEO-6M) that report each bus's position. Firmware: firmware/.

How it works:
  * The admin adds a device in the backend (GPS devices tab) and fits it to a bus.
    BusPlus makes a secret key for it and shows it ONCE, together with the server URL.
  * Both go into the device's firmware (firmware/busplus_tracker/secrets.h).
  * The device then POSTs its position every few seconds to /api/device/location
    (controllers/device_controller.py) with the key in the "X-Device-Key" header.
  * Each position moves the device's bus on every live map, through the same speed filter
    and road snapping as before. The bus goes online with the first position and offline by
    itself when no position arrives for AUTO_OFFLINE_MINUTES (content/rules.py).

Only a SHA-256 hash of each key is stored. A lost key can't be shown again: make a new one
in the backend and put that into the device.

Boxes can also JOIN BY THEMSELVES, so nobody has to copy a key:
  * A box without a key POSTs /api/device/pair with its chip ID and a random secret ("token")
    that it made once and keeps in its flash memory.
  * The backend lists it under "Boxes asking to join" with a 6-digit pairing code. The code is
    worked out from the chip ID and the token, and the box prints the same code on its serial
    monitor, so the admin can check it is the right box before approving it.
  * The admin approves it (name + bus). On its next request the box receives its key - once,
    and only together with the same token - and saves it. A rejected box is told so and ignored
    for an hour. Requests waiting for approval are kept in memory only.

Like the other services, devices are kept in memory and every admin change is written
straight through to the database. All public methods are thread-safe.
"""

import hashlib
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from models.device import GpsDevice
from models.records import GpsDeviceRecord
from services import store
from services.words import say

KEY_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: easy to read and type
KEY_LENGTH = 24                                     # about 119 bits: impossible to guess

CHIP_ID_RE = re.compile(r"^[0-9A-Fa-f]{6,16}$")    # the ESP32's chip ID (from its factory MAC address)
TOKEN_RE = re.compile(r"^[A-Za-z0-9]{16,64}$")     # the box's own random pairing secret
PAIR_FORGET_S = 10 * 60      # a waiting box that stops asking is forgotten after this long
PAIR_KEY_KEEP_S = 30 * 60    # an approved key waits this long for its box to pick it up
PAIR_REJECT_S = 60 * 60      # a rejected box is ignored this long
PAIR_MAX_WAITING = 20        # at most this many boxes waiting at the same time
PAIR_ASK_EVERY_S = 5         # the box is told to ask again this often


@dataclass
class JoinRequest:
    """A box that asked to join (memory only)."""
    chip_id: str
    token_hash: str
    code: str                         # 6-digit pairing code, also printed by the box
    firmware: str = ""
    ip: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0
    asks: int = 0
    status: str = "waiting"           # waiting, approved or rejected
    key: str | None = None            # the new key, kept only until the box has picked it up
    device_id: str | None = None
    decided_at: float = 0.0

    def to_dict(self, known_device: "GpsDevice | None") -> dict:
        """JSON for the backend's "Boxes asking to join" list (never contains the token or a key)."""
        return {"chip_id": self.chip_id, "code": self.code, "firmware": self.firmware, "ip": self.ip,
                "first_seen": round(self.first_seen, 1), "last_seen": round(self.last_seen, 1),
                "asks": self.asks,
                "known_device_id": known_device.device_id if known_device else None,
                "known_device_name": known_device.name if known_device else None}


def pairing_code(chip_id: str, token: str) -> str:
    """The 6-digit code the backend shows and the box prints, from its chip ID and token."""
    digest = hashlib.sha256(f"{chip_id.upper()}:{token}".encode()).hexdigest()
    return f"{int(digest[:8], 16) % 1_000_000:06d}"


def hash_key(key: str) -> str:
    """The stored form of a device key."""
    return hashlib.sha256(key.strip().lower().encode()).hexdigest()


class DeviceService:
    """All GPS devices (one instance per process)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._devices: dict[str, GpsDevice] = {}
        self._by_hash: dict[str, str] = {}             # key hash -> device_id
        self._joins: dict[str, JoinRequest] = {}       # chip ID -> box asking to join

    def load(self) -> None:
        """(Re)load all devices from the database. Called once by create_app()."""
        with self._lock:
            self._devices = {r.device_id: GpsDevice.from_record(r) for r in store.all_rows(GpsDeviceRecord)}
            self._by_hash = {d.key_hash: d.device_id for d in self._devices.values()}
            self._joins.clear()                          # boxes asking to join are memory only

    # =====================================================================
    # Reading
    # =====================================================================
    def all_devices(self) -> list[GpsDevice]:
        """Every device, in ID order."""
        with self._lock:
            return sorted(self._devices.values(), key=lambda d: d.device_id)

    def get(self, device_id: str | None) -> GpsDevice | None:
        """The device with this ID, or None."""
        with self._lock:
            return self._devices.get(device_id or "")

    def by_key(self, key: str | None) -> GpsDevice | None:
        """The device a secret key belongs to (None for a missing or unknown key)."""
        if not key or not key.strip():
            return None
        with self._lock:
            return self._devices.get(self._by_hash.get(hash_key(key), ""))

    def on_bus(self, bus_id: str) -> GpsDevice | None:
        """The device fitted to a bus, or None."""
        with self._lock:
            return next((d for d in self._devices.values() if d.bus_id == bus_id), None)

    def by_chip(self, chip_id: str | None) -> GpsDevice | None:
        """The device that joined with this ESP32 chip ID, or None."""
        if not chip_id:
            return None
        with self._lock:
            return next((d for d in self._devices.values() if d.chip_id and d.chip_id == chip_id.upper()), None)

    def next_name(self, bus_number: str | None) -> str:
        """A name for a new device: "Tracker in <bus>", or "GPS box <n>" when it isn't fitted to a bus."""
        if bus_number:
            return say("Tracker in {bus}", bus=bus_number)[:60]
        with self._lock:
            return say("GPS box {number}", number=len(self._devices) + 1)[:60]

    # =====================================================================
    # Admin setup
    # =====================================================================
    def create(self, name: str, bus_id: str | None, chip_id: str = "") -> tuple[GpsDevice, str]:
        """Add a device. Returns (device, its new secret key). The form is checked by the admin controller."""
        with self._lock:
            n = 1
            while f"GPS-{n:02d}" in self._devices:          # never reuse an ID that is in use
                n += 1
            key = _new_key()
            device = GpsDevice(device_id=f"GPS-{n:02d}", name=name, key_hash=hash_key(key),
                               key_hint=key[-4:], bus_id=bus_id, created_at=store.utc_now_iso(),
                               chip_id=chip_id.upper())
            self._devices[device.device_id] = device
            self._by_hash[device.key_hash] = device.device_id
            store.save(device.to_record())
            return device, key

    def update(self, device_id: str, name: str | None = None, bus_id: str | None = None,
               change_bus: bool = False) -> GpsDevice | None:
        """Rename a device and/or fit it to another bus (bus_id None with change_bus = take it off)."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return None
            if name:
                device.name = name
            if change_bus:
                device.bus_id = bus_id
            store.save(device.to_record())
            return device

    def new_key(self, device_id: str) -> str | None:
        """Replace a device's key: the old key stops working at once. None if there is no such device."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return None
            self._by_hash.pop(device.key_hash, None)
            key = _new_key()
            device.key_hash, device.key_hint = hash_key(key), key[-4:]
            self._by_hash[device.key_hash] = device_id
            store.save(device.to_record())
            return key

    def set_show_on_map(self, device_id: str, show: bool) -> GpsDevice | None:
        """Put a device's bus on every map, or take it off (the box stays connected). None if no such device."""
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                return None
            device.show_on_map = bool(show)
            store.save(device.to_record())
            return device

    def delete(self, device_id: str) -> bool:
        """Remove a device (its key stops working). False if it doesn't exist."""
        with self._lock:
            device = self._devices.pop(device_id, None)
            if device is None:
                return False
            self._by_hash.pop(device.key_hash, None)
            store.delete(GpsDeviceRecord, device_id)
            return True


    # =====================================================================
    # Boxes that join by themselves (see the top of this file)
    # =====================================================================
    def ask_to_join(self, chip_id: str, token: str, firmware: str = "", ip: str = "") -> dict:
        """
        One request from a box without a key. Returns what to answer:
          {"status": "waiting", "code"}          not approved yet (the box asks again)
          {"status": "approved", "key", "code"}  approved: its key (handed out this one time)
          {"status": "rejected"}                 the admin said no
        Raises ReportError for a malformed request or when too many boxes are waiting.
        """
        chip_id, token = str(chip_id or "").strip().upper(), str(token or "").strip()
        if not CHIP_ID_RE.match(chip_id) or not TOKEN_RE.match(token):
            raise ReportError(say("Send the box's chip ID and its pairing token."))
        now = time.time()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            self._forget_old_joins(now)
            join = self._joins.get(chip_id)
            if join is not None and not secrets.compare_digest(join.token_hash, token_hash):
                if join.status == "rejected":
                    return {"status": "rejected"}
                raise ReportError(say("Another box with this chip ID is already waiting."))
            if join is None:
                if sum(j.status == "waiting" for j in self._joins.values()) >= PAIR_MAX_WAITING:
                    raise ReportError(say("Too many boxes are waiting. Approve or reject some in the backend."))
                join = JoinRequest(chip_id=chip_id, token_hash=token_hash, code=pairing_code(chip_id, token),
                                   first_seen=now)
                self._joins[chip_id] = join
            join.last_seen, join.asks = now, join.asks + 1
            join.firmware, join.ip = str(firmware or "")[:20] or join.firmware, ip
            if join.status == "approved" and join.key:
                key = join.key
                del self._joins[chip_id]                 # handed out once: forget it
                return {"status": "approved", "key": key, "code": join.code, "device_id": join.device_id}
            return {"status": join.status, "code": join.code}

    def waiting_boxes(self) -> list[dict]:
        """Boxes waiting for the admin's approval, oldest first (for the backend)."""
        with self._lock:
            self._forget_old_joins(time.time())
            waiting = sorted((j for j in self._joins.values() if j.status == "waiting"), key=lambda j: j.first_seen)
            return [j.to_dict(self.by_chip(j.chip_id)) for j in waiting]

    def approve_box(self, chip_id: str, name: str, bus_id: str | None) -> GpsDevice | None:
        """
        Approve a waiting box: it becomes a device (or, if it joined before, its device gets a new key).
        The key is handed to the box on its next request. None if no such box is waiting.
        The admin controller checks the name and the bus first.
        """
        chip_id = str(chip_id or "").strip().upper()
        with self._lock:
            join = self._joins.get(chip_id)
            if join is None or join.status != "waiting":
                return None
            device = self.by_chip(chip_id)
            if device is not None:
                key = self.new_key(device.device_id)
                device = self.update(device.device_id, name=name, bus_id=bus_id, change_bus=True)
            else:
                device, key = self.create(name, bus_id, chip_id=chip_id)
            join.status, join.key, join.device_id, join.decided_at = "approved", key, device.device_id, time.time()
            return device

    def reject_box(self, chip_id: str) -> bool:
        """Say no to a waiting box: it is ignored for an hour. False if no such box is waiting."""
        chip_id = str(chip_id or "").strip().upper()
        with self._lock:
            join = self._joins.get(chip_id)
            if join is None or join.status != "waiting":
                return False
            join.status, join.decided_at = "rejected", time.time()
            return True

    def _forget_old_joins(self, now: float) -> None:
        """Drop boxes that stopped asking, keys nobody picked up, and rejections that have run out."""
        for chip_id, join in list(self._joins.items()):
            if ((join.status == "waiting" and now - join.last_seen > PAIR_FORGET_S)
                    or (join.status == "approved" and now - join.decided_at > PAIR_KEY_KEEP_S)
                    or (join.status == "rejected" and now - join.decided_at > PAIR_REJECT_S)):
                del self._joins[chip_id]


def _new_key() -> str:
    return "".join(secrets.choice(KEY_LETTERS) for _ in range(KEY_LENGTH))


# =========================================================================
# Reading a report from a device
# =========================================================================
class ReportError(ValueError):
    """A report that can't be used. The message goes back to the device (and its serial monitor)."""


def parse_report(body: dict) -> dict:
    """
    Check one report from a device and return it in BusPlus's own units.

    Expected JSON (only lat/lng are required when "fix" is true; see firmware/README.md):
        {"fix": true, "lat": 22.80209, "lng": 89.53398, "speed_kmh": 31.5, "course": 182.0,
         "sats": 8, "hdop": 1.1, "age_ms": 420, "time": "2026-11-17T08:15:01Z",
         "battery_v": 12.4, "rssi": -67, "fw": "1.0.0", "uptime_s": 3600}

    "fix": false is a heartbeat while the GPS is still searching: the device is shown as
    connected but the bus doesn't move. Raises ReportError for anything unusable.
    """
    if not isinstance(body, dict):
        raise ReportError(say("Send the report as JSON."))
    has_fix = body.get("fix", True) not in (False, 0, "0", "false", "no")
    report = {
        "has_fix": has_fix,
        "satellites": _int_in(body.get("sats", body.get("satellites")), 0, 99),
        "hdop": _float_in(body.get("hdop"), 0, 99.99),
        "battery_v": _float_in(body.get("battery_v"), 0, 60),
        "rssi_dbm": _int_in(body.get("rssi"), -150, 0),
        "firmware": str(body.get("fw") or "")[:20],
        "uptime_s": _int_in(body.get("uptime_s"), 0, 10**9),
        "age_s": None, "fix_time": None,
        "latitude": None, "longitude": None, "speed_kmh": None, "heading_deg": None,
    }
    if not has_fix:
        return report

    lat = _float_in(body.get("lat", body.get("latitude")), -90, 90)
    lng = _float_in(body.get("lng", body.get("lon", body.get("longitude"))), -180, 180)
    if lat is None or lng is None:
        raise ReportError(say("Valid latitude and longitude are required."))
    if lat == 0 and lng == 0:
        raise ReportError(say("The GPS has no position yet (0, 0)."))
    age_ms = _float_in(body.get("age_ms"), 0, 86_400_000)
    report.update(
        latitude=lat,
        longitude=lng,
        speed_kmh=_float_in(body.get("speed_kmh", body.get("speed")), 0, 250),
        heading_deg=_float_in(body.get("course", body.get("heading")), 0, 360),
        age_s=age_ms / 1000 if age_ms is not None else None,
        fix_time=_timestamp(body.get("time")),
    )
    return report


def _float_in(value, low: float, high: float) -> float | None:
    """A finite number between low and high, else None (bad values are ignored, not fatal)."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def _int_in(value, low: int, high: int) -> int | None:
    number = _float_in(value, low, high)
    return int(round(number)) if number is not None else None


def _timestamp(value) -> float | None:
    """GPS time as ISO text ("2026-11-17T08:15:01Z") or Unix seconds -> Unix seconds (None if unreadable)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(value) and value > 1e9 else None
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.timestamp() if parsed.tzinfo else None
    return None
