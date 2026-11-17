"""
BusPlus automated tests. Run them with:  pytest
"""

import json
import threading
import time
from unittest import mock

import services.tracking_service as tracking_module
from app import create_app
from config import Config, TestConfig
from services import devices, geo

DEST = Config.FINAL_DESTINATION


def buses_by_id(browser, audience=None):
    url = "/api/buses" + (f"?audience={audience}" if audience else "")
    return {b["bus_id"]: b for b in browser.get(url).get_json()["buses"]}


# ---------------------------------------------------------------------------
# Map maths
# ---------------------------------------------------------------------------
def test_distance_malabotha_to_campus():
    assert 5.0 < geo.distance_km(22.7725, 89.5855, 22.8010, 89.5345) < 9.0


def test_eta_is_longer_for_more_stops():
    near = geo.estimate_eta(22.78, 89.58, 22.80, 89.53)
    with_stops = geo.estimate_eta(22.78, 89.58, 22.80, 89.53, stops_between=3)
    assert with_stops["eta_minutes"] == round(near["eta_minutes"] + 4.5, 1)


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
def test_backend_is_admin_only(client, gps_box):
    assert client.get("/backend").status_code == 302
    assert "/backend/login" in client.get("/backend").headers["Location"]
    assert client.post("/api/admin/buses", json={"bus_number": "X"}).status_code == 401
    assert client.post("/api/auth/admin/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.get("/backend/login").status_code == 200
    assert client.get("/api/admin/devices").status_code == 401
    # A GPS box's key opens nothing but its own report endpoint
    headers = {"X-Device-Key": gps_box.key}
    assert client.get("/api/admin/devices", headers=headers).status_code == 401
    assert client.post("/api/admin/devices", json={"name": "x"}, headers=headers).status_code == 401


def test_csrf_token_required_outside_tests():
    """With CSRF on (the real setting), a POST without the page's token is refused."""
    class CsrfOn(TestConfig):
        WTF_CSRF_ENABLED = True
    browser = create_app(CsrfOn).test_client()
    resp = browser.post("/api/auth/student/login", json={"full_name": "A", "student_id": "1"})
    assert resp.status_code == 400
    assert "expired" in resp.get_json()["message"]


def test_login_rate_limit():
    class LimitsOn(TestConfig):
        RATELIMIT_ENABLED = True
    browser = create_app(LimitsOn).test_client()
    codes = [browser.post("/api/auth/admin/login", json={"username": "admin", "password": "x"}).status_code
             for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


def test_security_headers(client):
    headers = client.get("/").headers
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["X-Content-Type-Options"] == "nosniff"


def test_production_refuses_missing_secrets():
    class Production(Config):
        IS_PRODUCTION = True
        SECRET_KEY = None
        ADMIN_PASSWORD = None
    try:
        Production.check_production()
    except RuntimeError as err:
        assert "SECRET_KEY" in str(err) and "BUSPLUS_ADMIN_PASSWORD" in str(err)
    else:
        raise AssertionError("production started without secrets")


def test_device_keys_are_hashed_and_shown_once(admin, add_device, services):
    _, devices = services
    key = add_device()
    device = devices.get("GPS-01")
    assert device.key_hash and key not in device.key_hash and device.key_hint == key[-4:]
    listing = json.dumps(admin.get("/api/admin/devices").get_json())
    assert key not in listing and device.key_hash not in listing
    assert key not in admin.get("/backend").get_data(as_text=True)
    assert key not in json.dumps(admin.get("/api/buses").get_json())


# ---------------------------------------------------------------------------
# GPS devices (ESP32 + NEO-6M)
# ---------------------------------------------------------------------------
def test_device_setup_in_the_backend(admin, add_device, services):
    _, devices = services
    resp = admin.post("/api/admin/devices", json={"name": "Box 1", "bus_id": "KU-BUS-01"})
    settings = resp.get_json()["settings"]
    assert resp.get_json()["device"]["device_id"] == "GPS-01"
    assert settings["server_url"].endswith("/api/device/location") and len(settings["key"]) == 24
    assert settings["send_every_s"] > 0

    assert admin.post("/api/admin/devices", json={"name": "", "bus_id": "KU-BUS-02"}).status_code == 400
    assert admin.post("/api/admin/devices", json={"name": "X", "bus_id": "NOPE"}).status_code == 400
    # One device per bus
    resp = admin.post("/api/admin/devices", json={"name": "Box 2", "bus_id": "KU-BUS-01"})
    assert resp.status_code == 400 and "Box 1" in resp.get_json()["message"]
    # A device may wait in the drawer without a bus
    assert admin.post("/api/admin/devices", json={"name": "Spare", "bus_id": ""}).status_code == 200
    assert devices.get("GPS-02").bus_id is None

    resp = admin.put("/api/admin/devices/GPS-02", json={"bus_id": "KU-BUS-02", "name": "Box 2"})
    assert resp.get_json()["device"]["bus_id"] == "KU-BUS-02" and devices.get("GPS-02").name == "Box 2"
    assert admin.put("/api/admin/devices/GPS-99", json={"name": "x"}).status_code == 404
    assert admin.delete("/api/admin/devices/GPS-02").status_code == 200
    assert devices.get("GPS-02") is None


def test_device_moves_only_its_own_bus_and_leaves_trail(client, gps_box):
    for lat in (22.7725, 22.7760, 22.7800):
        resp = gps_box(lat=lat, lng=89.584, speed_kmh=25, course=0, bus_id="KU-BUS-02")
        assert resp.status_code == 200
        # the bus comes from the device's setup: a bus_id in the report is ignored
        assert resp.get_json() == {"ok": True, "bus_id": "KU-BUS-01", "send_every_s": 2, "on_map": True}
    buses = buses_by_id(client)
    assert buses["KU-BUS-01"]["is_active"] and len(buses["KU-BUS-01"]["trail"]) >= 3
    assert not buses["KU-BUS-02"]["is_active"]


def test_device_without_fix_is_connected_but_bus_stays_offline(admin, client, gps_box):
    resp = gps_box(fix=False, sats=2, rssi=-71, battery_v=12.6, fw="1.0.0")
    assert resp.status_code == 200
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]
    device = admin.get("/api/admin/devices").get_json()["devices"][0]
    assert device["status"] == "no_fix"
    health = (device["satellites"], device["rssi_dbm"], device["battery_v"], device["firmware"])
    assert health == (2, -71, 12.6, "1.0.0")

    gps_box(lat=22.7725, lng=89.5857, speed_kmh=0)
    assert buses_by_id(client)["KU-BUS-01"]["is_active"]
    assert admin.get("/api/admin/devices").get_json()["devices"][0]["status"] == "online"


def test_device_reports_are_checked(admin, client, gps_box):
    no_key = client.post("/api/device/location", json={"lat": 22.8, "lng": 89.5})
    assert no_key.status_code == 401 and no_key.get_json()["ok"] is False
    assert gps_box(key_override="wrong-key", lat=22.8, lng=89.5).status_code == 401
    assert gps_box(lat="abc", lng=89.5).status_code == 400
    assert gps_box(lat=95, lng=89.5).status_code == 400
    assert gps_box(lat=0, lng=0).status_code == 400                       # NEO-6M before its first fix
    assert client.post("/api/device/location", data="not json",
                       headers={"X-Device-Key": gps_box.key}).status_code == 400
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]

    # Odd numbers are dropped instead of breaking every map (JSON has no NaN / Infinity)
    resp = gps_box(lat=22.7725, lng=89.5857, speed_kmh=float("inf"), course=float("nan"), hdop="x")
    assert resp.status_code == 200
    text = client.get("/api/buses").get_data(as_text=True)
    assert "NaN" not in text and "Infinity" not in text

    # A position the box kept for minutes (e.g. while offline) is not shown as live
    gps_box(lat=22.80, lng=89.55, age_ms=10 * 60 * 1000)
    assert round(buses_by_id(client)["KU-BUS-01"]["current_latitude"], 2) != 22.80

    # Bearer token works too
    resp = client.post("/api/device/location", json={"lat": 22.7726, "lng": 89.5858},
                       headers={"Authorization": f"Bearer {gps_box.key}"})
    assert resp.status_code == 200


