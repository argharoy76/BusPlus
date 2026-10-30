"""
Driver accounts.

The admin creates drivers in the backend. A driver signs in on the front end
with their name, their bus's route and their PIN. The PIN itself is never
stored: only a salted hash made by Werkzeug (`generate_password_hash`).

One phone at a time: while a driver is signed in, `session_token` holds the
token of that phone's browser session, and other phones are refused until the
driver logs out, the admin unlocks the account, or the phone goes quiet for
`Config.DRIVER_SESSION_TIMEOUT_MINUTES`.
"""

from dataclasses import dataclass
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from models.records import DriverRecord


@dataclass
class DriverUser:
    """A driver account as used while the app runs (see the module notes above)."""
    driver_id: str                         # e.g. "DRV-01"
    username: str                          # short login name, e.g. "rafiqul"
    full_name: str                         # drivers pick this name on the login page
    pin_hash: str
    phone: str = ""
    assigned_bus_id: str | None = None     # the bus the admin gave this driver
    assignment_updated_at: str | None = None   # when the admin last changed the bus/route (ISO, UTC)
    assignment_seen_at: str | None = None      # when the driver last opened that notice (ISO, UTC)

    # ---- one-phone lock ----
    session_token: str | None = None       # token of the phone that is signed in (None = free)
    last_login_at: str | None = None
    last_active_at: datetime | None = None  # last request from that phone (memory only)

    @property
    def is_logged_in(self) -> bool:
        """True while a phone holds this account."""
        return self.session_token is not None

    def set_pin(self, pin: str) -> None:
        """Store a new PIN as a salted hash."""
        self.pin_hash = generate_password_hash(pin)

    def check_pin(self, pin: str) -> bool:
        """True if `pin` is this driver's PIN (constant-time comparison inside Werkzeug)."""
        return bool(pin) and check_password_hash(self.pin_hash, pin)

    def to_dict(self) -> dict:
        """JSON form for the admin panel and the driver's own page (never includes the PIN)."""
        return {
            "driver_id": self.driver_id,
            "username": self.username,
            "full_name": self.full_name,
            "phone": self.phone,
            "assigned_bus_id": self.assigned_bus_id,
            "is_logged_in": self.is_logged_in,
            "last_login_at": self.last_login_at,
        }

    # ---------------------------------------------------------------- database
    @classmethod
    def from_record(cls, record: DriverRecord) -> "DriverUser":
        """Build the in-memory driver from their database row."""
        return cls(
            driver_id=record.driver_id,
            username=record.username,
            full_name=record.full_name,
            pin_hash=record.pin_hash,
            phone=record.phone or "",
            assigned_bus_id=record.bus_id,
            assignment_updated_at=record.assignment_updated_at,
            assignment_seen_at=record.assignment_seen_at,
            session_token=record.session_token,
            last_login_at=record.last_login_at,
        )

    def to_record(self) -> DriverRecord:
        """Database row for this driver (saved with `db.session.merge`)."""
        return DriverRecord(
            driver_id=self.driver_id,
            username=self.username,
            full_name=self.full_name,
            phone=self.phone,
            pin_hash=self.pin_hash,
            bus_id=self.assigned_bus_id,
            assignment_updated_at=self.assignment_updated_at,
            assignment_seen_at=self.assignment_seen_at,
            session_token=self.session_token,
            last_login_at=self.last_login_at,
        )
