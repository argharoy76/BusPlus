"""
Khulna University Bus Tracker (BusPlus)
Driver and Student User Models & Demo Credentials
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

@dataclass
class DriverUser:
    """Driver account credentials, route assignment, and active session status."""
    driver_id: str
    username: str
    pin: str
    full_name: str
    phone: str
    assigned_route_id: str = "KU-R01"
    assigned_bus_id: str = "KU-BUS-01"
    is_logged_in: bool = False
    current_session_token: Optional[str] = None
    last_login_at: Optional[str] = None
    last_active_at: Optional[str] = None  # last login or GPS update (used to expire a stale lock)
    # Daily duty: when the admin last changed this driver's bus/route, and when the driver last read it
    assignment_updated_at: Optional[str] = None
    assignment_seen_at: Optional[str] = None

    def to_dict(self, include_pin: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if not include_pin:
            data.pop("pin", None)
            data.pop("current_session_token", None)
        return data

@dataclass
class StudentUser:
    """Student profile, default boarding stop, and proximity alert settings."""
    student_id: str
    full_name: str
    department: str
    preferred_route_id: str = "KU-R01"
    preferred_stop_name: str = "Malabotha Bazar"
    alert_lead_minutes: int = 5
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_default_driver_accounts() -> Dict[str, DriverUser]:
    """Default driver accounts for Khulna University."""
    return {
        "DRV-01": DriverUser(
            driver_id="DRV-01",
            username="rafiqul",
            pin="1234",
            full_name="Md. Rafiqul Islam",
            phone="+880 1712-890123",
            assigned_route_id="KU-R01",
            assigned_bus_id="KU-BUS-01",
            is_logged_in=False
        ),
        "DRV-02": DriverUser(
            driver_id="DRV-02",
            username="mannan",
            pin="1234",
            full_name="Abdul Mannan",
            phone="+880 1715-456789",
            assigned_route_id="KU-R02",
            assigned_bus_id="KU-BUS-02",
            is_logged_in=False
        ),
        "DRV-03": DriverUser(
            driver_id="DRV-03",
            username="kamal",
            pin="1234",
            full_name="Kamal Hossain",
            phone="+880 1819-123987",
            assigned_route_id="KU-R03",
            assigned_bus_id="KU-BUS-03",
            is_logged_in=False
        ),
        "DRV-04": DriverUser(
            driver_id="DRV-04",
            username="siraj",
            pin="1234",
            full_name="Siraj Uddin",
            phone="+880 1913-654321",
            assigned_route_id="KU-R01",
            assigned_bus_id="KU-BUS-04",
            is_logged_in=False
        )
    }
