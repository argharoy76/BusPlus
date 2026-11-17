BUSPLUS - SPECS
==============
Which library and which function does each job, and in which file it lives.
Short overview: README.txt.   Change texts, colours and settings: the content/ folder.

  PART 1  Features: what each one does, which libraries and functions build it
  PART 2  Libraries: what each one does in BusPlus and where it is used
  PART 3  Web addresses (pages and API) and the function behind each
  PART 4  The content/ folder: which setting is used where
  PART 5  Every file and every function in it (one line each)

How to read a line:   file.py: function()  -  what it does
                      file.js: Class.method()


======================================================================
PART 1. FEATURES
======================================================================

1. START PAGE  (/)
   Shows the logo, app name, university and one button per rider type (Student, Teacher, Staff ...).
   Libraries : Flask (page + URL), Jinja (HTML template, part of Flask)
   Functions : controllers/view_controller.py: landing()
               templates/landing.html, templates/_ui.html: logo(), icon()
               app.py: content_for_templates()  - gives every page the content/ settings
   Settings  : content/branding.py, content/user_types.py, content/colors.py

2. SIGN-IN
   a) Student / teacher / staff (and any type in user_types.py): name + ID, no password.
      Libraries : Flask (session cookie), Flask-SQLAlchemy (remembers the rider), Flask-Limiter
      Functions : view_controller.py: rider_login()  -> page templates/student_login.html
                  auth_controller.py: rider_login()  -> checks the form, starts the session
                  services/store.py: record_rider()  -> saves the rider for the backend's Users tab
   b) Admin (/backend/login): username + password from .env.
      Libraries : hmac.compare_digest (safe compare), Flask-Limiter
      Functions : admin_controller.py: login_page(), auth_controller.py: admin_login(), admin_logout()
   All sign-ins: auth_controller.py: _start_fresh_session() (new session, keeps the CSRF token)
   Settings  : content/rules.py (login limits), content/words/login_pages.py, content/words/backend_login.py
   (There is no driver sign-in: each bus reports its own position from its GPS box, see 3.)

3. GPS BOX IN EVERY BUS (ESP32 + NEO-6M)
   A box in the bus reads the NEO-6M and POSTs the position every DEVICE_SEND_EVERY_SECONDS to
   /api/device/location, with its secret key in the "X-Device-Key" header. The server checks the
   key, checks the report (finite numbers, inside range, not 0,0, not older than
   DEVICE_MAX_FIX_AGE_SECONDS) and moves the bus the box is fitted to. The bus goes online with
   the first position and offline by itself after AUTO_OFFLINE_MINUTES without GPS.
   {"fix": false} reports (GPS still searching) only update the box's status in the backend.
   Every answer tells the box how often to send ("send_every_s"), so it can be changed without
   re-flashing.
   Libraries : ESP32 Arduino core (WiFi, HTTPClient, WiFiClientSecure), TinyGPSPlus (NMEA from the
               NEO-6M), Flask-Limiter (per-key limit), hashlib (keys stored as SHA-256), secrets
   Functions : firmware/busplus_tracker/busplus_tracker.ino: readGps(), haveFix(), buildReport(),
               sendReport(), followServerInterval(), wifiReady(), printStatus()
               controllers/device_controller.py: receive_report(), _presented_key(), _limit_per_device()
               services/device_service.py: DeviceService.by_key(), parse_report(), hash_key()
               models/device.py: GpsDevice.note_report(), status()
               services/tracking_service.py: TrackingService.start_trip(), update_location(),
               stop_trip(), start_auto_offline(), _update_next_stop(), _add_trail_point()
   Settings  : content/rules.py (DEVICE_SEND_EVERY_SECONDS, DEVICE_OFFLINE_SECONDS,
               DEVICE_MAX_FIX_AGE_SECONDS, DEVICE_LIMIT, GPS_HDOP_TO_METERS, AUTO_OFFLINE_MINUTES)
   Guide     : firmware/README.md (parts, wiring, upload, testing on your own computer)
   Test it   : tools/simulate_gps_box.py <key>   (pretends to be a box and drives the route)
   Check     : tests/test_busplus.py (GPS devices section)

3b. PRECISE SPEED (0 km/h when the bus stands still)
   A parked bus's GPS wobbles a few metres every second; dividing that by one second used to
   show 4-15 km/h. Now each fix comes with its accuracy (HDOP x GPS_HDOP_TO_METERS) and time, and
   the server:
     - ignores fixes less exact than GPS_IGNORE_ACCURACY_M,
     - fits a straight line through the last SPEED_WINDOW_SECONDS of fixes (least squares),
       so the wobble averages out and only the real movement is left,
     - shows 0 km/h and keeps the marker still while that movement stays inside the wobble
       circle (SPEED_STOPPED_RADIUS_M, or 1.5 x the GPS accuracy); two moving fixes in a row
       are needed to start again,
     - uses the GPS's own Doppler speed while moving (most exact), else the fitted speed,
     - shows speeds under SPEED_MIN_KMH as 0, smooths the number, and shows 0 when the GPS box
       has sent nothing for SPEED_STALE_SECONDS.
   Libraries : Python statistics + math (least-squares fit), TinyGPSPlus on the box (speed, HDOP, time)
   Functions : services/speedometer.py: Speedometer.update(), _velocity(), _fix_time()
               tracking_service.py: update_location(), _speedometer(); models/bus.py: Bus.shown_speed()
               device_controller.py: receive_report() (turns HDOP and GPS time into accuracy and fix time)
   Settings  : content/rules.py (SPEED_STOPPED_RADIUS_M, SPEED_WINDOW_SECONDS, SPEED_MIN_KMH,
               GPS_IGNORE_ACCURACY_M, SPEED_STALE_SECONDS)
   Check     : tests/test_speed.py

