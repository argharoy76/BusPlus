"""
Background GPS with the Traccar Client app: /api/tracker in both request styles.
"""

import time
from datetime import UTC, datetime

from services import tracking


def _key(admin, driver_id="DRV-01"):
    reply = admin.post(f"/api/admin/drivers/{driver_id}/tracker", json={}).get_json()
    assert reply["success"] and reply["server_url"].endswith("/api/tracker")
    return reply["key"]


def test_tracker_key_is_stable_and_renewable(admin):
    key = _key(admin)
    assert _key(admin) == key
    new = admin.post("/api/admin/drivers/DRV-01/tracker", json={"renew": True}).get_json()["key"]
    assert new != key


def test_query_style_position_moves_the_bus(admin, client, app):
    key = _key(admin)
    reply = client.post(f"/api/tracker?id={key}&lat=22.7725&lon=89.5855&timestamp={int(time.time())}"
                        "&speed=10&bearing=90&accuracy=6")
    assert reply.status_code == 200
    with app.app_context():
        bus = tracking.get_bus("KU-BUS-01")
        assert bus.is_active and abs(bus.current_latitude - 22.7725) < 0.001


def test_json_style_position_moves_the_bus(admin, client, app):
    key = _key(admin, "DRV-02")
    body = {"device_id": key, "location": {
        "timestamp": datetime.now(UTC).isoformat(),
        "coords": {"latitude": 22.80, "longitude": 89.53, "speed": 5.0, "heading": 180, "accuracy": 5}}}
    assert client.post("/api/tracker", json=body).status_code == 200
    with app.app_context():
        assert tracking.get_bus("KU-BUS-02").is_active


def test_unknown_key_and_bad_position_are_refused(client):
    assert client.get("/api/tracker?id=nope&lat=22.8&lon=89.5").status_code == 403
    assert client.get("/api/tracker?id=nope").status_code == 400


def test_old_saved_positions_are_not_shown_live(admin, client, app):
    key = _key(admin, "DRV-03")
    client.get(f"/api/tracker?id={key}&lat=22.80&lon=89.53&timestamp={int(time.time()) - 3600}")
    with app.app_context():
        assert not tracking.get_bus("KU-BUS-03").is_active
