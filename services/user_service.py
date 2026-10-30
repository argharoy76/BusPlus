"""
Khulna University Bus Tracker (BusPlus)
User & Driver Management Service (Authentication, Single-Session Lock, & Admin CRUD)
"""

import hmac
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from models.user import DriverUser, StudentUser, get_default_driver_accounts

class UserService:
    """Singleton service for Driver and Student management with session concurrency control."""

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(UserService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self._drivers: Dict[str, DriverUser] = get_default_driver_accounts()
        self._students: Dict[str, StudentUser] = {
            "KU-2026-0842": StudentUser(
                student_id="KU-2026-0842",
                full_name="Tanvir Ahmed",
                department="Computer Science & Engineering",
                preferred_route_id="KU-R01",
                preferred_stop_name="Malabotha Bazar",
                alert_lead_minutes=5
            ),
            "KU-2026-1102": StudentUser(
                student_id="KU-2026-1102",
                full_name="Sumaiya Rahman",
                department="Business Administration",
                preferred_route_id="KU-R02",
                preferred_stop_name="Shibbari Mor",
                alert_lead_minutes=5
            )
        }
        self._initialized = True

    # -------------------------------------------------------------------------
    # Driver Operations
    # -------------------------------------------------------------------------
    def get_all_drivers(self, include_pin: bool = False) -> List[Dict[str, Any]]:
        """Returns all registered drivers for the backend admin portal."""
        with self._lock:
            return [d.to_dict(include_pin=include_pin) for d in self._drivers.values()]

    def get_driver_by_id(self, driver_id: str) -> Optional[DriverUser]:
        """Finds a driver by their unique ID."""
        with self._lock:
            return self._drivers.get(driver_id)

    def search_drivers(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches drivers by name or username for the frontend autocomplete dropdown.
        Matches as the driver starts typing letters.
        """
        with self._lock:
            q = (query or "").strip().lower()
            matches = []
            for d in self._drivers.values():
                if not q or q in d.full_name.lower() or q in d.username.lower() or q in d.driver_id.lower():
                    matches.append({
                        "driver_id": d.driver_id,
                        "full_name": d.full_name,
                        "assigned_route_id": d.assigned_route_id
                    })
            return matches

    def authenticate_driver(
        self,
        name_or_id: str,
        route_id: str,
        pin: str,
        session_token: str,
        bus_route_id: Optional[str] = None,
        lock_timeout_minutes: float = 10
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Signs a driver in with the details the admin set in the backend:
          - driver name (exact), username or driver ID
          - route (must be the route of the driver's bus, when known)
          - PIN (the driver's own PIN, nothing else)
        One device at a time: another device is refused while the account is in use,
        unless that device has been quiet for lock_timeout_minutes.
        """
        with self._lock:
            target = (name_or_id or "").strip().lower()
            matched: Optional[DriverUser] = None
            for d in self._drivers.values():
                if target and target in (d.driver_id.lower(), d.full_name.lower(), d.username.lower()):
                    matched = d
                    break

            if not matched:
                return False, "Driver not found. Please pick your name from the list.", None

            if not hmac.compare_digest(str(matched.pin), str(pin or "")):
                return False, "Incorrect PIN.", None

            expected_route = bus_route_id or matched.assigned_route_id
            if route_id and expected_route and route_id != expected_route:
                return False, "That isn't your route. Please choose the route of your assigned bus.", None

            now = datetime.now(timezone.utc)
            if matched.is_logged_in and matched.current_session_token != session_token:
                last = None
                try:
                    last = datetime.fromisoformat(matched.last_active_at) if matched.last_active_at else None
                except ValueError:
                    last = None
                still_in_use = last is None or (now - last) < timedelta(minutes=lock_timeout_minutes)
                if still_in_use:
                    return (
                        False,
                        f"Account '{matched.full_name}' is already logged in on another device. "
                        "Log out there first, or ask the admin to unlock it.",
                        None
                    )

            matched.is_logged_in = True
            matched.current_session_token = session_token
            matched.last_login_at = now.isoformat()
            matched.last_active_at = now.isoformat()
            if expected_route:
                matched.assigned_route_id = expected_route

            return True, "Login successful.", matched.to_dict()

    # -------------------------------------------------------------------------
    # Daily duty (bus + route) notifications
    # -------------------------------------------------------------------------
    def mark_assignment_changed(self, driver_id: str) -> None:
        """Called when the admin changes a driver's bus, or the route of that bus."""
        with self._lock:
            d = self._drivers.get(driver_id)
            if d:
                d.assignment_updated_at = datetime.now(timezone.utc).isoformat()

    def mark_assignment_seen(self, driver_id: str) -> None:
        with self._lock:
            d = self._drivers.get(driver_id)
            if d:
                d.assignment_seen_at = datetime.now(timezone.utc).isoformat()

    def touch_driver(self, driver_id: str, session_token: Optional[str]) -> bool:
        """Records activity from the driver's device. False if this device no longer holds the account."""
        with self._lock:
            d = self._drivers.get(driver_id)
            if not d or not d.is_logged_in or d.current_session_token != session_token:
                return False
            d.last_active_at = datetime.now(timezone.utc).isoformat()
            return True

    def logout_driver(self, driver_id: str, session_token: Optional[str] = None) -> bool:
        """Frees the driver session lock upon logout (only for the device that holds it)."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver and (session_token is None or driver.current_session_token in (None, session_token)):
                driver.is_logged_in = False
                driver.current_session_token = None
                return True
            return False

    def unlock_driver_session(self, driver_id: str) -> bool:
        """Admin override to force-unlock a locked driver account."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if driver:
                driver.is_logged_in = False
                driver.current_session_token = None
                return True
            return False

    def update_driver(self, driver_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates driver details from the backend admin portal."""
        with self._lock:
            driver = self._drivers.get(driver_id)
            if not driver:
                return None

            if "full_name" in data and data["full_name"]:
                driver.full_name = data["full_name"].strip()
            if "phone" in data and data["phone"] is not None:
                driver.phone = str(data["phone"]).strip()
            if "assigned_route_id" in data and data["assigned_route_id"]:
                driver.assigned_route_id = data["assigned_route_id"]
            if "assigned_bus_id" in data and data["assigned_bus_id"]:
                driver.assigned_bus_id = data["assigned_bus_id"]
            if "pin" in data and data["pin"]:
                driver.pin = str(data["pin"]).strip()
            if "is_logged_in" in data:
                driver.is_logged_in = bool(data["is_logged_in"])
                if not driver.is_logged_in:
                    driver.current_session_token = None

            return driver.to_dict(include_pin=True)

    def create_driver(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new driver record from backend admin."""
        with self._lock:
            n = 1
            while f"DRV-{n:02d}" in self._drivers:   # never reuse/overwrite an existing ID
                n += 1
            new_id = f"DRV-{n:02d}"
            username = str(data.get("username") or new_id.lower().replace("-", "")).strip()
            driver = DriverUser(
                driver_id=new_id,
                username=username,
                pin=str(data.get("pin") or "").strip(),
                full_name=str(data.get("full_name") or f"Driver {new_id}").strip(),
                phone=str(data.get("phone") or "").strip(),
                assigned_route_id=data.get("assigned_route_id", "KU-R01"),
                assigned_bus_id=data.get("assigned_bus_id", "KU-BUS-01"),
                is_logged_in=False
            )
            self._drivers[driver.driver_id] = driver
            return driver.to_dict(include_pin=True)

    def delete_driver(self, driver_id: str) -> bool:
        """Deletes a driver record from backend admin."""
        with self._lock:
            if driver_id in self._drivers:
                del self._drivers[driver_id]
                return True
            return False

    # -------------------------------------------------------------------------
    # Student Operations (for Student Setup Sidebar)
    # -------------------------------------------------------------------------
    def get_all_students(self) -> List[Dict[str, Any]]:
        """Returns all registered students for student setup."""
        with self._lock:
            return [s.to_dict() for s in self._students.values()]

    def update_student(self, student_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Updates student details from the backend admin portal."""
        with self._lock:
            student = self._students.get(student_id)
            if not student:
                # If creating or saving guest as registered
                student = StudentUser(
                    student_id=student_id,
                    full_name=data.get("full_name", "KU Student"),
                    department=data.get("department", "CSE"),
                    preferred_route_id=data.get("preferred_route_id", "KU-R01"),
                    preferred_stop_name=data.get("preferred_stop_name", "Malabotha Bazar"),
                    alert_lead_minutes=int(data.get("alert_lead_minutes", 5))
                )
                self._students[student_id] = student
                return student.to_dict()

            if "full_name" in data:
                student.full_name = data["full_name"]
            if "department" in data:
                student.department = data["department"]
            if "preferred_route_id" in data:
                student.preferred_route_id = data["preferred_route_id"]
            if "preferred_stop_name" in data:
                student.preferred_stop_name = data["preferred_stop_name"]
            if "alert_lead_minutes" in data:
                student.alert_lead_minutes = int(data["alert_lead_minutes"])

            return student.to_dict()