3c. BACKEND LIVE MAP
   Backend > "Live map": every online bus moving live (same smooth map as the riders'), with a
   table of speed, next stop and how old each bus's GPS is (greyed after 30 s).
   Functions : admin.js: startLiveMap(), renderLiveList(); google_maps_helper.js: BusFeed, GoogleMapsHelper
               templates/admin_dashboard.html (tab-live); admin_controller.portal() (map_center)

4. LIVE MAP UPDATES (smooth, about real time)
   Server side: every open map keeps one connection. The first message has every bus
   ("snapshot"); after that only what moved ("delta": position, speed, distance along the
   route, time measured, new trail points - a few hundred bytes). Each message is turned into
   JSON once and shared by all open maps. A ping every 15 s keeps the line open.
   On the way in, each GPS fix is: timed on the server clock, filtered (feature 3b), put on the
   road when within ROUTE_SNAP_METERS, and its distance along the route smoothed.
   Browser side: each frame (60 per second) the bus's position NOW is predicted from its last
   fix, moving on along the road at its speed (max 2 s); the marker moves with the bus and
   works off any difference gently, so it glides around corners instead of jumping.
   Libraries : Server-Sent Events (EventSource), threading.Condition, gevent, requestAnimationFrame,
               Leaflet (setLatLng / addLatLng)
   Functions : bus_controller.py: stream_buses(), list_buses()
               tracking_service.py: update_location(), _sample_time(), _route_path(), _bump(),
               feed_message(), wait_for_change()
               services/route_geometry.py: RoutePath.project(), point_at(), between(); AlongTrack.update()
               google_maps_helper.js: BusFeed (connect, apply, poll), RoadLine.pointAt(),
               GoogleMapsHelper.track(), targetOf(), startAnimation(), drawFrame(), noteServerTime()
               student_tracker.js: startLiveStream(); admin.js: startLiveMap()
   Settings  : content/rules.py (ROUTE_SNAP_METERS, MAP_REFRESH_SECONDS = fallback when the stream is down)
   Check     : tests/test_live.py
   Note      : a bus whose GPS box goes quiet (tunnel, no mobile signal) turns grey on the maps after
               30 s without GPS, and goes offline after AUTO_OFFLINE_MINUTES.

5. THE MAP: TILES, BUS MARKERS, ROUTE LINES, RED TRAILS
   Libraries : Leaflet 1.9.4 (static/vendor/leaflet), Google Maps tile servers (pictures)
   Functions : static/js/google_maps_helper.js: GoogleMapsHelper.initMap(), addLayerSwitcher(),
               switchLayer(), updateActiveBuses(), updateBusMarker(), glideMarker() (smooth
               movement), busPopupHtml(), updateTrails(), drawRoutes(), showRoutes(), fitToPoints()
               models/route_paths.py (built-in road lines), tracking_service.py: _bus_dict() (adds trail)
   Trail gaps: a jump longer than TRAIL_FILL_GAP_METERS (GPS box lost signal) is filled along the
               route line (tracking_service.py: _add_trail_point()), or off the route by the road router
               in the background (_fill_gap_by_road()) - never a straight line across.
   Settings  : content/map_settings.py (MAP_CENTER, MAP_START_ZOOM, MAP_LAYERS, MAP_CREDIT),
               content/colors.py (THEME "bus_trail"), content/rules.py (TRAIL_MIN_STEP_KM, TRAIL_MAX_POINTS, TRAIL_FILL_GAP_METERS),
               content/words/map.py

6. RIDER MAP (STUDENT / TEACHER / STAFF): CHOOSE A ROUTE OR A BUS
   Bottom sheet on phones (drag up/down), side panel on computers.
   Libraries : Pointer / touch / wheel events (browser), matchMedia (phone or computer)
   Functions : static/js/student_tracker.js: BottomSheet (measure(), snapTo(), drag handlers),
               StudentTracker.attachRouteSearch(), findRoutes(), renderRouteOptions(), pickRoute(),
               selectBus(), renderSheet(), busRowHtml(), busDetailHtml(), applyMapFilter()
               controllers/view_controller.py: rider_dashboard() (only that type's buses: "audience")
               controllers/route_controller.py: list_routes()
   Settings  : content/words/rider_map.py

7. HOME STOP AND "YOUR BUS IS COMING" ALERTS
   The rider picks a Home stop and how many minutes before arrival to be alerted.
   Libraries : localStorage (saved on the phone), Web Audio API (chime, no sound file),
               Notification API (system notification), our own maths for distance / ETA
   Functions : student_tracker.js: attachHomeAddressAutocomplete(), findHomePlaces(), setHomeAddress(),
               attachMinutesInput(), setAlertLeadMinutes(), setAlertFrequency(), checkArrival(),
               getAlertTarget(), updateHomeStrip(), maybeAlert(), playProximityAlertChime(),
               triggerBrowserNotification(), showToast()
               route_controller.py: check_arrival(), _best_bus_for_stop()
               services/notification_service.py: arrival_alert()  (IDLE / PASSED / ARRIVED /
               CRITICAL / WARNING / INFO)
               services/geo.py: distance_km(), estimate_eta()
   Settings  : content/map_settings.py (DEFAULT_HOME), content/rules.py (DEFAULT_ALERT_MINUTES,
               MAX_ALERT_MINUTES), content/words/rider_map.py, content/words/server_messages.py

8. BUS SCHEDULE
   Admin sets each route's buses for every day of the week; riders see TODAY only.
   Morning trips show the time the bus reaches campus, afternoon trips the time it leaves.
   Libraries : Flask-SQLAlchemy (table route_timetables, JSON column), zoneinfo + tzdata
               ("today" in Bangladesh time)
   Functions : services/schedule_service.py: today_key(), todays_schedules(), all_timetables(),
               save_timetable(), _clean_trips(), delete_timetable(), seed_timetables()
               route_controller.py: list_schedules()       (riders)
               admin_controller.py: save_schedule()        (backend)
               static/js/schedule.js: BusSchedule.open(), render(), clock()   (pop-up)
               static/js/admin.js: openScheduleModal(), showScheduleDay(), addTripRow(),
               storeScheduleDay(), updateDayCounts(), busOptions()   (backend editor)
               templates/_schedule_popup.html
   Settings  : content/starting_data.py (SCHEDULES for a new database),
               content/words/bus_schedule.py (words, DAY_NAMES)

9. GPS DEVICES IN THE BACKEND
   Backend > "GPS devices", top to bottom:
   a) Add a device. Manually: name + bus makes a secret key and shows it ONCE with the Server URL
      and a ready secrets.h. Automatically: Quick add (name and the first bus without a device
      filled in) or "Boxes asking to join": a box with no key POSTs /api/device/pair with its chip ID
      and a random token; the backend shows it with a 6-digit pairing code (also printed by the box);
      Approve gives it a key on its next request (once, only with the same token), Reject ignores it
      for an hour. Waiting boxes live in memory only (max 20, forgotten after 10 min of silence).
   b) Counts: devices, sending GPS now, off the map, waiting for approval, buses without a device.
   c) Connected devices: one row per box with its bus, status (Sending GPS / Searching for
      satellites / Offline / Never connected), on / off the map, satellites + HDOP, signal + power,
      firmware and last report; refreshed every 5 seconds. "Remove from map" keeps that bus off every
      map (saved: gps_devices.show_on_map; the box still reports); "Show on map" undoes it; "View live"
      opens the Live map on the bus; New key replaces the key; Delete stops it.
   A device can be moved to another bus (its old bus goes offline) or wait without a bus.
   One device per bus; a bus with a device can't be deleted.
   Libraries : secrets (key), hashlib (SHA-256: only the hash is stored), socket + ipaddress
               (suggests this computer's network address when the backend is opened on localhost)
   Functions : admin_controller.py: list_devices(), create_device(), quick_add_device(), set_device_on_map(),
               approve_box(), reject_box(), update_device(), renew_device_key(), delete_device(),
               _clean_device_form(), _device_settings(), _lan_url(), _take_bus_offline()
               device_controller.py: receive_report(), ask_to_join()
               services/device_service.py: DeviceService.create(), update(), new_key(), delete(), on_bus(),
               set_show_on_map(), ask_to_join(), waiting_boxes(), approve_box(), reject_box(); pairing_code()
               services/store.py: upgrade_tables() (adds new columns to an older database)
               models/device.py: GpsDevice.status(), to_dict(); models/records.py: GpsDeviceRecord
               admin.js: renderDevices(), renderWaitingBoxes(), refreshDevices(), setDeviceOnMap(),
               viewDeviceLive(), openDeviceModal(), renewDeviceKey(),
               deleteDevice(), showDeviceSettings(), copyText(), agoText()
   Settings  : content/rules.py (DEVICE_OFFLINE_SECONDS, DEVICE_PAIR_LIMIT), content/words/backend.py

10. BACKEND (ADMIN PANEL, /backend)
   Tabs: Live map, GPS devices, Routes, Buses, Schedules, Users.
   a) GPS devices: see feature 9. Live map: see feature 3c.
   b) Routes   : the admin clicks points on a map; the server snaps them to real roads.
                 Libraries: Leaflet (editor map), requests -> OSRM public road router
                 admin_controller.py: snap_to_roads(), create_route(), update_route(), delete_route()
                 services/road_router.py: road_path()
                 tracking_service.py: create_route(), update_route(), delete_route(),
                 _clean_route_fields(), _apply_points(); models/route.py: end_at_final_destination()
                 admin.js: openRouteModal(), ensureRouteMap(), fetchRoadPath(), drawRoute(),
                 attachPlaceSuggest(), deleteRoute()
   c) Buses    : admin_controller.py: create_bus(), update_bus(), delete_bus(), simulate_bus()
                 tracking_service.py: create_bus(), update_bus(), delete_bus(), _clean_bus_fields(),
                 start_simulation(), _drive_along() (test drive runs in a background thread)
                 admin.js: openBusModal(), changeBusRoute(), changeBusAudience(), simulateBus(), deleteBus()
   d) Schedules: see feature 8.
   e) Users    : students / teachers / staff who opened the map: store.py: list_riders()
   Page        : admin_controller.py: require_admin() (guards every backend URL), portal()
                 templates/admin_dashboard.html, static/js/admin.js: switchTab(), api(), toast()
   Settings    : content/words/backend.py, content/rules.py (DEFAULT_BUS_SEATS, MAX_BUS_SEATS,
                 TEST_DRIVE_SPEED), content/colors.py (BUS_COLORS, ROUTE_COLORS)

