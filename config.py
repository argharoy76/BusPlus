"""
BusPlus settings.

Everything that changes between your computer and the live server is read from
environment variables. On the server they live in a `.env` file next to this one
(copy `.env.example` to `.env` and fill it in). `.env` is never committed to Git.

Settings that are the same everywhere (the university, the final stop of every
route, timings) are plain constants at the bottom of the `Config` class.
"""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from content import map_settings, rules, site_text

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"          # database + local secrets (ignored by Git)
INSTANCE_DIR.mkdir(exist_ok=True)

# Read KEY=value lines from .env into the environment (real environment variables win).
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read an on/off environment variable such as `true`, `1`, `yes`, `false`, `0`."""
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _local_secret(file_name: str, length: int = 32) -> str:
    """
    Development helper: return a random secret kept in instance/<file_name>.

    The first call creates the file, later calls reuse it, so sessions and the
    admin password survive restarts on your own computer. Production never uses
    this - it must set real values in `.env` (checked in `Config.check_production`).
    """
    path = INSTANCE_DIR / file_name
    if path.exists():
        saved = path.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    value = secrets.token_urlsafe(length)
    path.write_text(value + "\n", encoding="utf-8")
    return value


class Config:
    """Flask settings and BusPlus constants. `create_app()` loads this class."""

    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    # "production" on the live server, "development" on your computer.
    ENV_NAME = os.environ.get("BUSPLUS_ENV", "development").strip().lower()
    IS_PRODUCTION = ENV_NAME == "production"
    DEBUG = env_bool("FLASK_DEBUG", False) and not IS_PRODUCTION
    TESTING = False

    # Where `python app.py` listens (production uses gunicorn instead, see gunicorn.conf.py).
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = int(os.environ.get("PORT", "5000"))

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # Signs the session cookie. Must be a long random value in production.
    SECRET_KEY = os.environ.get("SECRET_KEY") or (None if IS_PRODUCTION else _local_secret("secret_key.txt"))

    # Backend (/backend) admin login.
    ADMIN_USERNAME = os.environ.get("BUSPLUS_ADMIN_USERNAME", "admin").strip() or "admin"
    ADMIN_PASSWORD = os.environ.get("BUSPLUS_ADMIN_PASSWORD") or (
        None if IS_PRODUCTION else _local_secret("admin_password.txt", 9)
    )

    # Session cookie: not readable by JavaScript, not sent by other sites, HTTPS-only in production.
    SESSION_COOKIE_NAME = "busplus_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = timedelta(days=180)   # students/teachers stay signed in

    # Flask-WTF CSRF protection: every POST/PUT/DELETE must carry the page's token.
    # No time limit, because a driver's map page stays open for a whole shift.
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_SSL_STRICT = IS_PRODUCTION

    # Flask-Limiter: login attempt limits are kept in memory (one server process).
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True

    # Flask-Talisman: redirect http:// to https:// in production (nginx terminates HTTPS).
    FORCE_HTTPS = env_bool("FORCE_HTTPS", IS_PRODUCTION)

    # How many reverse proxies (nginx) sit in front of the app. Lets Flask see the
    # visitor's real IP and https scheme. Use 0 when nothing is in front.
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "1" if IS_PRODUCTION else "0"))

    # Largest request body accepted (a long route line is the biggest thing we receive).
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # ------------------------------------------------------------------
    # Database (Flask-SQLAlchemy). SQLite file in instance/ unless DATABASE_URL is set.
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{INSTANCE_DIR / 'busplus.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # On first start with an empty database, also create 4 demo drivers (PIN 1234).
    # Handy on your computer; keep it off on the live server.
    SEED_DEMO_DRIVERS = env_bool("BUSPLUS_DEMO_DRIVERS", not IS_PRODUCTION)

    # ------------------------------------------------------------------
    # BusPlus constants - edit them in the content/ folder, not here.
    # ------------------------------------------------------------------
    UNIVERSITY_NAME = site_text.UNIVERSITY_NAME
    UNIVERSITY_LOCATION = map_settings.MAP_CENTER          # map centre before any bus/home is known
    FINAL_DESTINATION = map_settings.FINAL_DESTINATION     # last stop of every route (Hadi Chattar)
    TIMEZONE = map_settings.TIMEZONE
    DRIVER_SESSION_TIMEOUT_MINUTES = rules.DRIVER_LOCK_MINUTES
    DEFAULT_ALERT_MINUTES = rules.DEFAULT_ALERT_MINUTES

    # Road router used by the route editor to snap a route to real roads (OpenStreetMap data).
    ROAD_ROUTER_URL = os.environ.get("ROAD_ROUTER_URL", "https://router.project-osrm.org/route/v1/driving/")

    @classmethod
    def check_production(cls) -> None:
        """Stop the server from starting in production with missing or weak secrets."""
        if not cls.IS_PRODUCTION:
            return
        problems = []
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be set to a random value of at least 32 characters.")
        if not cls.ADMIN_PASSWORD or len(cls.ADMIN_PASSWORD) < 10:
            problems.append("BUSPLUS_ADMIN_PASSWORD must be set (at least 10 characters).")
        if problems:
            raise RuntimeError("BusPlus is not configured for production:\n  - " + "\n  - ".join(problems))


class TestConfig(Config):
    """Settings for the automated tests: throw-away in-memory database, no CSRF/HTTPS checks."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    ADMIN_PASSWORD = "test-admin-password"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SEED_DEMO_DRIVERS = True
    WTF_CSRF_ENABLED = False
    FORCE_HTTPS = False
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False