def test_device_not_fitted_to_a_bus_is_told_so(admin, client, gps_box):
    assert admin.put("/api/admin/devices/GPS-01", json={"bus_id": ""}).status_code == 200
    resp = gps_box(lat=22.7725, lng=89.5857)
    assert resp.status_code == 409 and "backend" in resp.get_json()["error"]
    assert admin.get("/api/admin/devices").get_json()["devices"][0]["reports"] == 1


def test_new_key_or_delete_stops_the_old_key(admin, client, gps_box):
    assert gps_box(lat=22.7725, lng=89.5857).status_code == 200
    new_key = admin.post("/api/admin/devices/GPS-01/key").get_json()["settings"]["key"]
    assert new_key != gps_box.key
    assert gps_box(lat=22.7725, lng=89.5857).status_code == 401
    assert gps_box(key_override=new_key, lat=22.7725, lng=89.5857).status_code == 200
    assert admin.delete("/api/admin/devices/GPS-01").status_code == 200
    assert gps_box(key_override=new_key, lat=22.7725, lng=89.5857).status_code == 401
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]             # its bus went offline


def test_moving_a_device_takes_its_old_bus_offline(admin, client, gps_box):
    gps_box(lat=22.7725, lng=89.5857)
    assert buses_by_id(client)["KU-BUS-01"]["is_active"]
    assert admin.put("/api/admin/devices/GPS-01", json={"bus_id": "KU-BUS-02"}).status_code == 200
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]
    assert gps_box(lat=22.9784, lng=89.4626).get_json()["bus_id"] == "KU-BUS-02"
    assert buses_by_id(client)["KU-BUS-02"]["is_active"]


