"""
Khulna University Bus Tracker (BusPlus)
Bus Entity and Live Tracking State Model
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, Optional

@dataclass
class Bus:
    """Represents a university bus vehicle and its real-time telemetry."""
    bus_id: str
    bus_number: str
    bus_name: str
    license_plate: str
    assigned_route_id: str
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    current_latitude: float = 22.8010
    current_longitude: float = 89.5345
    speed_kmh: float = 0.0
    heading_deg: float = 0.0
    is_active: bool = False
    is_simulating: bool = False
    last_updated_iso: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    current_stop_index: int = 0
    next_stop_name: str = "Khulna University"
    estimated_next_stop_minutes: float = 0.0
    trip_status: str = "IDLE"  # IDLE, EN_ROUTE, APPROACHING, STOPPED, COMPLETED
    capacity: int = 52
    occupancy_level: str = "Seats Available"
    color_hex: str = "#0866FF"  # Bus's own marker colour on the student map
    audience: str = "student"   # who rides it: "student" or "teacher" (each only sees their own buses)

    def update_telemetry(
        self,
        latitude: float,
        longitude: float,
        speed_kmh: Optional[float] = None,
        heading_deg: Optional[float] = None,
        trip_status: Optional[str] = None
    ) -> None:
        """Updates real-time GPS coordinates and metadata."""
        self.current_latitude = float(latitude)
        self.current_longitude = float(longitude)
        if speed_kmh is not None:
            self.speed_kmh = max(0.0, float(speed_kmh))
        if heading_deg is not None:
            self.heading_deg = float(heading_deg) % 360.0
        if trip_status is not None:
            self.trip_status = trip_status
        self.is_active = True
        self.last_updated_iso = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes bus status into JSON-compatible dictionary."""
        return asdict(self)


def get_default_khulna_university_buses() -> Dict[str, Bus]:
    """Returns the fleet of official Khulna University buses."""
    fleet: Dict[str, Bus] = {}

    # Bus 1: Dedicated to Route 1 (Malabotha - Rupsha - KU Line)
    b1 = Bus(
        bus_id="KU-BUS-01",
        color_hex="#E11D48",
        bus_number="KU Bus #01",
        bus_name="Khan Jahan Ali Express",
        license_plate="Khulna-Cha 11-2041",
        assigned_route_id="KU-R01",
        driver_id="DRV-01",
        driver_name="Md. Rafiqul Islam",
        driver_phone="+880 1712-890123",
        current_latitude=22.7725,  # Initially parked at Malabotha
        current_longitude=89.5855,
        speed_kmh=0.0,
        heading_deg=315.0,
        is_active=False,
        trip_status="IDLE",
        next_stop_name="Malabotha Bazar",
        capacity=52,
        occupancy_level="Seats Available"
    )
    fleet[b1.bus_id] = b1

    # Bus 2: Dedicated to Route 2 (Phultala - Daulatpur - Shibbari - KU Line)
    b2 = Bus(
        bus_id="KU-BUS-02",
        color_hex="#0891B2",
        bus_number="KU Bus #02",
        bus_name="Sundarban Pioneer",
        license_plate="Khulna-Cha 11-3052",
        assigned_route_id="KU-R02",
        driver_id="DRV-02",
        driver_name="Abdul Mannan",
        driver_phone="+880 1715-456789",
        current_latitude=22.9780,  # Initially parked at Phultala
        current_longitude=89.4620,
        speed_kmh=0.0,
        heading_deg=180.0,
        is_active=False,
        trip_status="IDLE",
        next_stop_name="Phultala Super Market",
        capacity=52,
        occupancy_level="Seats Available"
    )
    fleet[b2.bus_id] = b2

    # Bus 3: Dedicated to Route 3 (Dumuria - Zero Point - KU Line)
    b3 = Bus(
        bus_id="KU-BUS-03",
        color_hex="#EA580C",
        bus_number="KU Bus #03",
        bus_name="Moyur Express",
        license_plate="Khulna-Cha 11-4019",
        assigned_route_id="KU-R03",
        driver_id="DRV-03",
        driver_name="Kamal Hossain",
        driver_phone="+880 1819-123987",
        current_latitude=22.8105,  # Dumuria
        current_longitude=89.4250,
        speed_kmh=0.0,
        heading_deg=90.0,
        is_active=False,
        trip_status="IDLE",
        next_stop_name="Dumuria Hospital Mor",
        capacity=52,
        occupancy_level="Seats Available"
    )
    fleet[b3.bus_id] = b3

    # Bus 4: Campus Shuttle (Campus - Zero Point - Gollamari Loop)
    b4 = Bus(
        bus_id="KU-BUS-04",
        color_hex="#7C3AED",
        bus_number="KU Bus #04",
        bus_name="Bhairab Shuttle",
        license_plate="Khulna-Cha 11-5088",
        assigned_route_id="KU-R01",
        driver_id="DRV-04",
        driver_name="Siraj Uddin",
        driver_phone="+880 1913-654321",
        current_latitude=22.8090,  # Gollamari
        current_longitude=89.5398,
        speed_kmh=0.0,
        heading_deg=220.0,
        is_active=False,
        trip_status="IDLE",
        next_stop_name="Gollamari Mor",
        capacity=40,
        occupancy_level="Seats Available"
    )
    fleet[b4.bus_id] = b4

    return fleet
