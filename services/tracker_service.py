"""
Background GPS for drivers, with the free Traccar Client app (Android and iPhone).

A web page can only use GPS while it is open on the screen: phones pause it when the screen
locks or another app is opened. Traccar Client is a small app that keeps sending the phone's
location in the background (and stores it while there is no internet). It speaks the simple
"OsmAnd" protocol, which BusPlus understands at /api/tracker:

  * The admin gives each driver a secret key (backend > Drivers > Background GPS).
  * In Traccar Client the driver sets:  Server URL = https://<your site>/api/tracker,
    Device identifier = that key, and switches "Service status" on.
  * Every fix then moves the driver's bus exactly like the driver page does (same speed filter,
    same road snapping, same live maps). The bus goes online with the first fix and offline by
    itself when no GPS arrives for a while (content/rules.py: AUTO_OFFLINE_MINUTES).

Both request styles of the app are understood:
  old / query style:  ?id=KEY&lat=..&lon=..&timestamp=<unix s>&speed=<knots>&bearing=..&accuracy=..
  new / JSON style:   {"device_id": KEY, "location": {"timestamp": "<ISO>", "coords":
                       {"latitude", "longitude", "speed" (m/s), "heading", "accuracy"}}}
"""

import secrets
import threading
from datetime import datetime

from models.records import TrackerKeyRecord
from services import store

KEY_LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i: easy to type on a phone
KEY_LENGTH = 12
KNOTS_TO_KMH = 1.852


class TrackerService:
    """The drivers' tracker keys (one instance per process, kept in memory)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key_of: dict[str, str] = {}        # driver_id -> key
        self._driver_of: dict[str, str] = {}     # key -> driver_id

    def load(self) -> None:
        """Read the keys from the database. Called once by create_app()."""
        with self._lock:
            self._key_of = {r.driver_id: r.key for r in store.all_rows(TrackerKeyRecord)}
            self._driver_of = {key: driver_id for driver_id, key in self._key_of.items()}

    def key_for(self, driver_id: str, renew: bool = False) -> str:
        """The driver's key; made on first use, or replaced when `renew` (the old one stops working)."""
        with self._lock:
            key = self._key_of.get(driver_id)
            if key and not renew:
                return key
            if key:
                self._driver_of.pop(key, None)
            key = "".join(secrets.choice(KEY_LETTERS) for _ in range(KEY_LENGTH))
            self._key_of[driver_id] = key
            self._driver_of[key] = driver_id
            store.save(TrackerKeyRecord(driver_id=driver_id, key=key, created_at=store.utc_now_iso()))
            return key

    def driver_for(self, key: str | None) -> str | None:
        """The driver_id a key belongs to (None for an unknown key)."""
        with self._lock:
            return self._driver_of.get((key or "").strip().lower())

    def forget(self, driver_id: str) -> None:
        """The driver was deleted: their key stops working."""
        with self._lock:
            key = self._key_of.pop(driver_id, None)
            if key:
                self._driver_of.pop(key, None)
                store.delete(TrackerKeyRecord, driver_id)


def parse_fix(args: dict, body: dict | None) -> dict | None:
    """
    One position from Traccar Client, in either request style, as
    {"key", "latitude", "longitude", "speed_kmh", "heading_deg", "accuracy_m", "fix_time"}.
    None if it has no usable position.
    """
    if isinstance(body, dict) and isinstance(body.get("location"), dict):
        location = body["location"]
        coords = location.get("coords") or {}
        speed = _number(coords.get("speed"))
        fix = {
            "key": body.get("device_id"),
            "latitude": _number(coords.get("latitude")),
            "longitude": _number(coords.get("longitude")),
            "speed_kmh": speed * 3.6 if speed is not None and speed >= 0 else None,
            "heading_deg": _positive(coords.get("heading")),
            "accuracy_m": _positive(coords.get("accuracy")),
            "fix_time": _timestamp(location.get("timestamp")),
        }
    else:
        merged = {**(body or {}), **args} if isinstance(body, dict) else dict(args)
        lat, lng = _number(merged.get("lat")), _number(merged.get("lon"))
        if (lat is None or lng is None) and "," in str(merged.get("location", "")):
            lat, lng = (_number(part) for part in str(merged["location"]).split(",", 1))
        speed = _number(merged.get("speed"))
        fix = {
            "key": merged.get("id") or merged.get("deviceid"),
            "latitude": lat,
            "longitude": lng,
            "speed_kmh": speed * KNOTS_TO_KMH if speed is not None and speed >= 0 else None,
            "heading_deg": _positive(merged.get("bearing", merged.get("heading"))),
            "accuracy_m": _positive(merged.get("accuracy")),
            "fix_time": _timestamp(merged.get("timestamp")),
        }
    if fix["latitude"] is None or fix["longitude"] is None:
        return None
    if not (-90 <= fix["latitude"] <= 90 and -180 <= fix["longitude"] <= 180):
        return None
    fix["key"] = str(fix["key"] or "")
    return fix


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None          # NaN -> None


def _positive(value) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _timestamp(value) -> float | None:
    """Unix seconds / milliseconds or ISO text -> Unix seconds (None if unreadable)."""
    number = _number(value)
    if number is not None:
        return number / 1000 if number > 1e11 else number
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None