def test_device_rate_limit_is_per_key():
    class LimitsOn(TestConfig):
        RATELIMIT_ENABLED = True
    app = create_app(LimitsOn)
    admin = app.test_client()
    admin.post("/api/auth/admin/login", json={"username": "admin", "password": TestConfig.ADMIN_PASSWORD})
    key1 = admin.post("/api/admin/devices", json={"name": "A", "bus_id": "KU-BUS-01"}).get_json()["settings"]["key"]
    key2 = admin.post("/api/admin/devices", json={"name": "B", "bus_id": "KU-BUS-02"}).get_json()["settings"]["key"]
    box = app.test_client()
    codes = [box.post("/api/device/location", json={"fix": False}, headers={"X-Device-Key": key1}).status_code
             for _ in range(130)]
    assert codes[0] == 200 and codes[-1] == 429                 # content/rules.py: DEVICE_LIMIT (120 per minute)
    # Another bus behind the same mobile-network IP address still gets through
    assert box.post("/api/device/location", json={"fix": False}, headers={"X-Device-Key": key2}).status_code == 200


def test_real_gps_ends_a_test_drive(admin, client, gps_box, services):
    tracking, _ = services
    real_sleep = time.sleep
    with mock.patch.object(tracking_module.time, "sleep", lambda *_: real_sleep(0.01)):
        assert admin.post("/api/admin/buses/KU-BUS-01/simulate").get_json()["simulating"]
        gps_box(lat=22.7725, lng=89.5857)
        tracking._simulation_threads["KU-BUS-01"].join(timeout=10)
    bus = tracking.get_bus("KU-BUS-01")
    assert bus.is_active and not bus.is_simulating


# ---------------------------------------------------------------------------
# Routes and buses (backend)
# ---------------------------------------------------------------------------
def test_route_management(admin, client):
    road = [[22.7840, 89.5780], [22.7900, 89.5700], [22.8000, 89.5500], [22.80209, 89.53398]]
    resp = admin.post("/api/admin/routes", json={
        "route_name": "Rupsha - Hadi Chattar",
        "points": [{"lat": 22.7840, "lng": 89.5780, "name": "Rupsha"}, {"lat": 22.7900, "lng": 89.5700}],
        "path": road})
    assert resp.status_code == 200, resp.get_json()
    route = resp.get_json()["route"]
    assert [s["stop_name"] for s in route["stops"]] == ["Rupsha", DEST["stop_name"]]   # unnamed points aren't stops
    assert [[p["lat"], p["lng"]] for p in route["polyline_waypoints"]][:3] == road[:3]
    assert len(route["via_points"]) == 2 and route["length_km"] > 2
    assert route["route_id"] in [r["route_id"] for r in client.get("/api/routes").get_json()["routes"]]

    assert admin.post("/api/admin/routes", json={"route_name": "X", "points": []}).status_code == 400
    assert admin.post("/api/admin/routes", json={"route_name": "X", "points": [{"name": "A"}]}).status_code == 400
    assert admin.post("/api/admin/routes", json={"route_name": "Bad", "points": [{"lat": 22.78, "lng": 89.57}],
                                                 "path": [[0, 0], [1, 1]]}).status_code == 400

    resp = admin.put(f"/api/admin/routes/{route['route_id']}", json={"route_name": "Rupsha Express"})
    assert resp.get_json()["route"]["route_name"] == "Rupsha Express"
    assert admin.delete("/api/admin/routes/KU-R01").status_code == 400      # buses still use it
    assert admin.delete(f"/api/admin/routes/{route['route_id']}").status_code == 200


def test_every_route_ends_at_hadi_chattar(client):
    routes = client.get("/api/routes").get_json()["routes"]
    assert len(routes) >= 3
    for route in routes:
        last = route["stops"][-1]
        assert (last["stop_name"], last["latitude"], last["longitude"]) == \
               (DEST["stop_name"], DEST["latitude"], DEST["longitude"])
        points = route["polyline_waypoints"]
        assert points[-1] == {"lat": DEST["latitude"], "lng": DEST["longitude"]}

        def to_dest(p):
            return geo.distance_km(p["lat"], p["lng"], DEST["latitude"], DEST["longitude"])
        assert to_dest(points[-2]) <= to_dest(points[-3]), f"{route['route_id']} overshoots Hadi Chattar"


