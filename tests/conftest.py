"""
Shared test setup (pytest fixtures).

Every test gets a brand-new app with an empty in-memory database that is filled
with the built-in routes and buses.
"""

import pytest

from app import create_app
from config import TestConfig
from services import devices, tracking


@pytest.fixture
def app():
    application = create_app(TestConfig)
    yield application
    for bus in tracking.all_buses():          # stop any test drive still running in the background
        tracking.stop_trip(bus["bus_id"])


@pytest.fixture
def client(app):
    """A browser that is not signed in."""
    return app.test_client()


@pytest.fixture
def admin(app):
    """A browser signed in to the backend as the admin."""
    browser = app.test_client()
    resp = browser.post("/api/auth/admin/login",
                        json={"username": TestConfig.ADMIN_USERNAME, "password": TestConfig.ADMIN_PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    return browser


@pytest.fixture
def add_device(admin):
    """Function that adds a GPS device in the backend: add_device(name, bus_id) -> its secret key."""
    def add(name="Tracker in Bus #01", bus_id="KU-BUS-01"):
        resp = admin.post("/api/admin/devices", json={"name": name, "bus_id": bus_id})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["settings"]["key"]
    return add


@pytest.fixture
def gps_box(app, add_device):
    """
    A GPS box (ESP32 + NEO-6M) fitted to KU-BUS-01: gps_box(**report) POSTs one report like the
    firmware does and returns the response. gps_box.key is its secret key.
    """
    key = add_device()
    browser = app.test_client()

    def send(key_override=None, **report):
        body = {"fix": True, "sats": 8, "hdop": 1.0, "age_ms": 200, **report}
        return browser.post("/api/device/location", json=body, headers={"X-Device-Key": key_override or key})
    send.key = key
    return send


@pytest.fixture
def services():
    """The live services, for setting up situations directly (e.g. a bus at a given place)."""
    return tracking, devices
