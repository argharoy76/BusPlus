"""
Shared test setup (pytest fixtures).

Every test gets a brand-new app with an empty in-memory database that is filled
with the built-in routes, buses and the 4 demo drivers (PIN 1234).
"""

import pytest

from app import create_app
from config import TestConfig
from services import tracking, users


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
def driver_login(app):
    """Function that signs a new browser in as a driver: driver_login(name, route, pin) -> (browser, response)."""
    def login(name="Md. Rafiqul Islam", route_id="KU-R01", pin="1234"):
        browser = app.test_client()
        resp = browser.post("/api/auth/driver/login", json={"driver_name": name, "route_id": route_id, "pin": pin})
        return browser, resp
    return login


@pytest.fixture
def services():
    """The live services, for setting up situations directly (e.g. a bus at a given place)."""
    return tracking, users