def test_bus_management(admin, client, services):
    tracking, _ = services
    resp = admin.post("/api/admin/buses", json={"bus_number": "KU Bus #05", "bus_name": "Rupsha Express",
                                                "assigned_route_id": "KU-R01", "capacity": 40})
    assert resp.status_code == 200, resp.get_json()
    bus_id = resp.get_json()["bus"]["bus_id"]
    assert bus_id == "KU-BUS-05" and bus_id in buses_by_id(client)

    assert admin.post("/api/admin/buses", json={"bus_number": ""}).status_code == 400
    assert admin.post("/api/admin/buses", json={"bus_number": "X", "assigned_route_id": "NOPE"}).status_code == 400
    assert admin.put(f"/api/admin/buses/{bus_id}", json={"color_hex": "red"}).status_code == 400
    resp = admin.put(f"/api/admin/buses/{bus_id}", json={"assigned_route_id": "KU-R02", "color_hex": "#16a34a"})
    assert resp.get_json()["bus"]["assigned_route_id"] == "KU-R02"
    assert resp.get_json()["bus"]["color_hex"] == "#16A34A"

    tracking.start_trip(bus_id)
    assert admin.delete(f"/api/admin/buses/{bus_id}").status_code == 400    # live
    tracking.stop_trip(bus_id)
    assert admin.post("/api/admin/devices", json={"name": "Box", "bus_id": "KU-BUS-01"}).status_code == 200
    resp = admin.delete("/api/admin/buses/KU-BUS-01")
    assert resp.status_code == 400 and "GPS devices" in resp.get_json()["message"]   # still has a GPS box
    assert admin.delete(f"/api/admin/buses/{bus_id}").status_code == 200
    assert tracking.get_bus(bus_id) is None


def test_buses_have_own_colours(client):
    colours = [b["color_hex"] for b in buses_by_id(client).values()]
    assert all(colours) and len(colours) == len(set(colours))


def test_admin_changes_survive_restart(tmp_path):
    """Routes, buses and GPS devices are saved in the database, not just in memory."""
    class FileDb(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'busplus.db'}"
    first = create_app(FileDb).test_client()
    first.post("/api/auth/admin/login", json={"username": "admin", "password": TestConfig.ADMIN_PASSWORD})
    resp = first.post("/api/admin/devices", json={"name": "Box 2", "bus_id": "KU-BUS-02"})
    key = resp.get_json()["settings"]["key"]
    assert first.put("/api/admin/buses/KU-BUS-02", json={"bus_name": "Renamed"}).status_code == 200

    second = create_app(FileDb).test_client()                              # "server restart"
    assert buses_by_id(second)["KU-BUS-02"]["bus_name"] == "Renamed"
    resp = second.post("/api/device/location", json={"lat": 22.9784, "lng": 89.4626},
                       headers={"X-Device-Key": key})                     # the same key still works
    assert resp.status_code == 200 and resp.get_json()["bus_id"] == "KU-BUS-02"


# ---------------------------------------------------------------------------
# Students and teachers
# ---------------------------------------------------------------------------
def test_student_sign_in_and_map(client, admin):
    assert client.get("/student/dashboard").status_code == 302                # sign in first
    page = client.get("/student/login").get_data(as_text=True)
    assert "Student login" in page and "Student ID" in page
    assert client.post("/api/auth/student/login", json={"full_name": "Tanvir", "student_id": ""}).status_code == 400
    resp = client.post("/api/auth/student/login", json={"full_name": "Tanvir Ahmed", "student_id": "260201"})
    assert resp.get_json()["redirect_url"] == "/student/dashboard"
    assert "Tanvir Ahmed" in client.get("/student/dashboard").get_data(as_text=True)
    assert "260201" in admin.get("/backend").get_data(as_text=True)         # admin's Users tab
    client.post("/api/auth/logout")
    assert client.get("/student/dashboard").status_code == 302


def test_teacher_and_student_buses_are_separate(admin, app, services):
    tracking, _ = services
    assert admin.put("/api/admin/buses/KU-BUS-04", json={"audience": "teacher"}).status_code == 200
    assert admin.put("/api/admin/buses/KU-BUS-04", json={"audience": "visitor"}).status_code == 400
    assert "KU-BUS-04" not in buses_by_id(admin, "student")
    assert list(buses_by_id(admin, "teacher")) == ["KU-BUS-04"]

    teacher = app.test_client()
    assert teacher.get("/teacher/dashboard").status_code == 302
    teacher.post("/api/auth/teacher/login", json={"full_name": "Dr. Nasrin", "teacher_id": "T-101"})
    page = teacher.get("/teacher/dashboard").get_data(as_text=True)
    assert "KU-BUS-04" in page and "KU-BUS-01" not in page

    tracking.update_location("KU-BUS-04", 22.7740, 89.5845, 30.0)
    check = "/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More&audience="
    assert admin.get(check + "student").get_json()["alert"]["bus_id"] == "KU-BUS-01"
    assert admin.get(check + "teacher").get_json()["alert"]["bus_id"] == "KU-BUS-04"
    assert admin.get("/api/notification/check?route_id=KU-R03&audience=teacher").get_json()["alert"] is None