11. USER TYPES (add "Passenger" without code)
   One entry in content/user_types.py gives a start-page button, /<type>/login, /<type>/dashboard,
   a choice in the backend's Buses tab and an entry in its Users tab.
   Functions : models/rider_types.py: _check_rider_types() (clear error if the file has a mistake),
               rider_info(), RIDER_KEYS; view_controller.py: rider_login(), rider_dashboard();
               auth_controller.py: rider_login(); helpers.py: audience_arg()

12. EVERY TEXT EDITABLE (content/words/)
   Each page has a words file: "Original": "Shown text". The code asks for the original and shows
   the right side.
   Functions : services/words.py: words() (templates: {{ t("...") }}), say() (server messages),
               page_words() (sends a page's words to its JavaScript), fill() (puts in {blanks})
               static/js/common.js: window.words()  (JavaScript: RT("..."), MT, ST, AT)
               app.py: content_for_templates(), _tab_title()
   Check     : tests/test_words.py - every text the code uses is in the words files, no unused lines

13. LOOK: LOGO, COLOURS, ICONS
   Functions : templates/_ui.html: logo(), icon() (line icons drawn in SVG)
               templates/_theme.html (THEME colours -> CSS variables --bp-brand, --bp-text, ...)
               view_controller.py: favicon() (browser-tab icon made from the logo emoji)
               static/css/*.css (common, landing, student, schedule, admin)
   Settings  : content/branding.py (LOGO_EMOJI, names, tab titles), content/colors.py (THEME),
               content/user_types.py ("icon", "color")

14. SECURITY
   CSRF tokens on every change ..... Flask-WTF CSRFProtect (extensions.py), common.js (adds X-CSRFToken)
   Login rate limits ............... Flask-Limiter (extensions.py, @limiter.limit in auth_controller.py)
   GPS report limit per key ........ Flask-Limiter key_func=_limit_per_device (device_controller.py)
   HTTPS + security headers ........ flask-talisman: CSP, HSTS, Permissions-Policy (app.py)
   Real visitor IP behind nginx .... Werkzeug ProxyFix (app.py)
   Device keys stored only hashed .. hashlib.sha256 (device_service.py: hash_key()), shown once
   A box moves only its own bus .... device_controller.py: receive_report() (bus from the device's setup)
   Bad GPS numbers dropped ......... device_service.py: parse_report() (NaN, Infinity, ranges, 0,0, old fixes)
   Backend for admin only .......... admin_controller.py: require_admin()
   No HTML injection ............... Jinja auto-escaping; JS escapeHtml() / textContent
   Strong secrets in production .... config.py: Config.check_production()
   Errors as JSON, not stack traces  app.py: _register_error_handlers()

15. SAVING DATA
   SQLite file instance/busplus.db through Flask-SQLAlchemy.
   Tables    : models/records.py: RouteRecord, BusRecord, GpsDeviceRecord, RiderRecord, TimetableRecord
   Functions : services/store.py: save(), delete(), all_rows(), seed_defaults(), record_rider()
               TrackingService.load(), DeviceService.load() (database -> memory at start)
   In memory only: live GPS, speed, trails, each box's latest report (back with the next report).

16. DEVELOPER COMFORT
   Auto reload ......... config.py: AUTO_RELOAD -> Flask reloader + TEMPLATES_AUTO_RELOAD
   Fresh CSS/JS ........ app.py: _add_static_versions() (?v=<file time> on /static links)
   Missing library hint  app.py (friendly "pip install -r requirements.txt" message)
   Code checks ......... ruff (pyproject.toml), pytest (tests/)

17. PUTTING IT ONLINE (Hostinger VPS)
   gunicorn + gevent ... gunicorn.conf.py (1 worker, many live connections), wsgi.py
   nginx ............... deploy/nginx-busplus.conf (HTTPS, static files, live-stream settings)
   systemd ............. deploy/busplus.service (starts on boot, restarts on crash)
   certbot ............. free HTTPS certificate (deploy/setup_server.sh)
   Updates ............. deploy/update.sh (git pull, install, restart, health check)
   Backups ............. deploy/backup_db.sh (daily SQLite copy)
   GitHub Actions ...... .github/workflows/ci.yml (ruff + pytest, then SSH deploy)
   Full steps: DEPLOYMENT.md


======================================================================
PART 2. LIBRARIES
======================================================================

PYTHON (requirements.txt)
  Flask 3.1 ............ web framework: URLs (blueprints in controllers/), pages (Jinja templates),
                         sessions (signed cookies), JSON replies. Used everywhere.
  Werkzeug 3.1 ......... Flask's base. ProxyFix (app.py), the auto-reloader (python app.py).
  Flask-SQLAlchemy 3.1 . database layer: extensions.py (db), models/records.py (tables),
  SQLAlchemy 2.1         services/store.py (save / read), schedule_service.py.
  Flask-WTF 1.3 ........ CSRFProtect (extensions.py); token in templates/base.html meta tag.
  Flask-Limiter 4.1 .... login rate limits (auth_controller.py) and the per-key limit on GPS reports
                         (device_controller.py), limits in content/rules.py.
  flask-talisman 1.1 ... security headers, HTTPS redirect, secure cookies (app.py).
  python-dotenv 1.2 .... reads .env into settings (config.py).
  requests 2.34 ........ calls the OSRM road router (services/road_router.py: road_path());
                         also used by tools/simulate_gps_box.py.
  tzdata ............... time-zone data for zoneinfo("Asia/Dhaka") (services/geo.py: local_now()).
  gunicorn 26 + gevent . production web server (gunicorn.conf.py, wsgi.py). Linux only.
  pytest, ruff ......... tests (tests/) and code style checks (requirements-dev.txt, pyproject.toml).

PYTHON STANDARD LIBRARY
  math ......... haversine distance, bearing (services/geo.py), speed fit (services/speedometer.py)
  statistics ... average / median of recent GPS fixes (services/speedometer.py)
  difflib ...... forgiving stop-name matching (models/route.py: get_stop_by_name())
  threading .... live-feed signal (Condition) and test drives (tracking_service.py)
  secrets ...... random device keys and secret keys (device_service.py, config.py)
  hashlib ...... SHA-256 of the device keys (device_service.py: hash_key()) and per-key rate limits
  socket, ipaddress  this computer's network address for the device settings (admin_controller.py)
  hmac ......... constant-time admin password check (auth_controller.py)
  zoneinfo ..... Bangladesh time (services/geo.py)
  json, re, string, importlib, datetime, pathlib - small jobs across the code
                 (string.Formatter fills {blanks} in services/words.py)

BROWSER
  Leaflet 1.9.4 ......... maps: static/vendor/leaflet, used by google_maps_helper.js and admin.js
  Google Maps tiles ..... map pictures, URLs in content/map_settings.py (MAP_LAYERS)
  OSRM (OpenStreetMap) .. road router behind the route editor (called by the server, not the browser)
  Inter font ............ static/vendor/inter
  Geolocation API ....... "Locate me" on the rider map (student_tracker.js)
  EventSource ........... live bus feed (rider map and the backend's Live map)
  Web Audio API ......... arrival chime
  Notification API ...... system notification for arrival alerts
  localStorage .......... Home stop, alert settings, login name on this phone
  fetch() ............... every call to the server (common.js adds the CSRF token)

GPS BOX (firmware/busplus_tracker, Arduino IDE)
  ESP32 Arduino core .... WiFi (connects to the bus's hotspot), HTTPClient + WiFiClientSecure
                          (POSTs the reports, HTTPS), HardwareSerial (reads the NEO-6M on GPIO 16/17)
  TinyGPSPlus ........... decodes the NEO-6M's NMEA sentences: location, speed, course, satellites,
                          HDOP, date and time


======================================================================
PART 3. WEB ADDRESSES
======================================================================

PAGES
  GET  /                          view_controller.landing()           start page
  GET  /<type>/login              view_controller.rider_login()       e.g. /student/login
  GET  /<type>/dashboard          view_controller.rider_dashboard()   e.g. /teacher/dashboard
  GET  /backend/login             admin_controller.login_page()       admin sign-in
  GET  /backend                   admin_controller.portal()           admin panel
  GET  /backend/logout            auth_controller.admin_logout()
  GET  /favicon.svg               view_controller.favicon()           browser-tab icon
  GET  /health                    view_controller.health()            "is it running?" check

SIGN-IN API
  POST /api/auth/admin/login      auth_controller.admin_login()
  POST /api/auth/<type>/login     auth_controller.rider_login()
  POST /api/auth/logout           auth_controller.logout()

MAP API (public)
  GET  /api/buses[?audience=]     bus_controller.list_buses()
  GET  /api/buses/stream          bus_controller.stream_buses()       live feed (Server-Sent Events)
  GET  /api/routes                route_controller.list_routes()
  GET  /api/schedules             route_controller.list_schedules()   today's bus schedule
  GET  /api/notification/check    route_controller.check_arrival()    arrival alert

GPS BOX API (header X-Device-Key: <the device's key>)
  POST /api/device/location       device_controller.receive_report()  one report from a GPS box

BACKEND API (admin only)
  GET/POST        /api/admin/devices             list_devices(), create_device()
  PUT/DELETE      /api/admin/devices/<id>        update_device(), delete_device()
  POST            /api/admin/devices/<id>/key    renew_device_key()  (new secret key, shown once)
  POST/PUT/DELETE /api/admin/buses[/<id>]        create_bus(), update_bus(), delete_bus()
  POST            /api/admin/buses/<id>/simulate simulate_bus()
  POST/PUT/DELETE /api/admin/routes[/<id>]       create_route(), update_route(), delete_route()
  POST            /api/admin/road-path           snap_to_roads()
  PUT             /api/admin/schedules/<route>   save_schedule()


======================================================================
PART 4. THE CONTENT FOLDER - WHERE EACH SETTING IS USED
======================================================================

  branding.py        APP_NAME, UNIVERSITY_NAME, LOGO_EMOJI, TAB_TITLE
                     -> app.py: content_for_templates(), _tab_title(); templates/_ui.html: logo();
                        view_controller.favicon(); config.py
  colors.py          THEME -> templates/_theme.html (CSS variables), map trail colour (APP_CONFIG)
                     BUS_COLORS, ROUTE_COLORS -> tracking_service.py: _first_unused()
  user_types.py      RIDER_TYPES -> models/rider_types.py -> start page, sign-in pages,
                     maps, backend Buses / Users tabs
  map_settings.py    MAP_CENTER, MAP_START_ZOOM, MAP_LAYERS, MAP_CREDIT, DEFAULT_HOME
                        -> templates/_map_assets.html (window.APP_CONFIG) -> google_maps_helper.js,
                           student_tracker.js
                     FINAL_DESTINATION -> config.py -> models/route.py, tracking_service.py
                     TIMEZONE -> services/geo.py: local_now();  COUNTRY_BOUNDS -> geo.in_bangladesh()
  rules.py           DEVICE_* -> device_controller.py, models/device.py, admin_controller.py (GPS boxes)
                     GPS_HDOP_TO_METERS -> device_controller.py;  AUTO_OFFLINE_MINUTES -> tracking_service.py
                     MAP_REFRESH_SECONDS -> APP_CONFIG -> student_tracker.js
                     DEFAULT_BUS_SEATS, MAX_BUS_SEATS, TEST_DRIVE_SPEED, TRAIL_* -> tracking_service.py
                     DEFAULT_ALERT_MINUTES, MAX_ALERT_MINUTES -> rider map;  *_LOGIN_LIMIT -> auth_controller.py
                     SPEED_*, GPS_IGNORE_ACCURACY_M -> services/speedometer.py, models/bus.py
  starting_data.py   ROUTES, BUSES, SCHEDULES -> models/seed_data.py, schedule_service.py
                     (only when the database is new / empty)
  words/*.py         WORDS -> services/words.py -> templates ({{ t(...) }}), JavaScript (window.WORDS),
                     server messages (say(...)).  bus_schedule.py also has DAY_NAMES.


======================================================================
PART 5. EVERY FILE AND FUNCTION
======================================================================
(Made from the code's own comments. Names starting with _ are helpers used inside their file.)

PYTHON (server)
---------------
app.py  -  BusPlus - live bus tracker for Khulna University.
    create_app()  Build and return the BusPlus Flask app.
    _tab_title()  Browser tab title, e.g. "Student login · BusPlus" (patterns in content/branding.py).
    _add_static_versions()  Add ?v=<file's last change time> to every /static/ link, e.g. /static/js/app.js?v=1730370000.
    _register_error_handlers()  Answer API errors as JSON (the pages show the message) instead of HTML error pages.

config.py  -  BusPlus settings.
    env_bool()  Read an on/off environment variable such as `true`, `1`, `yes`, `false`, `0`.
    _local_secret()  Development helper: return a random secret kept in instance/<file_name>.
    class Config  Flask settings and BusPlus constants. `create_app()` loads this class.
        .check_production()  Stop the server from starting in production with missing or weak secrets.
    class TestConfig  Settings for the automated tests: throw-away in-memory database, no CSRF/HTTPS checks.

extensions.py  -  Flask extensions shared by the whole app.
    class Base  Base class for every database table (see models/records.py).

gunicorn.conf.py  -  gunicorn settings for the live server: gunicorn -c gunicorn.conf.py wsgi:app

wsgi.py  -  Entry point for production servers (gunicorn): `gunicorn -c gunicorn.conf.py wsgi:app`.

controllers/__init__.py  -  BusPlus controllers (Flask blueprints): each file groups the URLs of one area.

controllers/admin_controller.py  -  The backend admin panel (/backend). Only the signed-in admin can use anything here.
    require_admin()  Everything in this blueprint needs the admin. API calls get 401, pages go to the login page.
    login_page()  [GET /backend/login] The admin sign-in page (already signed-in admins go straight to the panel).
    portal()  [GET /backend] The admin panel with the Live map, GPS devices, Routes, Buses, Schedules and Users tabs.
    _clean_device_form()  Check the device form. Returns (clean_fields, error_message). An empty bus = not fitted to a bus.
    _device_settings()  What goes into the device's firmware (firmware/busplus_tracker/secrets.h).
    _lan_url()  On your own computer the page says "localhost", which an ESP32 can't reach. Then this is the same address with the computer's Wi-Fi/LAN IP instead …
    _take_bus_offline()  The device was taken off a bus: that bus stops showing as live straight away.
    list_devices()  [GET /api/admin/devices] Every device with its latest report (the GPS devices tab refreshes itself with this).
    create_device()  [POST /api/admin/devices] Add a device. Body: {name, bus_id?}. Answers with its secret key - shown this one time only.
    update_device()  [PUT /api/admin/devices/<device_id>] Rename a device or fit it to another bus. Body: {name?, bus_id?} (bus_id "" = take it off its bus).
    renew_device_key()  [POST /api/admin/devices/<device_id>/key] Make a new secret key for a device. The old key stops working at once.
    delete_device()  [DELETE /api/admin/devices/<device_id>] Remove a device: its key stops working and its bus goes offline.
    create_bus()  [POST /api/admin/buses] Add a bus. Body: {bus_number, bus_name?, license_plate?, assigned_route_id, capacity?, color_hex?, audience?}.
    update_bus()  [PUT /api/admin/buses/<bus_id>] Edit a bus, or send it on another route today.
    delete_bus()  [DELETE /api/admin/buses/<bus_id>] Delete a bus. Not allowed while it is on a live trip or still has a GPS device fitted.
    simulate_bus()  [POST /api/admin/buses/<bus_id>/simulate] Test drive: move the bus along its route to Hadi Chattar without a GPS box. {"action": "stop"} ends it.
    snap_to_roads()  [POST /api/admin/road-path] Road line through the clicked points. Body: {"points": [[lat, lng], ...]} (2 to 60 points).
    create_route()  [POST /api/admin/routes] Add a route from the route editor (name, colour, clicked points and road line).
    update_route()  [PUT /api/admin/routes/<route_id>] Edit a route's name, colour and/or line.
    save_schedule()  [PUT /api/admin/schedules/<route_id>] Save a route's weekly timetable: per day, morning (reach campus) and afternoon (leave campus) buses.
    delete_route()  [DELETE /api/admin/routes/<route_id>] Remove a route. Refused while any bus still uses it.

controllers/auth_controller.py  -  Sign-in and sign-out for everyone.
    _start_fresh_session()  Forget any previous sign-in in this browser. Keeps the page's CSRF token (so the open page keeps working) and, unless told otherwise, the backend …
    admin_login()  [POST /api/auth/admin/login] Sign the admin in. Compares in constant time so the password can't be guessed by timing.
    admin_logout()  [GET/POST /backend/logout] Sign the admin out of the backend.
    rider_login()  [POST /api/auth/<rider_type>/login] Sign-in for a rider type (e.g. /api/auth/student/login): just a name and an ID. Body: {"full_name": ..., "rider_id": ...} (the older "<type>_id" key …
    logout()  [POST /api/auth/logout] Sign out of the rider map.

controllers/bus_controller.py  -  Live buses: the public bus feed for the maps (no sign-in, read only).
    list_buses()  [GET /api/buses] Every bus (or only one rider type's buses) with live position, route and trail.
    stream_buses()  [GET /api/buses/stream] Live bus feed (Server-Sent Events). The browser's EventSource keeps this open. First message: every bus ("snapshot"). After that only what moved …

controllers/device_controller.py  -  Positions from the GPS tracker boxes (ESP32 + NEO-6M) fitted to the buses.
    _presented_key()  The key the device sent: "X-Device-Key: <key>" (or "Authorization: Bearer <key>").
    _limit_per_device()  Rate-limit each key on its own (many buses may share one mobile-network IP address).
    _answer()  
    receive_report()  [POST /api/device/location] One report from a tracker box: moves its bus on every map (or just says "still searching").

controllers/helpers.py  -  Small helpers shared by the controllers (request parsing, JSON replies).
    json_body()  The request's JSON body as a dict ({} if missing or not JSON).
    ok()  A successful JSON reply: {"success": true, ...}.
    fail()  A failed JSON reply with a message the page can show: {"success": false, "message": ...}.
    audience_arg()  The ?audience= query value if it is a rider type (student, teacher, ...), else None (= all buses).
    optional_float()  float(value), or None when the value is missing or not a number.

controllers/route_controller.py  -  Routes and arrival alerts for the students' and teachers' map (public, read only).
    list_routes()  [GET /api/routes] Every route with its road line, stops and colour.
    list_schedules()  [GET /api/schedules] TODAY's timetable of every route for the "Bus schedule" pop-up: morning buses with the time they reach the campus, afternoon buses with the time they …
    check_arrival()  [GET /api/notification/check] Arrival check for the rider's home stop.
    _best_bus_for_stop()  Which bus to watch when the rider hasn't picked one: the live bus on the route that is still coming to the stop and nearest to it; if none is live, …

controllers/view_controller.py  -  The front-end pages (HTML).
    landing()  [GET /] Start page: one button per rider type (content/user_types.py).
    favicon()  [GET /favicon.svg] Browser-tab icon: the logo emoji on a rounded square in the brand colour (content/branding.py, colors.py).
    health()  [GET /health] Used by the deploy script and uptime monitors to check the app is running.
    rider_login()  [GET /<rider_type>/login] Sign-in page of a rider type, e.g. /student/login or /teacher/login.
    rider_dashboard()  [GET /<rider_type>/dashboard] Live map of a rider type, e.g. /student/dashboard. Shows only the buses meant for that type.

services/__init__.py  -  BusPlus services: the app's logic, shared by all controllers.

services/device_service.py  -  GPS tracker boxes (ESP32 + NEO-6M) that report each bus's position. Firmware: firmware/.
    hash_key()  The stored form of a device key.
    class DeviceService  All GPS devices (one instance per process).
        .load()  (Re)load all devices from the database. Called once by create_app().
        .all_devices()  Every device, in ID order.
        .get()  The device with this ID, or None.
        .by_key()  The device a secret key belongs to (None for a missing or unknown key).
        .on_bus()  The device fitted to a bus, or None.
        .create()  Add a device. Returns (device, its new secret key). The form is checked by the admin controller.
        .update()  Rename a device and/or fit it to another bus (bus_id None with change_bus = take it off).
        .new_key()  Replace a device's key: the old key stops working at once. None if there is no such device.
        .delete()  Remove a device (its key stops working). False if it doesn't exist.
    _new_key()  
    class ReportError  A report that can't be used. The message goes back to the device (and its serial monitor).
    parse_report()  Check one report from a device and return it in BusPlus's own units.
    _float_in()  A finite number between low and high, else None (bad values are ignored, not fatal).
    _int_in()  
    _timestamp()  GPS time as ISO text ("2026-11-17T08:15:01Z") or Unix seconds -> Unix seconds (None if unreadable).

services/geo.py  -  Map maths: distances, compass directions and arrival-time estimates.
    distance_km()  Straight-line ("as the crow flies") distance between two points, in km (haversine formula).
    bearing_deg()  Compass direction from point 1 to point 2: 0 = north, 90 = east, 180 = south, 270 = west.
    path_length_km()  Total length of a line given as [{"lat": .., "lng": ..}, ...], in km.
    in_bangladesh()  True if the point is inside the rough Bangladesh box (catches typos and 0,0 positions).
    local_now()  The current time in Bangladesh (the server itself may run on UTC).
    estimate_eta()  Estimate how long a bus needs to reach a point.

services/notification_service.py  -  "Your bus is coming" alerts for students and teachers.
    arrival_alert()  How far `bus` is from `stop`, and whether to alert the rider.

services/road_router.py  -  Snap a route to real roads for the admin's route editor.
    class RoadRouterError  The road router could not be reached or found no route.
    road_path()  Driving line through `points` ([(lat, lng), ...]).

services/route_geometry.py  -  Route geometry: keep live buses on their road and measure how far along it they are.
    class Projection  Where a GPS point lands on the route.
    class RoutePath  A route's road line, ready for measuring along.
        .project()  Nearest point on the road to (lat, lng). With `near_m` (where the bus was last time), segments around it are tried first, so a road used twice (out …
        ._closest()  
        .point_at()  (lat, lng, road direction in degrees) at `progress_m` metres along the route.
        .between()  Road points strictly between two distances along the route (in travel order).
    class AlongTrack  Smoothed distance along the route (metres) and speed along it (m/s, minus = driving backwards).
        .reset()  
        .update()  Add one measurement (metres along the route at time t) and return the smoothed position.
    _metres()  
    _bearing()  

services/schedule_service.py  -  Bus schedules: one timetable per route, set day by day by the admin (Schedules tab).
    today_key()  Today's day key in Bangladesh time, e.g. "sat".
    _saved_days()  route_id -> its saved week {"sat": {"morning": [...], "afternoon": [...]}, ...}.
    todays_schedules()  Today's trips of every route for the pop-up, with each trip's bus name and colour. With `audience` (e.g. "student") trips of buses meant for another …
    all_timetables()  Every route with its full week (for the backend), days in week order, missing days empty.
    save_timetable()  Save a route's whole week from the backend. Body: {"days": {"sat": {"morning": [{"bus_id", "time"}], "afternoon": [...]}, ...}} Raises LookupError …
    delete_timetable()  Remove a route's timetable (when the route itself is deleted).
    seed_timetables()  Add the starting timetables (content/starting_data.py) once, if there are none at all.
    _clean_trips()  Check one day's morning or afternoon trips: a known bus (or none) and a valid time. Sorted by time.

services/speedometer.py  -  A steady, honest speed for each bus from its GPS box (ESP32 + NEO-6M).
    class Reading  What the filter decided for one GPS fix.
    class Speedometer  The recent fixes of one bus and its current speed.
        .reset()  Forget everything (a new trip starts).
        .update()  Add one GPS fix and return the speed / position to show.
        ._result()  Smooth the speed, move the shown position, and build the reading.
    _clear()  True when the GPS itself clearly reports driving speed.
    _clean_speed()  A speed inside 0..MAX_KMH (bad or missing values count as 0).
    _velocity()  Least-squares velocity (north, east) in m/s through the fixes [(t, lat, lng, acc), ...].
    _fix_time()  When the fix was taken, in seconds. The GPS's own time is best (network delays don't distort it); it is used when it is close to the server's clock …

services/store.py  -  Small helpers for saving to and reading from the database.
    utc_now_iso()  Current UTC time as ISO-8601 text, the format all saved dates use.
    save()  Insert or update one row (matched by primary key) and commit.
    delete()  Delete the row of `model` with primary key `key` (if it exists) and commit.
    all_rows()  Every row of a table.
    seed_defaults()  Fill an empty database with the built-in KU routes and buses. Does nothing if routes exist.
    record_rider()  Remember a student/teacher who opened the map (insert, or refresh name and last-seen time).
    list_riders()  Students and teachers, most recently seen first (for the admin's Users tab).

services/tracking_service.py  -  Routes, buses and live bus tracking.
    class TrackingService  All routes and buses, their live state, and the live-update signal (one instance per process).
        .load()  (Re)load routes and buses from the database. Called once by create_app().
        .all_routes()  Every route as JSON-ready dicts.
        .get_route()  The route with this ID, or None.
        .create_route()  Add a route from the admin's route editor. Raises ValueError with a readable message.
        .update_route()  Edit a route (name, colour and/or its line). Returns None if it doesn't exist.
        .delete_route()  Remove a route. Refused (ValueError) while any bus still uses it.
        ._clean_route_fields()  Check the route editor's form.
        ._apply_points()  Rebuild a route from the admin's points: * the line follows the road path from the editor (or straight lines if there is none) * points that have a …
        .all_buses()  Every bus (or only the student / teacher buses) as JSON-ready dicts, with its route's name and colour, and the trail of its current trip while it is …
        .get_bus()  The bus with this ID, or None.
        .buses_on_route()  Buses currently assigned to a route (optionally only those for students or teachers).
        .create_bus()  Add a bus. It waits at the start of its route. Raises ValueError on bad input.
        .update_bus()  Edit a bus. Its route can't change during a live trip. Returns None if it doesn't exist.
        .delete_bus()  Remove a bus. Refused (ValueError) while it is on a live trip.
        ._clean_bus_fields()  Check the bus form from the admin panel. Raises ValueError with a readable message.
        .update_location()  Record a GPS position from the bus's GPS box (or a test drive). Returns the bus, or None.
        ._speedometer()  The speed filter of one bus (created on first use).
        ._forget_trip()  A new trip starts (or one ended): empty trail, fresh speed and road filters.
        ._sample_time()  When a fix was taken, on the server's clock. The GPS box's own fix times are exact but its clock may be a little off, so they are shifted by the …
        ._route_path()  The measurable road line of a route (rebuilt when the admin changes the route).
        .start_trip()  The GPS box started reporting: the bus shows on the maps from its next GPS position.
        .start_auto_offline()  Background check, every 30 s: a live bus with no GPS for AUTO_OFFLINE_MINUTES goes offline (the bus was switched off, the GPS box lost power or …
        .stop_trip()  The bus went offline (GPS silent, or a test drive stopped): hide it, clear its trail, end any test drive.
        ._update_next_stop()  Work out which stop the bus is heading for (the nearest one, or the one after it if already there).
        ._park_at_route_start()  Place an idle bus at the first point of its route.
        ._bus_dict()  A bus as JSON, with its route's name/colour and (while live) its trail.
        ._add_trail_point()  Grow the red trail behind a bus; returns the points added (sent to the open maps). Tiny GPS wobbles are skipped. A jump longer than …
        ._fill_gap_by_road()  Off the route: ask the road router for the road between two trail points, in the background.
        ._bump()  Note that something changed and wake every waiting live stream (lock must be held). bus_id: only this bus moved (trail_added = its new trail points); …
        .feed_message()  What a live map that has seen `since_version` needs next: (new version, JSON text). {"type": "snapshot", "now", "trail_max", "buses": [every bus, …
        .get_version()  Current change counter (goes up by one on every bus or route change).
        .wait_for_change()  Block until something changes after `since_version` (or `timeout` seconds). Returns the new version.
        .start_simulation()  Start a background test drive from the route's start to Hadi Chattar. False if not possible.
        ._drive_along()  Background thread of a test drive: moves the bus along `line` at a steady speed, one update per tick, then parks it at the end (Hadi Chattar). Stops …
        ._next_free_id()  Next unused ID such as KU-BUS-05 (never reuses an ID that is still in use).
    _first_unused()  First colour of the palette not used yet (or the first colour if all are used).
    _clean_color()  A colour like "#2563EB", or ValueError(message) if it isn't one.
    _clean_position()  Turn a latitude/longitude pair into floats, refusing missing or out-of-country values.
    _clean_path()  Check the road line from the route editor: [[lat, lng], ...] -> [{"lat", "lng"}, ...].

services/words.py  -  The words of the website, read from the content/words/ folder.
    class _KeepUnknown  Leaves {blank} as it is when the code has no value for it.
    fill()  Put values into the {blanks} of a text. Broken braces are shown as typed.
    word()  The text the page shows for `original` (falls back to the original itself).
    words()  A t(original, **values) function for one page (used by the HTML templates).
    page_words()  The words of some pages, sent to the browser for the JavaScript (window.WORDS).
    say()  A message from the server (errors, "saved", arrival alerts): content/words/server_messages.py.

models/__init__.py  -  BusPlus data models.

models/bus.py  -  A bus: the details the admin sets up, plus where it is right now.
    class Bus  One bus: its setup (saved in the database) and its live state (memory only).
        .move_to()  Record a new GPS position. Missing speed/heading keep their previous values.
        .shown_speed()  Speed for the maps: 0 when its GPS box has sent nothing for a while (content/rules.py).
        .live_dict()  Only what changes while a bus drives (sent to open maps many times a second, so kept small).
        .to_dict()  JSON form sent to the browser.
        .from_record()  Build the in-memory bus from its database row (live state starts empty).
        .to_record()  Database row for this bus's setup (saved with `db.session.merge`).

models/device.py  -  A GPS tracker box fitted to a bus: an ESP32 with a NEO-6M GPS module (see firmware/).
    class GpsDevice  One tracker box: its setup (saved in the database) and its latest report (memory only).
        .status()  NEVER, OFFLINE, NO_FIX or ONLINE (see the constants above).
        .note_report()  Remember the health values of a report (position handling is the tracking service's job).
        .to_dict()  JSON form for the admin panel (never contains the key or its hash).
        .from_record()  Build the in-memory device from its database row (no report yet).
        .to_record()  Database row for this device's setup (saved with `db.session.merge`).
    _iso()  

models/records.py  -  Database tables (Flask-SQLAlchemy).
    class RouteRecord  A bus route: its name, colour, road line and named places along it.
    class BusRecord  A bus and which route it drives today.
    class RiderRecord  A student or teacher who has opened the live map (shown to the admin).
    class TimetableRecord  The bus timetable of one route, set day by day in the backend.
    class GpsDeviceRecord  A GPS tracker box (ESP32 + NEO-6M) fitted to a bus. See services/device_service.py.

models/rider_types.py  -  Rider types (Student, Teacher, ... ) as set in content/user_types.py, checked once at start-up.
    _check_rider_types()  Stop with a clear message if content/user_types.py has a mistake.
    rider_info()  Label, plural, id_label, icon and color of a rider type (None if there is no such type).

models/route.py  -  Routes and the named places (stops) along them.
    class BusStop  A named place on a route (for example "Malabotha More").
        .to_dict()  JSON form of the stop.
    class BusRoute  A route as drawn by the admin.
        .to_dict()  JSON form sent to the browser.
        .get_stop_by_name()  Find a stop by name, forgiving small differences.
        .end_at_final_destination()  Make sure the last stop and the last point of the line are Hadi Chattar.
        .from_record()  Build the in-memory route from its database row.
        .to_record()  Database row for this route (saved with `db.session.merge`).

models/route_paths.py  -  Road-following lines for the built-in KU routes.

models/seed_data.py  -  Turns the starting data in content/starting_data.py into routes and buses. Used once, when the database is empty (see services/store.py: …
    default_routes()  The built-in KU routes, drawn along the real roads (see route_paths.py).
    default_buses()  The built-in KU buses (all for the first rider type, e.g. students, to begin with).


JAVASCRIPT (browser)
--------------------
static/js/admin.js  -  Backend admin panel (/backend): GPS devices, routes (map editor), buses, schedules, live map.
    switchTab()  Shows one tab (Live map, GPS devices, Routes, Buses, ...) and remembers it for the next reload.
    openModal()  Opens a pop-up form by its id.
    closeModal()  Closes a pop-up form (and any open place suggestions).
    showFormError()  Shows a red message inside a form (empty message hides it).
    toast()  Short message at the bottom of the screen (red when isError).
    api()  Sends JSON to the server and returns its reply; a server error becomes a readable message.
    deviceStatusText()  What the Status column says for each device status (models/device.py).
    agoText()  "now", "12 s ago", "3 min ago", "2 h ago" for a server timestamp (seconds).
    renderDevices()  Fills the GPS devices table and its counters from gpsDevices.
    refreshDevices()  Asks the server for the devices' latest reports (only while their tab is open).
    openDeviceModal()  Opens the Add / Edit device form (filled in when a device is given).
    renewDeviceKey()  Makes a new key for a device (after asking) and shows it.
    deleteDevice()  Deletes a device after asking to confirm.
    showDeviceSettings()  The settings for the device's firmware: server URL, its key and a ready secrets.h. Shown once.
    copyText()  Copies the text of an element (URL, key, secrets.h) to the clipboard.
    routeColor()  The colour chosen in the route form.
    destLatLng()  Position of the final stop that every route ends at.
    ensureRouteMap()  Creates the route editor's map the first time it is needed.
    routeChanged()  The admin moved or added a point: fetch a new road line shortly after.
    fetchRoadPath()  Asks the server (OSRM road router) for the road line through the points.
    lengthKm()  Length of a line of points in km.
    setRouteInfo()  Status line under the route editor map (length, or a warning).
    drawRoute()  Draws the route's points and its road line (or straight lines if the road router failed).
    knownPlaces()  Every named stop of every route (for the place suggestions).
    matchPlaces()  Known places matching the typed text, best first.
    closeSuggest()  Hides the place suggestion list.
    showSuggest()  Shows place suggestions under a text box.
    pickSuggest()  Uses the chosen suggestion.
    attachPlaceSuggest()  Adds type-ahead place suggestions to a text box.
    openRouteModal()  Opens the Add / Edit route form with its map editor.
    deleteRoute()  Deletes a route after asking to confirm.
    changeBusRoute()  Bus table: sends a bus on another route today.
    changeBusAudience()  Bus table: changes who a bus is for (students, teachers, ...).
    simulateBus()  Starts or stops a test drive of a bus along its route.
    selectBusColor()  Picks a colour in the bus form.
    openBusModal()  Opens the Add / Edit bus form (filled in when a bus is given).
    deleteBus()  Deletes a bus after asking to confirm.
    busOptions()  <option>s for the bus picker: buses on this route first, then the other buses.
    storeScheduleDay()  Reads the rows on screen back into scheduleWeek for the day being edited.
    addTripRow()  Adds one trip row (bus + time) to the morning or afternoon list in the schedule form.
    updateDayCounts()  Small number on each day tab = how many buses that day (empty = no bus).
    showScheduleDay()  Shows one day of the week in the schedule form.
    openScheduleModal()  Opens a route's weekly schedule form.
    startLiveMap()  Opens the Live map the first time its tab is shown: same smooth live buses as the riders' map.
    renderLiveList()  The table next to the live map: each online bus, its speed, next stop and how old its GPS is.

static/js/common.js  -  Shared by every page, loaded first
    fetch() wrapper  adds the CSRF token (X-CSRFToken header) to every POST / PUT / DELETE
    words()  look-up function for one page's words from content/words/ (fills {blanks})

static/js/google_maps_helper.js  -  BusPlus map helper, used by the rider map (students, teachers, staff) and the admin's Live map.
    escapeHtml()  Makes text safe to put inside HTML (names, messages, anything from the server).
    class RoadLine  A route's road line that we can measure along (same maths as services/route_geometry.py), so a bus between two GPS fixes moves ALONG the road, around …
        pointAt()  {lat, lng, bearing} at `m` metres from the start of the route.
    metresBetween()  
    bearingBetween()  
    class BusFeed  The live bus feed for a map page. One EventSource connection: the server first sends every bus ("snapshot"), then only what moved ("delta": new …
        start()  Opens the live connection and starts the fallback timer.
        connect()  
        poll()  
        apply()  Merges one message from the server into the bus list.
    class GoogleMapsHelper  Everything drawn on a map; one shared instance: window.googleMapsHelper.
        initMap()  Creates the map inside containerId. options: center {lat, lng}, zoom, layerSwitcher (Map / Satellite / Traffic buttons), attribution (small "Google …
        addLayerSwitcher()  Adds the floating Map / Satellite / Traffic buttons.
        switchLayer()  Shows one tile layer ("roadmap", "satellite" or "traffic") and hides the others.
        updateActiveBuses()  Shows exactly these buses (live ones only): adds/moves their markers, removes all others.
        removeBusMarker()  Takes one bus marker off the map.
        updateBusMarker()  Adds or moves one bus marker: a circle in the bus's colour with a bus icon, a heading arrow that turns with the bus, and a speed tag underneath. A …
        noteServerTime()  Learns the server's clock from a live message ("now"), to compare with sample times.
        serverNow()  
        isStale()  
        track()  Adds a bus's latest live state as a sample for the animation.
        targetOf()  Where the bus should be right now: its last sample, carried on along the road at its speed.
        startAnimation()  
        drawFrame()  Moves one marker for this frame. The marker travels WITH the bus (the change of the predicted position since the last frame) and works off any …
        busPopupHtml()  Popup shown when a bus is tapped on the admin's Live map.
        updateTrails()  Draws a red trail behind each given bus (bus.trail = [[lat, lng], ...]) and removes the rest. Each bus has its own trail, so buses that drove the …
        updateStudentLocationMarker()  Shows the rider's GPS position (blue pulsing dot + accuracy circle) and flies there.
        updateHomeLocationMarker()  Shows Home as a small dot (no label, no popup) and flies there. It sits below bus markers so a bus waiting at your stop can still be tapped.
        drawRoutes()  Draws every route as a coloured line (white casing underneath so it stands out on the map). Lines are created once; showRoutes() chooses which ones …
        showRoutes()  Shows only the given route lines (array of route_ids), or every route when routeIds is null.
        fitToPoints()  Zooms the map to fit the given points ([[lat, lng], ...]), keeping clear of the top bar, the bottom sheet (bottomPadding px) and a side panel …
        getRoutePoints()  All points of the given routes (all routes when routeIds is null), for fitToPoints().

static/js/schedule.js  -  "Bus schedule" pop-up (templates/_schedule_popup.html) for students, teachers and staff.

static/js/student_tracker.js  -  BusPlus rider map (students and teachers; APP_DATA.audience says which).
    class BottomSheet  Google-Maps-style bottom sheet with three resting heights: peek (just the header), half (about half the screen) and full. Drag the handle/header, …
        measure()  Works out the three resting heights (px of sheet visible) for the current screen and content.
        setForceFull()  Lets the sheet open to the full screen height (while the route drop-down is open).
        setVisible()  Moves the sheet so px of it is visible; also tells the page (Locate Me button rides on top).
        refresh()  Re-measures (e.g. after the header grew or shrank) and stays at the current resting height.
        snapTo()  Moves the sheet to a resting height: "peek", "half" or "full".
        settle()  Picks the resting height closest to where a drag would carry the sheet.
        startDrag()  A drag on the sheet began.
        moveDrag()  The sheet follows the finger / mouse.
        endDrag()  Drag ended: settle at the nearest resting height.
        bindPointerDrag()  Mouse / pen / touch drag on the handle and header.
        bindContentTouch()  Touch on the list: pulling down at the top of the list lowers the sheet, and pushing up while the sheet isn't full raises it, like Google Maps.
        bindWheel()  Mouse wheel / trackpad: scroll down on the sheet to raise it, scroll up at the top to lower it.
    class StudentTracker  The rider map page: live buses, route/bus selection, Home stop and arrival alerts.
        init()  Starts the page: map, routes, live feed, menu, Home and alerts.
        syncPreferencesUi()  Fills the menu's inputs and summary lines from the saved settings (called when a menu page opens).
        getHomeDisplayName()  Name shown for Home: the typed address if the rider entered one, otherwise the stop name.
        buildHomePlaces()  Unique stops across all routes, offered as Home address suggestions.
        findHomePlaces()  Best matching places for what the rider has typed so far. Names starting with the text come first, then names containing a word that starts with it, …
        attachHomeAddressAutocomplete()  Type-ahead on the Home address box (arrow keys, Enter, Escape, tap a suggestion).
        renderHomeSuggestions()  Shows matching stops under the Home address box.
        appendHighlighted()  Writes text into el, wrapping the part that matches the typed text in <mark>.
        setActiveSuggestion()  Highlights a Home suggestion (arrow keys).
        pickHomeSuggestion()  Puts the chosen stop into the Home address box.
        hideHomeSuggestions()  Hides the Home suggestions.
        attachMinutesInput()  Notification minutes box: the rider just types a number; it is applied automatically.
        maxAlertMinutes()  Largest "notify me" minutes allowed (MAX_ALERT_MINUTES in content/rules.py).
        updateMinutesHint()  Shows, in plain words, what the typed minutes mean (or why the value isn't valid).
        setHomeAddress()  Saves the Home address (called by the page's Save button). If it matches a known stop, the Home dot moves there; otherwise the text is kept as Home's …
        setAlertLeadMinutes()  Saves how many minutes before arrival the alert should go off.
        setAlertFrequency()  Saves how often the alert repeats ("1", "2", "3" or "continuous"); called by the page's Repeat select.
        locateStudentGps()  "Locate Me": shows the rider's GPS position on the map.
        startLiveStream()  Live bus feed: the server pushes every change straight away (no waiting for the next poll). If it drops, the browser reconnects by itself and the …
        fetchLiveTrackingData()  Checks the Home arrival (the bus positions themselves come from the live feed).
        checkArrival()  Asks the server how far the watched bus is from the Home stop; updates the Home line and alerts.
        getAlertStopName()  The stop alerts are about: the rider's Home stop.
        getAlertTarget()  Which route / bus to watch for the Home stop: - a selected bus: that bus (only if its route passes the Home stop) - otherwise the selected route if …
        updateHomeStrip()  Updates the Home line in the sheet: arrival time at the Home stop, shown only while a live bus is coming.
        maybeAlert()  Fires the arrival alert (chime, pop-up, browser notification) when the bus is within the rider's minutes, as many times as the Repeat setting allows …
        loadRoutesFromBackend()  Refreshes the route list from /api/routes (includes routes the admin just added); keeps the page's copy if that fails.
        setupBottomSheet()  Creates the bottom sheet and its click handlers.
        findRoutes()  Routes whose name contains the typed letters, best matches first. Empty text = all routes.
        attachRouteSearch()  "Select route" search box: type-ahead drop-down, arrow keys, Enter, Escape and the ✕ button.
        renderRouteOptions()  Shows the routes matching the typed text in the drop-down.
        highlightHtml()  Escapes text and wraps the part matching the query in <mark>.
        setActiveRouteOption()  Highlights a route in the drop-down (arrow keys).
        closeRouteDropdown()  Hides the route drop-down.
        pickRoute()  Shows only the chosen route and its buses.
        syncRouteSearchBox()  Shows the chosen route's name (and colour) in the search box, or empties it; hides the box in bus details.
        selectBus()  Shows one bus's details and zooms to it.
        sheetGoBack()  Back from a bus's details to the list.
        afterSelectionChange()  Redraws the sheet and map after a route or bus was chosen.
        getVisibleRouteIds()  Route ids of the current selection (null = all).
        getVisibleLiveBuses()  Live buses that match the current selection.
        getShownRouteIds()  Route lines to draw: only routes with a bus online right now (within the current selection).
        refreshMapBuses()  Puts the selected live buses, their trails and route lines on the map.
        applyMapFilter()  Redraws the map for the current selection; with fit, zooms to it (clear of the sheet / side panel).
        renderSheet()  Draws the sheet list for the current selection. Skips the redraw when nothing visible changed (the list is refreshed on every update), unless force …
        busRowHtml()  One bus in the list: icon in the bus's colour (solid + green dot = live, light = offline) and its name.
        busDetailHtml()  Bus details: speed, next stop, route and seats.
        playProximityAlertChime()  Two-tone chime made with the Web Audio API (no sound file needed).
        triggerBrowserNotification()  System notification (only if the rider allowed notifications for this site).
        showToast()  Small pop-up under the top bar that disappears after a few seconds. type: toast-info | toast-success | toast-warning


GPS BOX FIRMWARE (firmware/busplus_tracker, Arduino C++ for the ESP32)
-------------------------------------------------------------------------
busplus_tracker.ino  -  Reads the NEO-6M and sends the bus's position to /api/device/location.
    setLed() / updateLed()  On-board LED: slow blink = no Wi-Fi, fast blink = no GPS fix, flash = sent.
    startWifi() / wifiReady()  Connects to the bus's hotspot and retries every 10 s when it drops.
    readGps()  Feeds every byte from the NEO-6M (Serial2, GPIO 16/17) into TinyGPSPlus.
    haveFix()  True when TinyGPSPlus has a valid position younger than MAX_FIX_AGE_MS (and not 0,0).
    buildReport()  The JSON report: fix, lat, lng, speed_kmh, course, time, sats, hdop, rssi, fw, uptime_s.
    followServerInterval()  Reads "send_every_s" from the server's answer and sends that often.
    sendReport()  POSTs one report with the X-Device-Key header (HTTPS or HTTP) and logs errors.
    printStatus()  A status line on the serial monitor every 5 s (Wi-Fi, satellites, HDOP, fix, sent).
    setup() / loop()  Start the GPS and Wi-Fi; then read the GPS non-stop and report on time.
secrets.example.h  -  Template for secrets.h: WIFI_SSID, WIFI_PASSWORD, SERVER_URL, DEVICE_KEY.

TOOLS
-----
tools/simulate_gps_box.py  -  Pretend to be a GPS box (ESP32 + NEO-6M) - for testing BusPlus without the hardware.
    main()  Sends a heartbeat, then drives the device's bus along its route, one report every send_every_s.
    points_along()  (lat, lng, course) every step_m metres along the line.
    report()  POSTs one report like the firmware does and stops with the server's message on an error.


HTML TEMPLATES (templates/)
---------------------------
    _map_assets.html        map pages: Leaflet, google_maps_helper.js and window.APP_CONFIG (map settings from content/)
    _schedule_popup.html    the "Bus schedule" pop-up (included by both map pages)
    _theme.html             browser-tab icon and THEME colours as CSS variables (included in every page's <head>)
    _ui.html                logo() and icon() macros (logo emoji tile, line icons)
    admin_dashboard.html    backend panel: Live map, GPS devices, Routes, Buses, Schedules, Users tabs and their pop-ups
    admin_login.html        backend sign-in page
    base.html               shared page frame: <head>, CSRF token, common.js, window.WORDS, common.css
    landing.html            start page
    student_dashboard.html  student / teacher map: top bar, menu (Home, Notification, Bus schedule), bottom sheet
    student_login.html      sign-in page for every rider type (name + ID)

STYLES (static/css/)
--------------------
    admin.css  -  Backend admin panel (/backend). Shared styles come from common.css.
    common.css  -  BusPlus shared styles, loaded on every page (including the admin page). Holds the colour/spacing variables, the page shell, the buttons and pop-up …
    landing.css  -  Start page (templates/landing.html) and the sign-in pages (templates/student_login.html). Each option / form takes its colour from …
    schedule.css  -  "Bus schedule" pop-up (templates/_schedule_popup.html) on the rider maps.
    student.css  -  BusPlus rider map (templates/student_dashboard.html, for students and teachers). Full-screen map with a top bar (BusPlus menu button + Log Out), a …
