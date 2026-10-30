"""
Khulna University Bus Tracker (BusPlus)
Automated Unit and Integration Test Suite
"""

import unittest
from app import create_app
from services.eta_service import ETAService
from services.notification_service import NotificationService
from services.tracking_service import TrackingService
from services.user_service import UserService

class TestBusPlusCore(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.tracking_service = TrackingService()
        self.user_service = UserService()
        # self.client is the backend admin; other clients stay signed out unless a test signs them in
        from config import AppConfig
        self.admin_password = AppConfig.ADMIN_PASSWORD
        resp = self.client.post("/api/auth/admin/login", json={"username": AppConfig.ADMIN_USERNAME, "password": self.admin_password})
        assert resp.status_code == 200, resp.get_json()

    def driver_client(self, driver_name="Md. Rafiqul Islam", route_id="KU-R01", pin="1234", driver_id=None):
        """A browser signed in as a driver (front end)."""
        client = self.app.test_client()
        resp = client.post("/api/auth/driver/login", json={
            "driver_name": driver_name, "driver_id": driver_id, "route_id": route_id, "pin": pin})
        return client, resp

    def test_haversine_distance_calculation(self):
        """Tests that Haversine distance correctly measures distance between Malabotha and KU."""
        malabotha_lat, malabotha_lng = 22.7725, 89.5855
        ku_campus_lat, ku_campus_lng = 22.8010, 89.5345

        dist_km = ETAService.calculate_haversine_distance_km(
            malabotha_lat, malabotha_lng, ku_campus_lat, ku_campus_lng
        )
        self.assertGreater(dist_km, 5.0)
        self.assertLess(dist_km, 9.0)

    def test_driver_autocomplete_search(self):
        """Tests that driver search matches typed letters (e.g. 'raf')."""
        resp = self.client.get("/api/drivers/search?q=raf")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["count"], 1)
        self.assertIn("Rafiqul", data["drivers"][0]["full_name"])

    def test_driver_single_session_lock(self):
        """
        Tests that when a driver logs in, no other driver/device can access that account.
        """
        # Unlock driver DRV-01 first to ensure clean state
        self.user_service.unlock_driver_session("DRV-01")

        # Session 1 logs in
        client1 = self.app.test_client()
        resp1 = client1.post("/api/auth/driver/login", json={
            "driver_name": "Md. Rafiqul Islam",
            "route_id": "KU-R01",
            "pin": "1234"
        })
        self.assertEqual(resp1.status_code, 200)
        self.assertTrue(resp1.get_json()["success"])

        # Session 2 tries to log in with same driver account -> should be blocked!
        client2 = self.app.test_client()
        resp2 = client2.post("/api/auth/driver/login", json={
            "driver_name": "Md. Rafiqul Islam",
            "route_id": "KU-R01",
            "pin": "1234"
        })
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("logged in on another", resp2.get_json()["message"])

        # Admin unlocks session
        unlock_resp = self.client.post("/api/admin/drivers/DRV-01/unlock")
        self.assertEqual(unlock_resp.status_code, 200)

        # Now session 2 can log in
        resp3 = client2.post("/api/auth/driver/login", json={
            "driver_name": "Md. Rafiqul Islam",
            "route_id": "KU-R01",
            "pin": "1234"
        })
        self.assertEqual(resp3.status_code, 200)

        # Clean up
        self.user_service.unlock_driver_session("DRV-01")

    def test_backend_driver_update(self):
        """Tests updating driver details from backend admin."""
        resp = self.client.put("/api/admin/drivers/DRV-02", json={
            "full_name": "Abdul Mannan Updated",
            "phone": "+880 1799-888777",
            "assigned_route_id": "KU-R02",
            "assigned_bus_id": "KU-BUS-02",
            "pin": "5678"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["driver"]["full_name"], "Abdul Mannan Updated")
        self.assertEqual(data["driver"]["pin"], "5678")

    def test_admin_portal_render(self):
        """Backend admin portal shows Drivers, Routes and Buses to the signed-in admin."""
        for endpoint in ["/backend", "/admin"]:
            r = self.client.get(endpoint)
            self.assertEqual(r.status_code, 200)
            for section in (b"Drivers", b"Routes", b"Buses"):
                self.assertIn(section, r.data)

    def test_backend_requires_admin_sign_in(self):
        """Nobody but the admin can open the backend; drivers only use the front end."""
        anon = self.app.test_client()
        self.assertEqual(anon.get("/backend").status_code, 302)
        self.assertIn("/backend/login", anon.get("/backend").headers["Location"])
        self.assertEqual(anon.get("/api/admin/drivers").status_code, 401)
        self.assertEqual(anon.post("/api/admin/buses", json={"bus_number": "X"}).status_code, 401)
        self.assertEqual(anon.post("/api/config/maps-key", json={"api_key": "x"}).status_code, 401)
        self.assertEqual(anon.post("/api/auth/admin/login", json={"username": "admin", "password": "wrong"}).status_code, 401)
        self.assertEqual(anon.get("/backend/login").status_code, 200)

        self.user_service.unlock_driver_session("DRV-04")
        driver, resp = self.driver_client("Siraj Uddin", "KU-R01", "1234")
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertEqual(driver.get("/api/admin/drivers").status_code, 401)
        self.assertEqual(driver.get("/backend").status_code, 302)
        self.user_service.unlock_driver_session("DRV-04")

    def test_driver_login_uses_admin_set_details_only(self):
        """No master PIN, no partial names, and the route must be the driver's bus route."""
        self.client.put("/api/admin/drivers/DRV-03", json={"pin": "4321"})
        self.user_service.unlock_driver_session("DRV-03")
        try:
            _, resp = self.driver_client("Kamal Hossain", "KU-R03", "1234")
            self.assertEqual(resp.status_code, 401)          # old/master PIN refused
            _, resp = self.driver_client("a", "KU-R03", "4321")
            self.assertEqual(resp.status_code, 401)          # one letter isn't a name
            _, resp = self.driver_client("Kamal Hossain", "KU-R01", "4321")
            self.assertEqual(resp.status_code, 401)          # not his bus's route
            _, resp = self.driver_client("Kamal Hossain", "KU-R03", "4321")
            self.assertEqual(resp.status_code, 200, resp.get_json())
        finally:
            self.client.put("/api/admin/drivers/DRV-03", json={"pin": "1234"})
            self.user_service.unlock_driver_session("DRV-03")

    def test_only_signed_in_driver_moves_own_bus(self):
        """GPS updates need a driver login and always go to that driver's own bus; a trail is recorded."""
        anon = self.app.test_client()
        self.assertEqual(anon.post("/api/driver/location", json={"bus_id": "KU-BUS-02", "latitude": 22.8, "longitude": 89.5}).status_code, 401)

        self.user_service.unlock_driver_session("DRV-01")
        driver, resp = self.driver_client()
        self.assertEqual(resp.status_code, 200, resp.get_json())
        try:
            self.assertEqual(driver.post("/api/driver/trip/start", json={}).status_code, 200)
            for lat in (22.7725, 22.7760, 22.7800):
                r = driver.post("/api/driver/location", json={"bus_id": "KU-BUS-02", "latitude": lat, "longitude": 89.5840})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.get_json()["bus"]["bus_id"], "KU-BUS-01")   # body bus_id ignored
            buses = {b["bus_id"]: b for b in self.client.get("/api/buses").get_json()["buses"]}
            self.assertGreaterEqual(len(buses["KU-BUS-01"]["trail"]), 3)
            self.assertFalse(buses["KU-BUS-02"]["is_active"])

            # Logging out ends the trip and clears the trail
            driver.post("/api/auth/logout", json={})
            buses = {b["bus_id"]: b for b in self.client.get("/api/buses").get_json()["buses"]}
            self.assertFalse(buses["KU-BUS-01"]["is_active"])
            self.assertEqual(buses["KU-BUS-01"]["trail"], [])
        finally:
            self.tracking_service.set_trip_status("KU-BUS-01", False)
            self.user_service.unlock_driver_session("DRV-01")

    def test_backend_route_management(self):
        """Admin can add, edit and remove routes; every route ends at Hadi Chattar."""
        from config import AppConfig
        dest = AppConfig.FINAL_DESTINATION["stop_name"]
        resp = self.client.post("/api/admin/routes", json={
            "route_name": "Boyra - KU Line",
            "stops": [
                {"stop_name": "Boyra Bazar", "latitude": 22.8420, "longitude": 89.5380, "scheduled_morning_time": "08:30 AM"},
                {"stop_name": "Gollamari Mor", "latitude": 22.8090, "longitude": 89.5398}
            ]})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        route = resp.get_json()["route"]
        rid = route["route_id"]
        try:
            self.assertEqual([st["stop_name"] for st in route["stops"]], ["Boyra Bazar", "Gollamari Mor", dest])
            self.assertIn(rid, [r["route_id"] for r in self.client.get("/api/routes").get_json()["routes"]])

            # bad input
            self.assertEqual(self.client.post("/api/admin/routes", json={"route_name": "X", "stops": []}).status_code, 400)
            self.assertEqual(self.client.post("/api/admin/routes", json={"route_name": "X", "stops": [{"stop_name": "A"}]}).status_code, 400)

            # edit
            resp = self.client.put(f"/api/admin/routes/{rid}", json={"route_name": "Boyra Express", "stops": [
                {"stop_name": "Boyra Bazar", "latitude": 22.8420, "longitude": 89.5380}]})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["route"]["route_name"], "Boyra Express")
            self.assertEqual(resp.get_json()["route"]["stops"][-1]["stop_name"], dest)

            # a route with buses on it can't be removed
            self.assertEqual(self.client.delete("/api/admin/routes/KU-R01").status_code, 400)

            # New-style route: just a name + clicked points (no stop names) + the road line from the editor
            road = [[22.7840, 89.5780], [22.7900, 89.5700], [22.8000, 89.5500], [22.80209, 89.53398]]
            resp = self.client.post("/api/admin/routes", json={
                "route_name": "Rupsha - Hadi Chattar",
                "points": [{"lat": 22.7840, "lng": 89.5780}, {"lat": 22.7900, "lng": 89.5700}],
                "path": road})
            self.assertEqual(resp.status_code, 200, resp.get_json())
            new_route = resp.get_json()["route"]
            try:
                self.assertEqual([st["stop_name"] for st in new_route["stops"]], [dest])   # no stops to name
                self.assertEqual([[w["lat"], w["lng"]] for w in new_route["polyline_waypoints"]][:3], road[:3])
                self.assertEqual(len(new_route["via_points"]), 2)
                self.assertGreater(new_route["length_km"], 2)
                # bad line is refused
                self.assertEqual(self.client.post("/api/admin/routes", json={
                    "route_name": "Bad", "points": [{"lat": 22.78, "lng": 89.57}], "path": [[0, 0], [1, 1]]}).status_code, 400)
            finally:
                self.client.delete(f"/api/admin/routes/{new_route['route_id']}")
        finally:
            self.assertEqual(self.client.delete(f"/api/admin/routes/{rid}").status_code, 200)

    def test_driver_daily_duty_notification(self):
        """The driver sees today's bus and route; a change by the admin is flagged until read."""
        self.user_service.unlock_driver_session("DRV-03")
        driver, resp = self.driver_client("Kamal Hossain", "KU-R03", "1234")
        self.assertEqual(resp.status_code, 200, resp.get_json())
        try:
            duty = driver.get("/api/driver/assignment").get_json()["assignment"]
            self.assertEqual(duty["bus_id"], "KU-BUS-03")
            self.assertEqual(duty["route_id"], "KU-R03")
            self.assertEqual(duty["to_stop"], "Hadi Chattar")
            driver.post("/api/driver/assignment/seen")

            # Admin sends KU-BUS-03 on Route 2 today
            self.assertEqual(self.client.put("/api/admin/buses/KU-BUS-03", json={"assigned_route_id": "KU-R02"}).status_code, 200)
            duty = driver.get("/api/driver/assignment").get_json()["assignment"]
            self.assertEqual(duty["route_id"], "KU-R02")
            self.assertTrue(duty["changed_today"])
            self.assertTrue(duty["unseen"])
            driver.post("/api/driver/assignment/seen")
            self.assertFalse(driver.get("/api/driver/assignment").get_json()["assignment"]["unseen"])
        finally:
            self.client.put("/api/admin/buses/KU-BUS-03", json={"assigned_route_id": "KU-R03"})
            self.user_service.unlock_driver_session("DRV-03")

    def test_student_login_and_persistence(self):
        """Tests that student can log in with only Name & Student ID without permanent ID pre-registration."""
        student_client = self.app.test_client()

        # 1. Visiting /student/login renders the login form (HTTP 200)
        login_page_resp = student_client.get("/student/login")
        self.assertEqual(login_page_resp.status_code, 200)
        self.assertIn(b"Student's Name", login_page_resp.data)
        self.assertIn(b"Student ID", login_page_resp.data)

        # 2. Log in with only full_name and student_id (no permanent registration required)
        resp = student_client.post("/api/auth/student/login", json={
            "full_name": "Tanvir Ahmed",
            "student_id": "260201"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["success"])

        # 3. Student dashboard renders OK
        dash_resp = student_client.get("/student/dashboard")
        self.assertEqual(dash_resp.status_code, 200)
        self.assertIn(b"Tanvir Ahmed", dash_resp.data)

        # 4. Log out clears session
        logout_resp = student_client.post("/api/auth/logout", json={})
        self.assertEqual(logout_resp.status_code, 200)

        # 5. After logout, /student/login loads cleanly
        login_page_after_logout = student_client.get("/student/login")
        self.assertEqual(login_page_after_logout.status_code, 200)

    def test_inactive_bus_no_false_alarm(self):
        """Tests that offline/idle buses do not trigger false proximity alarms."""
        resp = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        alert = data["alert"]
        self.assertFalse(alert["is_active"])
        self.assertFalse(alert["is_alert_triggered"])
        self.assertIsNone(alert["eta_minutes"])

    def test_pti_and_malabotha_stops(self):
        """Tests that Malabotha More and PTI More are registered and resolvable on Route 1."""
        route1 = self.tracking_service.get_route_by_id("KU-R01")
        self.assertIsNotNone(route1)
        malabotha = route1.get_stop_by_name("Malabotha More")
        self.assertIsNotNone(malabotha)
        self.assertEqual(malabotha.sequence_order, 1)

        pti = route1.get_stop_by_name("PTI More")
        self.assertIsNotNone(pti)
        self.assertEqual(pti.sequence_order, 5)

    def test_buses_have_own_colors(self):
        """Every bus carries its own distinct marker colour."""
        buses = self.client.get("/api/buses").get_json()["buses"]
        colors = [b["color_hex"] for b in buses]
        self.assertTrue(all(colors))
        self.assertEqual(len(colors), len(set(colors)))

    def test_notification_check_specific_bus_and_best_bus(self):
        """bus_id picks that bus; without it, the live bus nearest the stop is used."""
        ts = self.tracking_service
        try:
            # Bus #04 (Route 1) is live right next to Malabotha More, Bus #01 is offline
            ts.set_trip_status("KU-BUS-01", False)
            ts.update_bus_location("KU-BUS-04", 22.7740, 89.5845, 30.0, None)

            data = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More").get_json()
            self.assertEqual(data["alert"]["bus_id"], "KU-BUS-04")
            self.assertTrue(data["alert"]["is_active"])

            data = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More&bus_id=KU-BUS-01").get_json()
            self.assertEqual(data["alert"]["bus_id"], "KU-BUS-01")
            self.assertFalse(data["alert"]["is_active"])

            # Bad threshold no longer crashes the endpoint
            resp = self.client.get("/api/notification/check?alert_threshold_minutes=abc")
            self.assertEqual(resp.status_code, 200)
        finally:
            ts.set_trip_status("KU-BUS-04", False)

    def test_every_route_ends_at_hadi_chattar(self):
        """All buses' routes finish at the one final destination (Hadi Chattar)."""
        from config import AppConfig
        dest = AppConfig.FINAL_DESTINATION
        routes = self.client.get("/api/routes").get_json()["routes"]
        self.assertGreaterEqual(len(routes), 3)
        for route in routes:
            last = route["stops"][-1]
            self.assertEqual(last["stop_name"], dest["stop_name"])
            self.assertAlmostEqual(last["latitude"], dest["latitude"])
            self.assertAlmostEqual(last["longitude"], dest["longitude"])
            self.assertEqual(route["polyline_waypoints"][-1], {"lat": dest["latitude"], "lng": dest["longitude"]})
            # The line must arrive at Hadi Chattar, not overshoot and double back:
            # the second-last point is farther from the destination than nothing in between gets closer.
            pts = route["polyline_waypoints"]
            def d(pt):
                return ((pt["lat"] - dest["latitude"]) ** 2 + (pt["lng"] - dest["longitude"]) ** 2) ** 0.5
            self.assertGreater(d(pts[-2]), 0)
            self.assertLessEqual(d(pts[-2]), d(pts[-3]), f"{route['route_id']} overshoots Hadi Chattar")

    def test_simulation_stops_at_final_destination(self):
        """A simulated trip drives to Hadi Chattar once and parks there (no loop back)."""
        from unittest import mock
        from config import AppConfig
        import services.tracking_service as ts_module
        dest = AppConfig.FINAL_DESTINATION
        with mock.patch.object(ts_module.time, "sleep", lambda *_: None):
            self.assertTrue(self.tracking_service.start_bus_simulation("KU-BUS-03"))
            thread = self.tracking_service._simulation_threads["KU-BUS-03"]
            thread.join(timeout=10)
        bus = self.tracking_service.get_bus_by_id("KU-BUS-03")
        try:
            self.assertFalse(thread.is_alive())
            self.assertAlmostEqual(bus.current_latitude, dest["latitude"], places=5)
            self.assertAlmostEqual(bus.current_longitude, dest["longitude"], places=5)
            self.assertEqual(bus.trip_status, "ARRIVED")
            self.assertFalse(bus.is_simulating)
        finally:
            self.tracking_service.set_trip_status("KU-BUS-03", False)

    def test_backend_bus_setup_crud(self):
        """Admin can add, edit and delete buses; unsafe deletes are refused."""
        # Add
        resp = self.client.post("/api/admin/buses", json={
            "bus_number": "KU Bus #05", "bus_name": "Rupsha Express",
            "license_plate": "Khulna-Cha 11-6001", "assigned_route_id": "KU-R01", "capacity": 40
        })
        self.assertEqual(resp.status_code, 200, resp.get_json())
        bus = resp.get_json()["bus"]
        bus_id = bus["bus_id"]
        try:
            self.assertNotIn(bus_id, ["KU-BUS-01", "KU-BUS-02", "KU-BUS-03", "KU-BUS-04"])
            self.assertTrue(bus["color_hex"].startswith("#"))
            ids = [b["bus_id"] for b in self.client.get("/api/buses").get_json()["buses"]]
            self.assertIn(bus_id, ids)

            # Bad input is rejected with a message, not a crash
            self.assertEqual(self.client.post("/api/admin/buses", json={"bus_number": ""}).status_code, 400)
            self.assertEqual(self.client.post("/api/admin/buses", json={"bus_number": "X", "assigned_route_id": "NOPE"}).status_code, 400)
            self.assertEqual(self.client.put(f"/api/admin/buses/{bus_id}", json={"color_hex": "red"}).status_code, 400)

            # Edit
            resp = self.client.put(f"/api/admin/buses/{bus_id}", json={"assigned_route_id": "KU-R02", "color_hex": "#16a34a"})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.get_json()["bus"]["assigned_route_id"], "KU-R02")
            self.assertEqual(resp.get_json()["bus"]["color_hex"], "#16A34A")

            # Can't delete while live
            self.tracking_service.set_trip_status(bus_id, True, "EN_ROUTE")
            self.assertEqual(self.client.delete(f"/api/admin/buses/{bus_id}").status_code, 400)
            self.tracking_service.set_trip_status(bus_id, False)

            # Can't delete a bus that still has a driver
            self.assertEqual(self.client.delete("/api/admin/buses/KU-BUS-01").status_code, 400)

            # Delete
            self.assertEqual(self.client.delete(f"/api/admin/buses/{bus_id}").status_code, 200)
            self.assertIsNone(self.tracking_service.get_bus_by_id(bus_id))
        finally:
            if self.tracking_service.get_bus_by_id(bus_id):
                self.tracking_service.set_trip_status(bus_id, False)
                self.tracking_service.delete_bus(bus_id)

    def test_driver_setup_shows_driver_on_bus(self):
        """Assigning a driver to a bus in Driver Setup shows that driver on the bus."""
        resp = self.client.put("/api/admin/drivers/DRV-03", json={"assigned_bus_id": "KU-BUS-03"})
        self.assertEqual(resp.status_code, 200)
        bus = self.client.get("/api/buses/KU-BUS-03").get_json()["bus"]
        self.assertEqual(bus["driver_id"], "DRV-03")

    def test_bus_that_passed_stop_does_not_count_down(self):
        """A bus that already went past the student's stop gives no ETA and no alert."""
        ts = self.tracking_service
        try:
            for b in ("KU-BUS-01", "KU-BUS-04"):
                ts.set_trip_status(b, False)
            # Bus #01 near Labanchara Ghat, i.e. past Malabotha More (stop 1) heading to KU
            ts.update_bus_location("KU-BUS-01", 22.7935, 89.5695, 30.0, None)
            alert = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More").get_json()["alert"]
            self.assertEqual(alert["urgency_level"], "PASSED")
            self.assertIsNone(alert["eta_minutes"])
            self.assertFalse(alert["is_alert_triggered"])

            # ...but a later stop on the route still gets a normal ETA
            alert = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=PTI%20More").get_json()["alert"]
            self.assertIsNotNone(alert["eta_minutes"])
        finally:
            ts.set_trip_status("KU-BUS-01", False)

    def test_teacher_and_student_buses_are_separate(self):
        """A bus is for students or teachers; each side only sees its own buses."""
        self.assertEqual(self.client.put("/api/admin/buses/KU-BUS-04", json={"audience": "teacher"}).status_code, 200)
        try:
            self.assertEqual(self.client.put("/api/admin/buses/KU-BUS-04", json={"audience": "staff"}).status_code, 400)
            students = [b["bus_id"] for b in self.client.get("/api/buses?audience=student").get_json()["buses"]]
            teachers = [b["bus_id"] for b in self.client.get("/api/buses?audience=teacher").get_json()["buses"]]
            self.assertNotIn("KU-BUS-04", students)
            self.assertEqual(teachers, ["KU-BUS-04"])

            # Student map page only carries student buses
            student_page = self.app.test_client().get("/student/dashboard").get_data(as_text=True)
            self.assertNotIn("KU-BUS-04", student_page)

            # Teachers sign in first, then see teacher buses only
            teacher = self.app.test_client()
            self.assertEqual(teacher.get("/teacher/dashboard").status_code, 302)
            self.assertEqual(teacher.post("/api/auth/teacher/login", json={"full_name": "", "teacher_id": "T1"}).status_code, 400)
            self.assertEqual(teacher.post("/api/auth/teacher/login", json={"full_name": "Dr. Nasrin", "teacher_id": "T-101"}).status_code, 200)
            page = teacher.get("/teacher/dashboard").get_data(as_text=True)
            self.assertIn("KU-BUS-04", page)
            self.assertNotIn("KU-BUS-01", page)

            # Arrival checks only use that side's buses
            self.tracking_service.update_bus_location("KU-BUS-04", 22.7740, 89.5845, 30.0, None)
            self.tracking_service.set_trip_status("KU-BUS-01", False)
            alert = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More&audience=student").get_json()["alert"]
            self.assertEqual(alert["bus_id"], "KU-BUS-01")
            alert = self.client.get("/api/notification/check?route_id=KU-R01&stop_name=Malabotha%20More&audience=teacher").get_json()["alert"]
            self.assertEqual(alert["bus_id"], "KU-BUS-04")
            alert = self.client.get("/api/notification/check?route_id=KU-R03&stop_name=Dumuria&audience=teacher").get_json()["alert"]
            self.assertIsNone(alert)   # no teacher bus on that route
        finally:
            self.tracking_service.set_trip_status("KU-BUS-04", False)
            self.client.put("/api/admin/buses/KU-BUS-04", json={"audience": "student"})

    def test_live_stream_pushes_bus_changes_immediately(self):
        """Open maps get bus changes pushed at once (no polling delay)."""
        import json as _json
        import threading
        import time as _time

        # The stream sends the current buses straight away, for the right riders only
        resp = self.client.get("/api/buses/stream?audience=student", buffered=False)
        chunks = iter(resp.response)
        first = next(chunks).decode()
        self.assertIn("retry:", first)
        data = next(chunks).decode()
        self.assertTrue(data.startswith("data: "))
        payload = _json.loads(data[len("data: "):])
        self.assertTrue(all(b["audience"] == "student" for b in payload["buses"]))
        resp.close()

        # A waiting stream wakes up as soon as a bus moves
        ts = self.tracking_service
        version = ts.get_version()
        threading.Timer(0.2, lambda: ts.update_bus_location("KU-BUS-02", 22.9, 89.48, 20.0, None)).start()
        started = _time.monotonic()
        new_version = ts.wait_for_change(version, timeout=5)
        waited = _time.monotonic() - started
        try:
            self.assertGreater(new_version, version)
            self.assertLess(waited, 1.5)
        finally:
            ts.set_trip_status("KU-BUS-02", False)


if __name__ == "__main__":
    unittest.main()
