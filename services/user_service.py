"""
Driver accounts: admin setup, front-end sign-in with a one-phone lock, and daily duty notices.

Like TrackingService, drivers are kept in memory and every change is written
through to the `drivers` table. All public methods are thread-safe.
"""

import secrets
import threading
from datetime import UTC, datetime, timedelta

from models.records import DriverRecord
from models.user import DriverUser
from services import store
from services.words import say


class LoginError(Exception):
    """A driver sign-in was refused. `status` is the HTTP status code to answer with."""

    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


class UserService:
    """All driver accounts (one instance per process)."""
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._drivers: dict[str, DriverUser] = {}

    def load(self) -> None:
        """(Re)load all drivers from the database. Called once by create_app()."""
        with self._lock:
            self._drivers = {r.driver_id: DriverUser.from_record(r) for r in store.all_rows(DriverRecord)}

    # =====================================================================
    # Reading
    # =====================================================================
    def all_drivers(self) -> list[DriverUser]:
        """Every driver account."""
        with self._lock:
            return list(self._drivers.values())

    def get_driver(self, driver_id: str | None) -> DriverUser | None:
        """The driver with this ID, or None."""
        with self._lock:
            return self._drivers.get(driver_id or "")

    def find_driver(self, name_or_id: str) -> DriverUser | None:
        """Exact (case-insensitive) match on driver ID, full name or username. No partial matches."""
        wanted = (name_or_id or "").strip().lower()
        if not wanted:
            return None
        with self._lock:
            return next((d for d in self._drivers.values()
                         if wanted in (d.driver_id.lower(), d.full_name.lower(), d.username.lower())), None)

    def search_drivers(self, query: str) -> list[dict]:
        """Name suggestions for the driver login page: drivers whose name/username/ID contains `query`."""
        q = (query or "").strip().lower()
        with self._lock:
            return [{"driver_id": d.driver_id, "full_name": d.full_name, "assigned_bus_id": d.assigned_bus_id}
                    for d in self._drivers.values()
                    if not q or q in d.full_name.lower() or q in d.username.lower() or q in d.driver_id.lower()]

    def drivers_of_bus(self, bus_id: str) -> list[DriverUser]:
        """Drivers whose assigned bus is `bus_id`."""
        with self._lock:
            return [d for d in self._drivers.values() if d.assigned_bus_id == bus_id]

    def name_taken(self, full_name: str, except_driver_id: str | None = None) -> bool:
        """True if another driver already uses this name (names must be unique to sign in by name)."""
        wanted = full_name.strip().lower()
        with self._lock:
            return any(d.full_name.lower() == wanted and d.driver_id != except_driver_id
                       for d in self._drivers.values())

    # =====================================================================
    # Admin setup
    # =====================================================================
    def create_driver(self, full_name: str, pin: str, bus_id: str, phone: str = "") -> DriverUser:
        """Add a driver (the form is already checked by the admin controller)."""
        with self._lock:
            n = 1
            while f"DRV-{n:02d}" in self._drivers:          # never reuse an ID that is in use
                n += 1
            driver_id = f"DRV-{n:02d}"
            driver = DriverUser(driver_id=driver_id, username=driver_id.lower().replace("-", ""),
                                full_name=full_name, pin_hash="", phone=phone, assigned_bus_id=bus_id,
                                assignment_updated_at=store.utc_now_iso())
            driver.set_pin(pin)
            self._drivers[driver_id] = driver
            store.save(driver.to_record())
            return driver

    def update_driver(self, driver_id: str, full_name: str | None = None, phone: str | None = None,
                      pin: str | None = None, bus_id: str | None = None) -> DriverUser | None:
        """Change a driver's details. Only the given fields change. A new bus counts as a duty change."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver is None:
                return None
            if full_name:
                driver.full_name = full_name
            if phone is not None:
                driver.phone = phone
            if pin:
                driver.set_pin(pin)
            if bus_id and bus_id != driver.assigned_bus_id:
                driver.assigned_bus_id = bus_id
                driver.assignment_updated_at = store.utc_now_iso()
            store.save(driver.to_record())
            return driver

    def delete_driver(self, driver_id: str) -> bool:
        """Remove a driver account. False if it doesn't exist."""
        with self._lock:
            if self._drivers.pop(driver_id, None) is None:
                return False
            store.delete(DriverRecord, driver_id)
            return True

    def mark_duty_changed(self, driver_id: str) -> None:
        """The route of this driver's bus changed: show "Changed today" on their duty card."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver:
                driver.assignment_updated_at = store.utc_now_iso()
                store.save(driver.to_record())

    def mark_duty_seen(self, driver_id: str) -> None:
        """The driver opened their duty card: the change notice is read."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver:
                driver.assignment_seen_at = store.utc_now_iso()
                store.save(driver.to_record())

    # =====================================================================
    # Front-end sign-in (one phone at a time)
    # =====================================================================
    def sign_in(self, name_or_id: str, route_id: str, pin: str, session_token: str,
                bus_route_id: str | None, lock_minutes: float) -> DriverUser:
        """
        Sign a driver in with exactly what the admin set up:
          * their name (or username / driver ID) - exact match only
          * their PIN
          * the route of their bus (when they chose one)

        The account is locked to this phone (`session_token`). Another phone is refused
        while the account is in use, unless the first phone has been quiet for `lock_minutes`.
        Raises LoginError with a message for the driver.
        """
        with self._lock:
            driver = self.find_driver(name_or_id)
            if driver is None:
                raise LoginError(say("Driver not found. Please pick your name from the list."))
            if not driver.check_pin(pin):
                raise LoginError(say("Incorrect PIN."))
            if route_id and bus_route_id and route_id != bus_route_id:
                raise LoginError(say("That isn't your route. Please choose the route of your assigned bus."))

            now = datetime.now(UTC)
            if driver.is_logged_in and driver.session_token != session_token:
                last_seen = driver.last_active_at or _parse_iso(driver.last_login_at)
                if last_seen and now - last_seen < timedelta(minutes=lock_minutes):
                    raise LoginError(say(
                        "Account '{name}' is already logged in on another device. Log out there first, or ask the admin to unlock it.",  # noqa: E501
                        name=driver.full_name), status=409)

            driver.session_token = session_token
            driver.last_login_at = now.isoformat()
            driver.last_active_at = now
            store.save(driver.to_record())
            return driver

    def touch(self, driver_id: str, session_token: str | None) -> bool:
        """
        Note activity from the driver's phone (keeps the lock alive).
        False if this phone no longer holds the account (logged out, unlocked, or taken over).
        """
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver is None or not session_token or driver.session_token != session_token:
                return False
            driver.last_active_at = datetime.now(UTC)
            return True

    def sign_out(self, driver_id: str, session_token: str | None) -> None:
        """Free the account, but only if this phone is the one holding it."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver and driver.session_token == session_token:
                self._release(driver)

    def unlock(self, driver_id: str) -> bool:
        """Admin override: free a locked account so the driver can sign in on another phone."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver is None:
                return False
            self._release(driver)
            return True

    @staticmethod
    def _release(driver: DriverUser) -> None:
        """Free the account: forget the phone that held it and save."""
        driver.session_token = None
        driver.last_active_at = None
        store.save(driver.to_record())


def new_session_token() -> str:
    """Random token that identifies one browser session (one phone) for the driver lock."""
    return secrets.token_hex(16)


def _parse_iso(text: str | None) -> datetime | None:
    """A saved ISO date text as a datetime (None if empty or unreadable)."""
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None