# ---------------------------------------------------------------------------
# Arrival alerts
# ---------------------------------------------------------------------------
def test_offline_bus_gives_no_alert(client):
    alert = client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More").get_json()["alert"]
    assert alert["urgency_level"] == "IDLE" and not alert["is_alert_triggered"] and alert["eta_minutes"] is None


def test_alert_uses_chosen_bus_or_nearest_live_bus(client, services):
    tracking, _ = services
    tracking.update_location("KU-BUS-04", 22.7740, 89.5845, 30.0)           # live, next to Malabotha More
    url = "/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More"
    alert = client.get(url).get_json()["alert"]
    assert alert["bus_id"] == "KU-BUS-04" and alert["is_alert_triggered"]
    assert client.get(url + "&bus_id=KU-BUS-01").get_json()["alert"]["bus_id"] == "KU-BUS-01"
    assert client.get(url + "&alert_threshold_minutes=abc").status_code == 200


def test_bus_that_passed_the_stop_does_not_count_down(client, services):
    tracking, _ = services
    tracking.update_location("KU-BUS-01", 22.7935, 89.5695, 30.0)           # past Malabotha More
    alert = client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More").get_json()["alert"]
    assert alert["urgency_level"] == "PASSED" and alert["eta_minutes"] is None
    alert = client.get("/api/notification/check?route_id=KU-R01&stop_name=PTI%20More").get_json()["alert"]
    assert alert["eta_minutes"] is not None


def test_stop_names_are_matched_forgivingly(services):
    tracking, _ = services
    route = tracking.get_route("KU-R01")
    assert route.get_stop_by_name("malabotha bazar").stop_name == "Malabotha More"
    assert route.get_stop_by_name("PTI").sequence_order == 5


# ---------------------------------------------------------------------------
# Live updates and test drives
# ---------------------------------------------------------------------------
def test_live_stream_pushes_changes_at_once(client, services):
    tracking, _ = services
    resp = client.get("/api/buses/stream?audience=student", buffered=False)
    chunks = iter(resp.response)
    assert "retry:" in next(chunks).decode()
    payload = json.loads(next(chunks).decode()[len("data: "):])
    assert all(b["audience"] == "student" for b in payload["buses"])
    resp.close()

    version = tracking.get_version()
    threading.Timer(0.2, lambda: tracking.update_location("KU-BUS-02", 22.9, 89.48, 20.0)).start()
    started = time.monotonic()
    assert tracking.wait_for_change(version, timeout=5) > version
    assert time.monotonic() - started < 1.5


def test_test_drive_parks_at_hadi_chattar(admin, services):
    tracking, _ = services
    with mock.patch.object(tracking_module.time, "sleep", lambda *_: None):
        assert admin.post("/api/admin/buses/KU-BUS-03/simulate").get_json()["simulating"]
        tracking._simulation_threads["KU-BUS-03"].join(timeout=10)
    bus = tracking.get_bus("KU-BUS-03")
    assert (round(bus.current_latitude, 5), round(bus.current_longitude, 5)) == (DEST["latitude"], DEST["longitude"])
    assert bus.trip_status == "ARRIVED" and not bus.is_simulating


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def test_pages_render(client, admin):
    for url in ("/", "/student/login", "/teacher/login", "/staff/login", "/health"):
        assert client.get(url).status_code == 200, url
    page = admin.get("/backend").get_data(as_text=True)
    for section in ("GPS devices", "Routes", "Buses", "Users"):
        assert section in page
    # The driver part is gone completely
    assert client.get("/driver/login").status_code == 404
    assert client.get("/driver/dashboard").status_code == 404
    assert client.post("/api/auth/driver/login", json={"full_name": "A", "rider_id": "1"}).status_code == 404
    assert client.post("/api/driver/location", json={"latitude": 22.8, "longitude": 89.5}).status_code == 404
    assert client.get("/api/nothing").get_json() == {"success": False, "message": "Not found."}


# ---------------------------------------------------------------------------
# Rider types from content/user_types.py
# ---------------------------------------------------------------------------
def test_every_rider_type_gets_button_login_and_map(client):
    from content.user_types import RIDER_TYPES
    landing = client.get("/").get_data(as_text=True)
    for key, info in RIDER_TYPES.items():
        assert f"/{key}/login" in landing and info["label"] in landing
        assert info["id_label"] in client.get(f"/{key}/login").get_data(as_text=True)
        resp = client.post(f"/api/auth/{key}/login", json={"full_name": "Test", "rider_id": "X1"})
        assert resp.get_json()["redirect_url"] == f"/{key}/dashboard"
        assert client.get(f"/{key}/dashboard").status_code == 200
    assert client.get("/nobody/login").status_code == 404
    assert "Driver" not in landing
    assert client.post("/api/auth/nobody/login", json={"full_name": "A", "rider_id": "1"}).status_code == 404


