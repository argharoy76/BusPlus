"""
A GPS tracker box fitted to a bus: an ESP32 with a NEO-6M GPS module (see firmware/).

The setup part (name, which bus, the hash of its secret key) is saved in the
`gps_devices` table. The live part (last report, satellites, signal ...) only lives
in memory and is refreshed by every report the device sends.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from content import rules
from models.records import GpsDeviceRecord

# What the admin panel shows for a device (see GpsDevice.status)
NEVER = "never"          # has not reported since the server started
OFFLINE = "offline"      # nothing heard for DEVICE_OFFLINE_SECONDS
NO_FIX = "no_fix"        # reporting, but the GPS has no position yet (searching for satellites)
ONLINE = "online"        # reporting good positions


@dataclass
class GpsDevice:
    """One tracker box: its setup (saved in the database) and its latest report (memory only)."""
    # ---- set up by the admin (saved in the database) ----
    device_id: str                       # e.g. "GPS-01"
    name: str                            # e.g. "Tracker in Bus #01"
    key_hash: str                        # sha256 of the secret key (the key itself is never stored)
    key_hint: str = ""                   # last 4 letters of the key, so the admin can tell keys apart
    bus_id: str | None = None            # the bus it is fitted to (None = in the drawer)
    created_at: str = ""
    chip_id: str = ""                    # ESP32 chip ID, when the box joined by itself (see services/device_service.py)
    show_on_map: bool = True             # False: the admin took its bus off every map (the box stays connected)

    # ---- latest report (memory only) ----
    last_seen_ts: float = 0.0            # any report, with or without a position
    last_fix_ts: float = 0.0             # last report with a usable position
    satellites: int | None = None
    hdop: float | None = None            # GPS precision: 1 = excellent, 2-5 = good, above 5 = poor
    battery_v: float | None = None
    rssi_dbm: int | None = None          # Wi-Fi / mobile signal, e.g. -67
    firmware: str = ""
    uptime_s: int | None = None
    reports: int = 0                     # reports since the server started
    last_ip: str = ""

    def status(self, now: float | None = None) -> str:
        """NEVER, OFFLINE, NO_FIX or ONLINE (see the constants above)."""
        now = time.time() if now is None else now
        if not self.last_seen_ts:
            return NEVER
        if now - self.last_seen_ts > rules.DEVICE_OFFLINE_SECONDS:
            return OFFLINE
        if now - self.last_fix_ts > rules.DEVICE_OFFLINE_SECONDS:
            return NO_FIX
        return ONLINE

    def note_report(self, report: dict, has_fix: bool, ip: str = "") -> None:
        """Remember the health values of a report (position handling is the tracking service's job)."""
        now = time.time()
        self.last_seen_ts = now
        if has_fix:
            self.last_fix_ts = now
        self.satellites = report.get("satellites")
        self.hdop = report.get("hdop")
        self.battery_v = report.get("battery_v")
        self.rssi_dbm = report.get("rssi_dbm")
        self.firmware = report.get("firmware") or self.firmware
        self.uptime_s = report.get("uptime_s")
        self.reports += 1
        self.last_ip = ip

    def to_dict(self) -> dict:
        """JSON form for the admin panel (never contains the key or its hash)."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "bus_id": self.bus_id,
            "key_hint": self.key_hint,
            "created_at": self.created_at,
            "chip_id": self.chip_id,
            "show_on_map": self.show_on_map,
            "status": self.status(),
            "last_seen_ts": round(self.last_seen_ts, 1),
            "last_seen_iso": _iso(self.last_seen_ts),
            "last_fix_ts": round(self.last_fix_ts, 1),
            "satellites": self.satellites,
            "hdop": self.hdop,
            "battery_v": self.battery_v,
            "rssi_dbm": self.rssi_dbm,
            "firmware": self.firmware,
            "uptime_s": self.uptime_s,
            "reports": self.reports,
            "last_ip": self.last_ip,
        }

    # ---------------------------------------------------------------- database
    @classmethod
    def from_record(cls, record: GpsDeviceRecord) -> "GpsDevice":
        """Build the in-memory device from its database row (no report yet)."""
        return cls(device_id=record.device_id, name=record.name, key_hash=record.key_hash,
                   key_hint=record.key_hint or "", bus_id=record.bus_id, created_at=record.created_at,
                   chip_id=record.chip_id or "", show_on_map=record.show_on_map is not False)

    def to_record(self) -> GpsDeviceRecord:
        """Database row for this device's setup (saved with `db.session.merge`)."""
        return GpsDeviceRecord(device_id=self.device_id, name=self.name, bus_id=self.bus_id,
                               key_hash=self.key_hash, key_hint=self.key_hint, created_at=self.created_at,
                               chip_id=self.chip_id or None, show_on_map=self.show_on_map)


def _iso(ts: float) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts else None
