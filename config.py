"""
Khulna University Bus Tracker (BusPlus)
Application Configuration & Constant Settings
"""

import os
import secrets

INSTANCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
ADMIN_PASSWORD_FILE = os.path.join(INSTANCE_DIR, "admin_password.txt")


def _load_admin_password() -> str:
    """
    Admin password for the /backend panel:
      1. BUSPLUS_ADMIN_PASSWORD environment variable, if set
      2. otherwise instance/admin_password.txt (created once with a random password)
    """
    from_env = os.environ.get("BUSPLUS_ADMIN_PASSWORD", "").strip()
    if from_env:
        return from_env
    try:
        with open(ADMIN_PASSWORD_FILE, encoding="utf-8") as fh:
            saved = fh.read().strip()
            if saved:
                return saved
    except FileNotFoundError:
        pass
    generated = secrets.token_urlsafe(9)
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    with open(ADMIN_PASSWORD_FILE, "w", encoding="utf-8") as fh:
        fh.write(generated + "\n")
    return generated


class AppConfig:
    # Flask settings
    SECRET_KEY = os.environ.get("SECRET_KEY", "khulna_university_busplus_secret_2026")
    DEBUG = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "yes")
    PORT = int(os.environ.get("PORT", 5000))
    HOST = os.environ.get("HOST", "0.0.0.0")

    # Backend admin panel login (drivers and students can't sign in here)
    ADMIN_USERNAME = os.environ.get("BUSPLUS_ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = _load_admin_password()

    # A driver account stays locked to one device while in use. If that device
    # goes quiet (no login / GPS update) for this long, the driver can sign in again elsewhere.
    DRIVER_SESSION_TIMEOUT_MINUTES = 10

    # Local time for "today" (driver duty notifications). Bangladesh has no daylight saving.
    LOCAL_UTC_OFFSET_HOURS = 6

    # University Information
    UNIVERSITY_NAME = "Khulna University"
    UNIVERSITY_SHORT_NAME = "KU"
    UNIVERSITY_LOCATION = {
        "name": "Khulna University Main Campus",
        "latitude": 22.8010,
        "longitude": 89.5345,
        "address": "Sher-e-Bangla Rd, Gollamari, Khulna 9208, Bangladesh"
    }

    # Final destination of EVERY KU bus route (KU Hadi Chattar).
    # All routes end here; change it in one place to move the end point for all buses.
    FINAL_DESTINATION = {
        "stop_name": "Hadi Chattar",
        "latitude": 22.80209,
        "longitude": 89.53398,
        "landmark_hint": "Khulna University · Hadi Chattar"
    }

    # Google Maps API Configuration
    # Defaults to empty string or environment variable.
    # Users can set GOOGLE_MAPS_API_KEY environment variable or enter it directly in the UI.
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    # Default Notification Threshold (in minutes)
    DEFAULT_ALERT_MINUTES_THRESHOLD = 5

    # Average Bus Speed in City Traffic (km/h) for fallback ETA calculations
    AVERAGE_BUS_SPEED_KMH = 26.0

    # Default Refresh Interval for student client polling in milliseconds
    POLLING_INTERVAL_MS = 3000