# ---------------------------------------------------------------------------
# Bus schedules (set day by day, riders see today)
# ---------------------------------------------------------------------------
def _week(morning=(), afternoon=()):
    day = {"morning": [{"bus_id": b, "time": t} for b, t in morning],
           "afternoon": [{"bus_id": b, "time": t} for b, t in afternoon]}
    return {"days": {d: day for d in ("sat", "sun", "mon", "tue", "wed", "thu", "fri")}}


def test_riders_see_only_todays_schedule(admin, client):
    from services import schedule_service
    today = schedule_service.today_key()
    week = _week()
    week["days"][today] = {"morning": [{"bus_id": "KU-BUS-01", "time": "08:50"}],
                           "afternoon": [{"bus_id": "KU-BUS-01", "time": "14:30"}]}
    assert admin.put("/api/admin/schedules/KU-R01", json=week).status_code == 200
    data = client.get("/api/schedules").get_json()
    assert data["day"] == today
    route1 = {r["route_id"]: r for r in data["routes"]}["KU-R01"]
    assert route1["morning"] == [{"time": "08:50", "bus_name": "Khan Jahan Ali Express", "color_hex": "#E11D48"}]
    assert route1["afternoon"][0]["time"] == "14:30"
    assert set(route1["morning"][0]) == {"time", "bus_name", "color_hex"}       # one time per bus, no extras


def test_admin_sets_every_day_separately(admin, client):
    week = _week(morning=[("KU-BUS-02", "09:10"), ("KU-BUS-02", "08:40")], afternoon=[("", "17:00")])
    week["days"]["fri"] = {"morning": [], "afternoon": []}
    assert client.put("/api/admin/schedules/KU-R02", json=week).status_code == 401      # admin only
    saved = admin.put("/api/admin/schedules/KU-R02", json=week).get_json()["schedule"]["days"]
    assert [t["time"] for t in saved["sat"]["morning"]] == ["08:40", "09:10"]           # sorted
    assert saved["fri"] == {"morning": [], "afternoon": []}                             # no bus on Friday
    for bad in (_week(morning=[("KU-BUS-02", "9am")]), _week(morning=[("NOPE", "08:00")]),
                {"days": {"holiday": {}}}, {"days": "x"}):
        assert admin.put("/api/admin/schedules/KU-R02", json=bad).status_code == 400
    assert admin.put("/api/admin/schedules/NOPE", json=_week()).status_code == 404


def test_schedule_hides_other_groups_buses(admin, client):
    admin.put("/api/admin/buses/KU-BUS-04", json={"audience": "teacher"})
    admin.put("/api/admin/schedules/KU-R01",
              json=_week(morning=[("KU-BUS-01", "08:50"), ("KU-BUS-04", "09:20")]))
    def morning(url):
        routes = {r["route_id"]: r for r in client.get(url).get_json()["routes"]}
        return [t["bus_name"] for t in routes["KU-R01"]["morning"]]
    assert morning("/api/schedules?audience=student") == ["Khan Jahan Ali Express"]
    assert morning("/api/schedules?audience=teacher") == ["Bhairab Shuttle"]
    assert len(morning("/api/schedules")) == 2                                          # no group: every bus


def test_schedule_option_on_rider_menu_and_backend(client, admin):
    client.post("/api/auth/student/login", json={"full_name": "A", "rider_id": "1"})
    assert "Bus schedule" in client.get("/student/dashboard").get_data(as_text=True)
    assert "Bus schedules" in admin.get("/backend").get_data(as_text=True)


def test_start_page_order_and_new_bus_default(client, admin):
    from content.user_types import DEFAULT_RIDER_TYPE, RIDER_TYPES
    landing = client.get("/").get_data(as_text=True)
    positions = [landing.index(f"/{key}/login") for key in RIDER_TYPES]
    assert positions == sorted(positions)                       # buttons follow content/user_types.py
    resp = admin.post("/api/admin/buses", json={"bus_number": "KU Bus #09", "assigned_route_id": "KU-R01"})
    assert resp.get_json()["bus"]["audience"] == DEFAULT_RIDER_TYPE


def test_admin_sign_in_forgives_spaces_and_shows_where_the_password_is(client):
    good = {"username": " Admin ", "password": f"  {TestConfig.ADMIN_PASSWORD} \n"}
    assert client.post("/api/auth/admin/login", json=good).status_code == 200
    page = client.get("/backend/login", follow_redirects=False)
    assert page.status_code == 302                                   # already signed in
    other = create_app(TestConfig).test_client()
    html = other.get("/backend/login").get_data(as_text=True)
    assert 'id="toggle-password"' in html and "Show password" in html


# ---------------------------------------------------------------------------
# GPS devices tab: quick add, boxes that join by themselves, on / off the map
# ---------------------------------------------------------------------------
JOIN = {"chip_id": "24a160c8f3b4", "token": "a1b2c3d4e5f60718293a4b5c", "fw": "1.1.0"}


