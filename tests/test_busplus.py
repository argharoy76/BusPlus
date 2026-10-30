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
from services import geo

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
def test_backend_is_admin_only(client, driver_login):
    assert client.get("/backend").status_code == 302
    assert "/backend/login" in client.get("/backend").headers["Location"]
    assert client.post("/api/admin/buses", json={"bus_number": "X"}).status_code == 401
    assert client.post("/api/auth/admin/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    assert client.get("/backend/login").status_code == 200
    driver, resp = driver_login()
    assert resp.status_code == 200
    assert driver.post("/api/admin/drivers", json={}).status_code == 401
    assert driver.get("/backend").status_code == 302


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


def test_pins_are_hashed_and_phones_private(admin, client, services):
    _, users = services
    driver = users.get_driver("DRV-01")
    assert driver.pin_hash and "1234" not in driver.pin_hash
    resp = admin.put("/api/admin/drivers/DRV-02", json={"full_name": "Abdul Mannan", "pin": "5678"})
    assert resp.status_code == 200 and "pin" not in resp.get_json()["driver"]
    public = json.dumps(client.get("/api/buses").get_json())
    assert "phone" not in public and "+880" not in public


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------
def test_driver_name_suggestions(client):
    data = client.get("/api/drivers/search?q=raf").get_json()
    assert data["count"] == 1
    assert data["drivers"][0]["full_name"] == "Md. Rafiqul Islam"
    assert data["drivers"][0]["route_id"] == "KU-R01"


def test_driver_login_uses_admin_set_details_only(admin, driver_login):
    assert admin.put("/api/admin/drivers/DRV-03", json={"pin": "4321"}).status_code == 200
    assert driver_login("Kamal Hossain", "KU-R03", "1234")[1].status_code == 401   # old PIN
    assert driver_login("a", "KU-R03", "4321")[1].status_code == 401               # not a full name
    assert driver_login("Kamal Hossain", "KU-R01", "4321")[1].status_code == 401   # not his bus's route
    assert driver_login("Kamal Hossain", "KU-R03", "4321")[1].status_code == 200


def test_driver_edit_keeps_pin_when_left_empty(admin, driver_login):
    assert admin.put("/api/admin/drivers/DRV-04", json={"phone": "+880 1", "pin": ""}).status_code == 200
    assert driver_login("Siraj Uddin", "KU-R01", "1234")[1].status_code == 200
    assert admin.put("/api/admin/drivers/DRV-04", json={"pin": "12"}).status_code == 400


def test_one_phone_at_a_time(admin, driver_login):
    _, first = driver_login()
    assert first.status_code == 200
    _, second = driver_login()
    assert second.status_code == 409
    assert "another device" in second.get_json()["message"]
    assert admin.post("/api/admin/drivers/DRV-01/unlock").status_code == 200
    assert driver_login()[1].status_code == 200


def test_driver_moves_only_own_bus_and_leaves_trail(client, driver_login):
    assert client.post("/api/driver/location", json={"latitude": 22.8, "longitude": 89.5}).status_code == 401
    driver, _ = driver_login()
    assert driver.post("/api/driver/trip/start").status_code == 200
    for lat in (22.7725, 22.7760, 22.7800):
        resp = driver.post("/api/driver/location", json={"bus_id": "KU-BUS-02", "latitude": lat, "longitude": 89.584})
        assert resp.get_json()["bus"]["bus_id"] == "KU-BUS-01"        # bus_id in the body is ignored
    buses = buses_by_id(client)
    assert len(buses["KU-BUS-01"]["trail"]) >= 3
    assert not buses["KU-BUS-02"]["is_active"]

    driver.post("/api/auth/logout")                                    # logging out = going offline
    bus = buses_by_id(client)["KU-BUS-01"]
    assert not bus["is_active"] and bus["trail"] == []


def test_offline_switch_hides_bus(client, driver_login):
    driver, _ = driver_login()
    driver.post("/api/driver/location", json={"latitude": 22.78, "longitude": 89.58})
    assert buses_by_id(client)["KU-BUS-01"]["is_active"]
    driver.post("/api/driver/trip/stop")
    assert not buses_by_id(client)["KU-BUS-01"]["is_active"]


def test_daily_duty_notice(admin, driver_login):
    driver, _ = driver_login("Kamal Hossain", "KU-R03", "1234")
    duty = driver.get("/api/driver/assignment").get_json()["assignment"]
    assert (duty["bus_id"], duty["route_id"], duty["to_stop"]) == ("KU-BUS-03", "KU-R03", DEST["stop_name"])
    driver.post("/api/driver/assignment/seen")
    assert not driver.get("/api/driver/assignment").get_json()["assignment"]["unseen"]

    assert admin.put("/api/admin/buses/KU-BUS-03", json={"assigned_route_id": "KU-R02"}).status_code == 200
    duty = driver.get("/api/driver/assignment").get_json()["assignment"]
    assert duty["route_id"] == "KU-R02" and duty["changed_today"] and duty["unseen"]
    driver.post("/api/driver/assignment/seen")
    assert not driver.get("/api/driver/assignment").get_json()["assignment"]["unseen"]


def test_driver_shown_on_assigned_bus(admin, client):
    assert admin.put("/api/admin/drivers/DRV-03", json={"assigned_bus_id": "KU-BUS-04"}).status_code == 200
    buses = buses_by_id(client)
    assert buses["KU-BUS-04"]["driver_id"] == "DRV-03"
    assert buses["KU-BUS-03"]["driver_id"] is None


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
    assert admin.delete("/api/admin/buses/KU-BUS-01").status_code == 400    # still has a driver
    assert admin.delete(f"/api/admin/buses/{bus_id}").status_code == 200
    assert tracking.get_bus(bus_id) is None


def test_buses_have_own_colours(client):
    colours = [b["color_hex"] for b in buses_by_id(client).values()]
    assert all(colours) and len(colours) == len(set(colours))


def test_admin_changes_survive_restart(tmp_path):
    """Routes, buses and drivers are saved in the database, not just in memory."""
    class FileDb(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'busplus.db'}"
    first = create_app(FileDb).test_client()
    first.post("/api/auth/admin/login", json={"username": "admin", "password": TestConfig.ADMIN_PASSWORD})
    assert first.post("/api/admin/drivers", json={"full_name": "New Driver", "pin": "9999",
                                                  "assigned_bus_id": "KU-BUS-02"}).status_code == 200
    assert first.put("/api/admin/buses/KU-BUS-02", json={"bus_name": "Renamed"}).status_code == 200

    second = create_app(FileDb).test_client()                              # "server restart"
    assert buses_by_id(second)["KU-BUS-02"]["bus_name"] == "Renamed"
    resp = second.post("/api/auth/driver/login", json={"driver_name": "New Driver", "route_id": "KU-R02",
                                                       "pin": "9999"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Students and teachers
# ---------------------------------------------------------------------------
def test_student_sign_in_and_map(client, admin):
    assert client.get("/student/dashboard").status_code == 302                # sign in first
    page = client.get("/student/login").get_data(as_text=True)
    assert "Student's Name" in page and "Student ID" in page
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
    assert admin.put("/api/admin/buses/KU-BUS-04", json={"audience": "staff"}).status_code == 400
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
def test_pages_render(client, admin, driver_login):
    for url in ("/", "/driver/login", "/student/login", "/teacher/login", "/health"):
        assert client.get(url).status_code == 200, url
    assert client.get("/driver/dashboard").status_code == 302
    driver, _ = driver_login()
    assert driver.get("/driver/dashboard").status_code == 200
    page = admin.get("/backend").get_data(as_text=True)
    for section in ("Drivers", "Routes", "Buses", "Users"):
        assert section in page
    assert client.get("/api/nothing").get_json() == {"success": False, "message": "Not found."}