def test_quick_add_names_the_device_and_takes_the_first_free_bus(admin, add_device):
    add_device("Tracker in Bus #01", "KU-BUS-01")
    reply = admin.post("/api/admin/devices/quick").get_json()
    assert reply["success"] and len(reply["settings"]["key"]) == 24
    assert reply["device"]["bus_id"] == "KU-BUS-02"
    assert reply["device"]["name"].startswith("Tracker in ")
    assert admin.get("/api/admin/devices").get_json()["next_free_bus"] == "KU-BUS-03"


def test_box_joins_by_itself_after_approval(admin, client):
    first = client.post("/api/device/pair", json=JOIN)
    assert first.status_code == 200
    waiting = first.get_json()
    assert waiting["status"] == "waiting" and len(waiting["code"]) == 6 and waiting["retry_s"] == 5

    listed = admin.get("/api/admin/devices").get_json()["waiting"]
    assert [w["chip_id"] for w in listed] == ["24A160C8F3B4"] and listed[0]["code"] == waiting["code"]
    assert "token" not in listed[0]

    # someone who only knows the chip ID can't take over the request
    other = client.post("/api/device/pair", json={**JOIN, "token": "zzzzzzzzzzzzzzzzzzzz"})
    assert other.status_code == 400

    approved = admin.post("/api/admin/devices/waiting/24A160C8F3B4/approve", json={"bus_id": "KU-BUS-03"}).get_json()
    assert approved["success"] and approved["device"]["bus_id"] == "KU-BUS-03"
    assert approved["device"]["chip_id"] == "24A160C8F3B4" and approved["device"]["name"].startswith("Tracker in ")

    got = client.post("/api/device/pair", json=JOIN).get_json()
    assert got["status"] == "approved" and len(got["key"]) == 24
    # the key is handed out once only
    assert client.post("/api/device/pair", json=JOIN).get_json()["status"] == "waiting"

    report = client.post("/api/device/location", json={"fix": True, "lat": 22.7725, "lng": 89.5855, "hdop": 1},
                         headers={"X-Device-Key": got["key"]})
    assert report.status_code == 200 and report.get_json()["bus_id"] == "KU-BUS-03"


def test_rejected_box_is_told_so(admin, client):
    client.post("/api/device/pair", json=JOIN)
    assert admin.post("/api/admin/devices/waiting/24a160c8f3b4/reject").get_json()["success"]
    resp = client.post("/api/device/pair", json=JOIN)
    assert resp.status_code == 403 and resp.get_json()["status"] == "rejected"
    assert admin.get("/api/admin/devices").get_json()["waiting"] == []
    assert admin.post("/api/admin/devices/waiting/24A160C8F3B4/approve", json={}).status_code == 404


def test_join_request_must_be_well_formed(client):
    assert client.post("/api/device/pair", json={"chip_id": "not hex!", "token": JOIN["token"]}).status_code == 400
    assert client.post("/api/device/pair", json={"chip_id": JOIN["chip_id"], "token": "short"}).status_code == 400
    assert client.post("/api/device/pair", data="nope").status_code == 400


def test_box_that_joined_before_gets_a_new_key_for_the_same_device(admin, client):
    client.post("/api/device/pair", json=JOIN)
    first = admin.post("/api/admin/devices/waiting/24A160C8F3B4/approve", json={"bus_id": "KU-BUS-02"}).get_json()
    old_key = client.post("/api/device/pair", json=JOIN).get_json()["key"]
    again = {**JOIN, "token": "ffffffffffffffffffffffff"}           # flash was erased: new token
    client.post("/api/device/pair", json=again)
    listed = admin.get("/api/admin/devices").get_json()["waiting"]
    assert listed[0]["known_device_id"] == first["device"]["device_id"]
    second = admin.post("/api/admin/devices/waiting/24A160C8F3B4/approve", json={}).get_json()
    assert second["device"]["device_id"] == first["device"]["device_id"] and second["device"]["bus_id"] == "KU-BUS-02"
    new_key = client.post("/api/device/pair", json=again).get_json()["key"]
    assert new_key != old_key
    old = client.post("/api/device/location", json={"fix": False}, headers={"X-Device-Key": old_key})
    assert old.status_code == 401
    assert len(admin.get("/api/admin/devices").get_json()["devices"]) == 1


def test_device_removed_from_the_map_hides_its_bus_everywhere(admin, client, gps_box):
    gps_box(lat=22.7725, lng=89.5855)
    assert buses_by_id(client)["KU-BUS-01"]["is_active"]

    off = admin.put("/api/admin/devices/GPS-01/map", json={"show": False}).get_json()
    assert off["success"] and off["device"]["show_on_map"] is False
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]

    reply = gps_box(lat=22.7760, lng=89.5855)                  # the box keeps reporting ...
    assert reply.status_code == 200 and reply.get_json()["on_map"] is False
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]   # ... but the bus stays off the map
    assert admin.get("/api/admin/devices").get_json()["devices"][0]["status"] == "online"

    assert admin.put("/api/admin/devices/GPS-01/map", json={"show": True}).get_json()["device"]["show_on_map"]
    gps_box(lat=22.7790, lng=89.5855)
    assert buses_by_id(client)["KU-BUS-01"]["is_active"]
    assert admin.put("/api/admin/devices/GPS-01/map", json={"show": "yes"}).status_code == 400
    assert admin.put("/api/admin/devices/GPS-99/map", json={"show": True}).status_code == 404


def test_map_setting_is_saved(app, admin, add_device):
    add_device()
    admin.put("/api/admin/devices/GPS-01/map", json={"show": False})
    with app.app_context():
        devices.load()
    assert devices.get("GPS-01").show_on_map is False


def test_older_database_gets_the_new_device_columns(tmp_path):
    import sqlite3

    from config import TestConfig

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:          # gps_devices as the previous version made it
        con.execute("CREATE TABLE gps_devices (device_id VARCHAR(20) PRIMARY KEY, name VARCHAR(60), "
                    "bus_id VARCHAR(20), key_hash VARCHAR(64), key_hint VARCHAR(8), created_at VARCHAR(40))")
        con.execute("INSERT INTO gps_devices VALUES ('GPS-01', 'Old box', NULL, 'abc', 'wxyz', '2026-11-16')")

    class OldDb(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{path}"

    create_app(OldDb)
    assert devices.get("GPS-01").show_on_map is True and devices.get("GPS-01").chip_id == ""


def test_backend_has_no_icons(admin):
    import re

    page = admin.get("/backend").get_data(as_text=True)
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿⌀-⏿■-◿]", page)
    assert "<svg" not in page
    for text in ("Add a device", "Manually", "Automatically", "Boxes asking to join", "Connected devices"):
        assert text in page


# ---------------------------------------------------------------------------
# Fixes from the code scan (17 Nov 2026)
# ---------------------------------------------------------------------------
def test_admin_sign_in_expires_and_is_not_extended_by_a_rider_sign_in(admin, monkeypatch):
    assert admin.get("/api/admin/devices").status_code == 200
    # signing in as a student in the same browser keeps the admin, but not for longer
    rider = {"full_name": "Argha Roy", "rider_id": "190212"}
    assert admin.post("/api/auth/student/login", json=rider).status_code == 200
    assert admin.get("/api/admin/devices").status_code == 200
    later = time.time() + 13 * 3600
    monkeypatch.setattr("controllers.auth_controller.time.time", lambda: later)
    assert admin.get("/api/admin/devices").status_code == 401
    assert admin.get("/backend").status_code == 302


def test_admin_sign_out_needs_post(admin):
    assert admin.get("/backend/logout").status_code == 405
    assert admin.post("/backend/logout").status_code == 302
    assert admin.get("/api/admin/devices").status_code == 401


def test_rider_sign_in_checks_id_and_name_and_keeps_the_first_name(app, client, admin):
    def login(name, rider_id):
        return client.post("/api/auth/student/login", json={"full_name": name, "rider_id": rider_id})

    assert login("Argha Roy", "KU-2021-033").status_code == 200
    assert login("রহিম উদ্দিন", "190212").status_code == 200          # names in Bangla are fine
    assert login("<script>alert(1)</script>", "190213").status_code == 400
    assert login("Visit http://spam.example", "190214").status_code == 400
    assert login("Argha Roy", "19 02 12").status_code == 400
    assert login("Somebody Else", "KU-2021-033").status_code == 200    # can sign in ...
    from services import store
    with app.app_context():
        names = {r["rider_id"]: r["full_name"] for r in store.list_riders()}
    assert names["KU-2021-033"] == "Argha Roy"                          # ... but can't rename the rider


def test_bad_timetable_shapes_are_refused_not_crashing(admin):
    for days in ({"sat": ["x"]}, {"sat": {"morning": ["x"]}}, {"sat": {"morning": [None]}}, ["sat"]):
        resp = admin.put("/api/admin/schedules/KU-R01", json={"days": days})
        assert resp.status_code == 400, days
    ok = admin.put("/api/admin/schedules/KU-R01", json={"days": {"sat": None, "sun": {"morning": []}}})
    assert ok.status_code == 200


def test_eta_never_gets_later_when_the_bus_speeds_up():
    etas = [geo.estimate_eta(22.80, 89.50, 22.85, 89.50, bus_speed_kmh=v)["eta_minutes"] for v in range(0, 61, 3)]
    assert all(later <= earlier for earlier, later in zip(etas, etas[1:], strict=False)), etas


def test_alert_minutes_must_be_a_real_number(client):
    from controllers.helpers import optional_float

    assert optional_float("nan") is None and optional_float("inf") is None and optional_float("7.5") == 7.5
    resp = client.get("/api/notification/check?route_id=KU-R01&alert_threshold_minutes=nan")
    assert resp.status_code == 200
