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
   Shows the logo, app name, university and one button per user type (Driver first).
   Libraries : Flask (page + URL), Jinja (HTML template, part of Flask)
   Functions : controllers/view_controller.py: landing()
               templates/landing.html, templates/_ui.html: logo(), icon()
               app.py: content_for_templates()  - gives every page the content/ settings
   Settings  : content/branding.py, content/user_types.py, content/colors.py

2. SIGN-IN
   a) Student / teacher (and any type in user_types.py): name + ID, no password.
      Libraries : Flask (session cookie), Flask-SQLAlchemy (remembers the rider), Flask-Limiter
      Functions : view_controller.py: rider_login()  -> page templates/student_login.html
                  auth_controller.py: rider_login()  -> checks the form, starts the session
                  services/store.py: record_rider()  -> saves the rider for the backend's Users tab
   b) Driver: name (with suggestions) + route + PIN. One phone at a time.
      Libraries : Werkzeug (check_password_hash for the PIN), Flask-Limiter, secrets (session token)
      Functions : view_controller.py: driver_login()  -> page templates/driver_login.html
                  auth_controller.py: search_drivers() (name suggestions), driver_login()
                  services/user_service.py: UserService.sign_in(), find_driver(), touch(), sign_out()
                  models/user.py: DriverUser.check_pin(), set_pin()
   c) Admin (/backend/login): username + password from .env.
      Libraries : hmac.compare_digest (safe compare), Flask-Limiter
      Functions : admin_controller.py: login_page(), auth_controller.py: admin_login(), admin_logout()
   All sign-ins: auth_controller.py: _start_fresh_session() (new session, keeps the CSRF token)
   Settings  : content/rules.py (PIN length, login limits, DRIVER_LOCK_MINUTES),
               content/words/login_pages.py, content/words/backend_login.py

3. DRIVER SHARES GPS
   The driver's phone sends its position about once a second while Online.
   Libraries : Browser Geolocation API (navigator.geolocation.watchPosition), Wake Lock API,
               fetch() + CSRF header (static/js/common.js)
   Functions : static/js/driver_tracker.js: DriverApp.startGps(), onPosition(), sendFix(),
               flushPending(), setOnline(), goOffline(), onGpsError(), requestWakeLock()
               controllers/bus_controller.py: start_trip(), driver_location(), stop_trip()
               controllers/helpers.py: driver_required() (only the driver's own bus can move)
               services/tracking_service.py: TrackingService.start_trip(), update_location(),
               stop_trip(), _update_next_stop(), _add_trail_point()
   Settings  : content/rules.py (GPS_SEND_EVERY_SECONDS, GPS_SEND_AFTER_METERS)

3b. PRECISE SPEED (0 km/h when the bus stands still)
   A parked phone's GPS wobbles a few metres every second; dividing that by one second used to
   show 4-15 km/h. Now the phone sends each fix with its accuracy and time, and the server:
     - ignores fixes less exact than GPS_IGNORE_ACCURACY_M,
     - fits a straight line through the last SPEED_WINDOW_SECONDS of fixes (least squares),
       so the wobble averages out and only the real movement is left,
     - shows 0 km/h and keeps the marker still while that movement stays inside the wobble
       circle (SPEED_STOPPED_RADIUS_M, or 1.5 x the GPS accuracy); two moving fixes in a row
       are needed to start again,
     - uses the phone's own Doppler speed while moving (most exact), else the fitted speed,
     - shows speeds under SPEED_MIN_KMH as 0, smooths the number, and shows 0 when the phone
       has sent nothing for SPEED_STALE_SECONDS.
   Libraries : Python statistics + math (least-squares fit), Geolocation API (coords.speed,
               coords.accuracy, position.timestamp)
   Functions : services/speedometer.py: Speedometer.update(), _velocity(), _fix_time()
               tracking_service.py: update_location(), _speedometer(); models/bus.py: Bus.shown_speed()
               driver_tracker.js: DriverApp.onPosition() (sends accuracy_m and fix_time)
   Settings  : content/rules.py (SPEED_STOPPED_RADIUS_M, SPEED_WINDOW_SECONDS, SPEED_MIN_KMH,
               GPS_IGNORE_ACCURACY_M, SPEED_STALE_SECONDS)
   Check     : tests/test_speed.py

3c. BACKGROUND GPS (screen off) WITH THE TRACCAR CLIENT APP
   Phones pause GPS in web pages when the screen locks. The free Traccar Client app (Android /
   iPhone) keeps sending in the background and stores positions while offline. The admin opens
   Drivers > "Background GPS" for a driver: it shows the Server URL (https://<site>/api/tracker)
   and the driver's secret Device identifier to type into the app. Each position then moves the
   driver's bus like the driver page does; the bus goes online with the first position and goes
   offline by itself after AUTO_OFFLINE_MINUTES without GPS.
   Libraries : Traccar Client app (OsmAnd protocol, query style or JSON), Flask-Limiter, secrets
   Functions : controllers/tracker_controller.py: receive_position()
               services/tracker_service.py: TrackerService.key_for(), driver_for(), forget(), load();
               parse_fix() (both request styles), _timestamp()
               admin_controller.py: driver_tracker(); admin.js: openTrackerModal(), renewTrackerKey(),
               copyTracker(); tracking_service.py: start_auto_offline()
               models/records.py: TrackerKeyRecord (table tracker_keys)
   Settings  : content/rules.py (AUTO_OFFLINE_MINUTES, TRACKER_LIMIT), content/words/backend.py
   Check     : tests/test_tracker.py

3d. BACKEND LIVE MAP
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
               google_maps_helper.js: BusFeed (connect, apply, poll, merge), RoadLine.pointAt(),
               GoogleMapsHelper.track(), targetOf(), startAnimation(), drawFrame(), noteServerTime()
               student_tracker.js / driver_tracker.js: startLiveStream() (driver: map follows the bus)
   Settings  : content/rules.py (ROUTE_SNAP_METERS, MAP_REFRESH_SECONDS = fallback when the stream is down)
   Check     : tests/test_live.py
   Note      : phones stop GPS in web pages while the screen is off or the browser is in the
               background - the driver must keep BusPlus open on screen (it keeps the screen awake).
               Such a bus turns grey on the maps after 30 s without GPS.

5. THE MAP: TILES, BUS MARKERS, ROUTE LINES, RED TRAILS
   Libraries : Leaflet 1.9.4 (static/vendor/leaflet), Google Maps tile servers (pictures)
   Functions : static/js/google_maps_helper.js: GoogleMapsHelper.initMap(), addLayerSwitcher(),
               switchLayer(), updateActiveBuses(), updateBusMarker(), glideMarker() (smooth
               movement), busPopupHtml(), updateTrails(), drawRoutes(), showRoutes(), fitToPoints()
               models/route_paths.py (built-in road lines), tracking_service.py: _bus_dict() (adds trail)
   Trail gaps: a jump longer than TRAIL_FILL_GAP_METERS (phone locked, no signal) is filled along the
               route line (tracking_service.py: _add_trail_point()), or off the route by the road router
               in the background (_fill_gap_by_road()) - never a straight line across.
   Settings  : content/map_settings.py (MAP_CENTER, MAP_START_ZOOM, MAP_LAYERS, MAP_CREDIT),
               content/colors.py (THEME "bus_trail"), content/rules.py (TRAIL_MIN_STEP_KM, TRAIL_MAX_POINTS, TRAIL_FILL_GAP_METERS),
               content/words/map.py

6. STUDENT / TEACHER MAP: CHOOSE A ROUTE OR A BUS
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
   Admin sets each route's buses for every day of the week; riders and drivers see TODAY only.
   Morning trips show the time the bus reaches campus, afternoon trips the time it leaves.
   Libraries : Flask-SQLAlchemy (table route_timetables, JSON column), zoneinfo + tzdata
               ("today" in Bangladesh time)
   Functions : services/schedule_service.py: today_key(), todays_schedules(), all_timetables(),
               save_timetable(), _clean_trips(), delete_timetable(), seed_timetables()
               route_controller.py: list_schedules()       (riders / drivers)
               admin_controller.py: save_schedule()        (backend)
               static/js/schedule.js: BusSchedule.open(), render(), clock()   (pop-up)
               static/js/admin.js: openScheduleModal(), showScheduleDay(), addTripRow(),
               storeScheduleDay(), updateDayCounts(), busOptions()   (backend editor)
               templates/_schedule_popup.html
   Settings  : content/starting_data.py (SCHEDULES for a new database),
               content/words/bus_schedule.py (words, DAY_NAMES, MONTH_NAMES)

9. DRIVER'S DUTY CARD
   Which bus and route to drive today; a "Changed today" badge when the admin changed it.
   Functions : bus_controller.py: driver_assignment(), driver_assignment_seen(), _local_date()
               user_service.py: mark_duty_changed(), mark_duty_seen()
               admin_controller.py: update_bus() (route change -> mark_duty_changed)
               driver_tracker.js: loadDuty(), renderDuty(), markDutySeen()
   Settings  : content/words/driver_map.py, content/words/server_messages.py

10. BACKEND (ADMIN PANEL, /backend)
   Tabs: Drivers, Routes, Buses, Schedules, Users.
   a) Drivers  : admin_controller.py: create_driver(), update_driver(), unlock_driver(),
                 delete_driver(), _clean_driver_form(); user_service.py: create_driver(),
                 update_driver(), delete_driver(), unlock(), name_taken()
                 admin.js: openDriverModal(), unlockDriver(), deleteDriver()
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
   e) Users    : students / teachers who opened the map: store.py: list_riders()
   Page        : admin_controller.py: require_admin() (guards every backend URL), portal()
                 templates/admin_dashboard.html, static/js/admin.js: switchTab(), api(), toast()
   Settings    : content/words/backend.py, content/rules.py (DEFAULT_BUS_SEATS, MAX_BUS_SEATS,
                 TEST_DRIVE_SPEED, PIN length), content/colors.py (BUS_COLORS, ROUTE_COLORS)

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
               static/js/common.js: window.words()  (JavaScript: RT("..."), DT, MT, ST, AT)
               app.py: content_for_templates(), _tab_title()
   Check     : tests/test_words.py - every text the code uses is in the words files, no unused lines

13. LOOK: LOGO, COLOURS, ICONS
   Functions : templates/_ui.html: logo(), icon() (line icons drawn in SVG)
               templates/_theme.html (THEME colours -> CSS variables --bp-brand, --bp-text, ...)
               view_controller.py: favicon() (browser-tab icon made from the logo emoji)
               static/css/*.css (common, landing, student, driver, schedule, admin)
   Settings  : content/branding.py (LOGO_EMOJI, names, tab titles), content/colors.py (THEME),
               content/user_types.py ("icon", "color")

14. SECURITY
   CSRF tokens on every change ..... Flask-WTF CSRFProtect (extensions.py), common.js (adds X-CSRFToken)
   Login rate limits ............... Flask-Limiter (extensions.py, @limiter.limit in auth_controller.py)
   HTTPS + security headers ........ flask-talisman: CSP, HSTS, Permissions-Policy (app.py)
   Real visitor IP behind nginx .... Werkzeug ProxyFix (app.py)
   PINs stored only as hashes ...... Werkzeug generate_password_hash / check_password_hash (models/user.py)
   One phone per driver ............ secrets.token_hex session token + user_service.py: sign_in(), touch()
   Drivers move only their bus ..... helpers.py: driver_required()
   Backend for admin only .......... admin_controller.py: require_admin()
   No HTML injection ............... Jinja auto-escaping; JS escapeHtml() / textContent
   Strong secrets in production .... config.py: Config.check_production()
   Errors as JSON, not stack traces  app.py: _register_error_handlers()

15. SAVING DATA
   SQLite file instance/busplus.db through Flask-SQLAlchemy.
   Tables    : models/records.py: RouteRecord, BusRecord, DriverRecord, RiderRecord, TimetableRecord
   Functions : services/store.py: save(), delete(), all_rows(), seed_defaults(), record_rider()
               TrackingService.load(), UserService.load() (database -> memory at start)
   In memory only: live GPS, speed, trails (they come back with the next GPS update).

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
  Werkzeug 3.1 ......... Flask's base. generate_password_hash / check_password_hash (models/user.py),
                         ProxyFix (app.py), the auto-reloader (python app.py).
  Flask-SQLAlchemy 3.1 . database layer: extensions.py (db), models/records.py (tables),
  SQLAlchemy 2.1         services/store.py (save / read), schedule_service.py.
  Flask-WTF 1.3 ........ CSRFProtect (extensions.py); token in templates/base.html meta tag.
  Flask-Limiter 4.1 .... login and search rate limits (auth_controller.py), limits in content/rules.py.
  flask-talisman 1.1 ... security headers, HTTPS redirect, secure cookies (app.py).
  python-dotenv 1.2 .... reads .env into settings (config.py).
  requests 2.34 ........ calls the OSRM road router (services/road_router.py: road_path()).
  tzdata ............... time-zone data for zoneinfo("Asia/Dhaka") (services/geo.py: local_now()).
  gunicorn 26 + gevent . production web server (gunicorn.conf.py, wsgi.py). Linux only.
  pytest, ruff ......... tests (tests/) and code style checks (requirements-dev.txt, pyproject.toml).

PYTHON STANDARD LIBRARY
  math ......... haversine distance, bearing (services/geo.py), speed fit (services/speedometer.py)
  statistics ... average / median of recent GPS fixes (services/speedometer.py)
  difflib ...... forgiving stop-name matching (models/route.py: get_stop_by_name())
  threading .... live-feed signal (Condition) and test drives (tracking_service.py)
  secrets ...... random session tokens and secret keys (user_service.py, config.py)
  hmac ......... constant-time admin password check (auth_controller.py)
  zoneinfo ..... Bangladesh time (services/geo.py)
  json, re, string, importlib, datetime, pathlib - small jobs across the code
                 (string.Formatter fills {blanks} in services/words.py)

BROWSER
  Leaflet 1.9.4 ......... maps: static/vendor/leaflet, used by google_maps_helper.js and admin.js
  Google Maps tiles ..... map pictures, URLs in content/map_settings.py (MAP_LAYERS)
  OSRM (OpenStreetMap) .. road router behind the route editor (called by the server, not the browser)
  Inter font ............ static/vendor/inter
  Geolocation API ....... driver GPS (driver_tracker.js), "Locate me" (student_tracker.js)
  EventSource ........... live bus feed (both map pages)
  Wake Lock API ......... keeps the driver's screen on
  Web Audio API ......... arrival chime
  Notification API ...... system notification for arrival alerts
  localStorage .......... Home stop, alert settings, driver view, login name on this phone
  fetch() ............... every call to the server (common.js adds the CSRF token)


======================================================================
PART 3. WEB ADDRESSES
======================================================================

PAGES
  GET  /                          view_controller.landing()           start page
  GET  /driver/login              view_controller.driver_login()      driver sign-in
  GET  /driver/dashboard          view_controller.driver_dashboard()  driver's map
  GET  /<type>/login              view_controller.rider_login()       e.g. /student/login
  GET  /<type>/dashboard          view_controller.rider_dashboard()   e.g. /teacher/dashboard
  GET  /backend/login             admin_controller.login_page()       admin sign-in
  GET  /backend                   admin_controller.portal()           admin panel
  GET  /backend/logout            auth_controller.admin_logout()
  GET  /favicon.svg               view_controller.favicon()           browser-tab icon
  GET  /health                    view_controller.health()            "is it running?" check
  GET/POST /api/tracker           tracker_controller.receive_position()  background GPS (Traccar Client)

SIGN-IN API
  POST /api/auth/admin/login      auth_controller.admin_login()
  POST /api/auth/driver/login     auth_controller.driver_login()
  POST /api/auth/<type>/login     auth_controller.rider_login()
  POST /api/auth/logout           auth_controller.logout()
  GET  /api/drivers/search?q=     auth_controller.search_drivers()

MAP API (public)
  GET  /api/buses[?audience=]     bus_controller.list_buses()
  GET  /api/buses/stream          bus_controller.stream_buses()       live feed (Server-Sent Events)
  GET  /api/routes                route_controller.list_routes()
  GET  /api/schedules             route_controller.list_schedules()   today's bus schedule
  GET  /api/notification/check    route_controller.check_arrival()    arrival alert

DRIVER'S PHONE API (signed-in driver only)
  POST /api/driver/trip/start     bus_controller.start_trip()
  POST /api/driver/location       bus_controller.driver_location()
  POST /api/driver/trip/stop      bus_controller.stop_trip()
  GET  /api/driver/assignment     bus_controller.driver_assignment()
  POST /api/driver/assignment/seen  bus_controller.driver_assignment_seen()

BACKEND API (admin only)
  POST/PUT/DELETE /api/admin/drivers[/<id>]      create_driver(), update_driver(), delete_driver()
  POST            /api/admin/drivers/<id>/unlock unlock_driver()
  POST/PUT/DELETE /api/admin/buses[/<id>]        create_bus(), update_bus(), delete_bus()
  POST            /api/admin/buses/<id>/simulate simulate_bus()
  POST/PUT/DELETE /api/admin/routes[/<id>]       create_route(), update_route(), delete_route()
  POST            /api/admin/road-path           snap_to_roads()
  PUT             /api/admin/schedules/<route>   save_schedule()
  POST            /api/admin/drivers/<id>/tracker driver_tracker()  (Traccar Client settings / new key)


======================================================================
PART 4. THE CONTENT FOLDER - WHERE EACH SETTING IS USED
======================================================================

  branding.py        APP_NAME, UNIVERSITY_NAME, LOGO_EMOJI, TAB_TITLE
                     -> app.py: content_for_templates(), _tab_title(); templates/_ui.html: logo();
                        view_controller.favicon(); config.py
  colors.py          THEME -> templates/_theme.html (CSS variables), map trail colour (APP_CONFIG)
                     BUS_COLORS, ROUTE_COLORS -> tracking_service.py: _first_unused()
  user_types.py      RIDER_TYPES, DRIVER -> models/rider_types.py -> start page, sign-in pages,
                     maps, backend Buses / Users tabs
  map_settings.py    MAP_CENTER, MAP_START_ZOOM, MAP_LAYERS, MAP_CREDIT, DEFAULT_HOME
                        -> templates/_map_assets.html (window.APP_CONFIG) -> google_maps_helper.js,
                           student_tracker.js
                     FINAL_DESTINATION -> config.py -> models/route.py, tracking_service.py
                     TIMEZONE -> services/geo.py: local_now();  COUNTRY_BOUNDS -> geo.in_bangladesh()
  rules.py           PIN_* -> admin_controller.py, login pages;  DRIVER_LOCK_MINUTES -> config.py -> auth_controller.driver_login()
                     GPS_* , MAP_REFRESH_SECONDS -> APP_CONFIG -> driver_tracker.js, student_tracker.js
                     DEFAULT_BUS_SEATS, MAX_BUS_SEATS, TEST_DRIVE_SPEED, TRAIL_* -> tracking_service.py
                     DEFAULT_ALERT_MINUTES, MAX_ALERT_MINUTES -> rider map;  *_LOGIN_LIMIT -> auth_controller.py
                     SPEED_*, GPS_IGNORE_ACCURACY_M -> services/speedometer.py, models/bus.py
  starting_data.py   ROUTES, BUSES, DEMO_DRIVERS, SCHEDULES -> models/seed_data.py, schedule_service.py
                     (only when the database is new / empty)
  words/*.py         WORDS -> services/words.py -> templates ({{ t(...) }}), JavaScript (window.WORDS),
                     server messages (say(...)).  bus_schedule.py also has DAY_NAMES, MONTH_NAMES.


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
    portal()  [GET /backend] The admin panel with the Drivers, Routes, Buses and Users tabs.
    _clean_driver_form()  Check the driver form. Returns (clean_fields, error_message). When editing, a missing or empty PIN keeps the current PIN.
    create_driver()  [POST /api/admin/drivers] Add a driver. Body: {full_name, pin, assigned_bus_id, phone?}.
    update_driver()  [PUT /api/admin/drivers/<driver_id>] Edit a driver; also moves their name onto their (new) bus.
    unlock_driver()  [POST /api/admin/drivers/<driver_id>/unlock] Free a driver account that is stuck on another phone.
    delete_driver()  [DELETE /api/admin/drivers/<driver_id>] Remove a driver and take their name off their bus.
    driver_tracker()  [POST /api/admin/drivers/<driver_id>/tracker] The settings a driver types into the Traccar Client app for background GPS: server URL and their secret key. Body {"renew": true} makes a new key …
    create_bus()  [POST /api/admin/buses] Add a bus. Body: {bus_number, bus_name?, license_plate?, assigned_route_id, capacity?, color_hex?, audience?}.
    update_bus()  [PUT /api/admin/buses/<bus_id>] Edit a bus, or send it on another route today. Its drivers then see "Changed today".
    delete_bus()  [DELETE /api/admin/buses/<bus_id>] Delete a bus. Not allowed while it is on a live trip or still has a driver.
    simulate_bus()  [POST /api/admin/buses/<bus_id>/simulate] Test drive: move the bus along its route to Hadi Chattar without a phone. {"action": "stop"} ends it.
    snap_to_roads()  [POST /api/admin/road-path] Road line through the clicked points. Body: {"points": [[lat, lng], ...]} (2 to 60 points).
    create_route()  [POST /api/admin/routes] Add a route from the route editor (name, colour, clicked points and road line).
    update_route()  [PUT /api/admin/routes/<route_id>] Edit a route's name, colour and/or line.
    save_schedule()  [PUT /api/admin/schedules/<route_id>] Save a route's weekly timetable: per day, morning (reach campus) and afternoon (leave campus) buses.
    delete_route()  [DELETE /api/admin/routes/<route_id>] Remove a route. Refused while any bus still uses it.

controllers/auth_controller.py  -  Sign-in and sign-out for everyone.
    _start_fresh_session()  Forget any previous sign-in in this browser. Keeps the page's CSRF token (so the open page keeps working) and, unless told otherwise, the backend …
    admin_login()  [POST /api/auth/admin/login] Sign the admin in. Compares in constant time so the password can't be guessed by timing.
    admin_logout()  [GET/POST /backend/logout] Sign the admin out of the backend.
    search_drivers()  [GET /api/drivers/search] Name suggestions while a driver types on the login page: /api/drivers/search?q=raf
    driver_login()  [POST /api/auth/driver/login] Sign a driver in. Body: {"driver_id" or "driver_name", "route_id", "pin"}. The account is then locked to this phone until the driver logs out.
    rider_login()  [POST /api/auth/<rider_type>/login] Sign-in for a rider type (e.g. /api/auth/student/login): just a name and an ID. Body: {"full_name": ..., "rider_id": ...} (the older "<type>_id" key …
    logout()  [POST /api/auth/logout] Sign out. A driver also goes offline and frees the account for their next login.

controllers/bus_controller.py  -  Live buses: the public bus feed for maps, and the driver's phone API.
    list_buses()  [GET /api/buses] Every bus (or only student / teacher buses) with live position, route and trail.
    stream_buses()  [GET /api/buses/stream] Live bus feed (Server-Sent Events). The browser's EventSource keeps this open. First message: every bus ("snapshot"). After that only what moved …
    driver_location()  [POST /api/driver/location] GPS position from the driver's phone: {"latitude", "longitude", "speed_kmh"?, "heading_deg"?, "accuracy_m"?, "fix_time"? (ms since 1970)}.
    _seconds()  Phone time in milliseconds -> seconds (None stays None).
    start_trip()  [POST /api/driver/trip/start] The driver switched to Online.
    stop_trip()  [POST /api/driver/trip/stop] The driver switched to Offline: the bus disappears from every map.
    driver_assignment()  [GET /api/driver/assignment] Today's duty for the driver's bus-icon menu: which bus, which route, where it starts, and whether the admin changed it today (shown until the driver …
    driver_assignment_seen()  [POST /api/driver/assignment/seen] The driver opened the duty card: clear the "new" dot.
    _local_date()  The Bangladesh calendar date of a saved UTC timestamp (None if missing or unreadable).

controllers/helpers.py  -  Small helpers shared by the controllers (request parsing, JSON replies, sign-in checks).
    json_body()  The request's JSON body as a dict ({} if missing or not JSON).
    ok()  A successful JSON reply: {"success": true, ...}.
    fail()  A failed JSON reply with a message the page can show: {"success": false, "message": ...}.
    audience_arg()  The ?audience= query value if it is "student" or "teacher", else None (= all buses).
    optional_float()  float(value), or None when the value is missing or not a number.
    driver_required()  Only for the signed-in driver's phone. Passes the driver's own bus ID to the view as `bus_id` (taken from the account, never from the request).

controllers/route_controller.py  -  Routes and arrival alerts for the students' and teachers' map (public, read only).
    list_routes()  [GET /api/routes] Every route with its road line, stops and colour.
    list_schedules()  [GET /api/schedules] TODAY's timetable of every route for the "Bus schedule" pop-up: morning buses with the time they reach the campus, afternoon buses with the time …
    check_arrival()  [GET /api/notification/check] Arrival check for the rider's home stop.
    _best_bus_for_stop()  Which bus to watch when the rider hasn't picked one: the live bus on the route that is still coming to the stop and nearest to it; if none is live, …

controllers/tracker_controller.py  -  Background GPS from the Traccar Client app (see services/tracker_service.py).
    receive_position()  [GET/POST /api/tracker] One GPS position from Traccar Client: moves the driver's bus like the driver page does.

controllers/view_controller.py  -  The front-end pages (HTML).
    landing()  [GET /] Start page: the Driver button and one button per rider type (content/user_types.py).
    favicon()  [GET /favicon.svg] Browser-tab icon: the logo emoji on a rounded square in the brand colour (content/branding.py, colors.py).
    health()  [GET /health] Used by the deploy script and uptime monitors to check the app is running.
    _signed_in_driver()  The driver signed in on this phone, or None (also None if another phone took over).
    driver_login()  [GET /driver/login] Driver sign-in page (a driver who is still signed in goes straight to the map).
    driver_dashboard()  [GET /driver/dashboard] The driver's full-screen map. Sends anyone else back to the sign-in page.
    rider_login()  [GET /<rider_type>/login] Sign-in page of a rider type, e.g. /student/login or /teacher/login.
    rider_dashboard()  [GET /<rider_type>/dashboard] Live map of a rider type, e.g. /student/dashboard. Shows only the buses meant for that type.

services/__init__.py  -  BusPlus services: the app's logic, shared by all controllers.

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

services/speedometer.py  -  A steady, honest speed for each bus from the driver's phone GPS.
    class Reading  What the filter decided for one GPS fix.
    class Speedometer  The recent fixes of one bus and its current speed.
        .reset()  Forget everything (a new trip starts).
        .update()  Add one GPS fix and return the speed / position to show.
        ._result()  Smooth the speed, move the shown position, and build the reading.
    _clear()  True when the phone itself clearly reports driving speed.
    _clean_speed()  A speed inside 0..MAX_KMH (bad or missing values count as 0).
    _velocity()  Least-squares velocity (north, east) in m/s through the fixes [(t, lat, lng, acc), ...].
    _fix_time()  When the fix was taken, in seconds. The phone's own GPS time is best (network delays don't distort it); it is used when it is close to the server's …

services/store.py  -  Small helpers for saving to and reading from the database.
    utc_now_iso()  Current UTC time as ISO-8601 text, the format all saved dates use.
    save()  Insert or update one row (matched by primary key) and commit.
    delete()  Delete the row of `model` with primary key `key` (if it exists) and commit.
    all_rows()  Every row of a table.
    seed_defaults()  Fill an empty database with the built-in KU routes and buses (and, if asked, four demo drivers with PIN 1234). Does nothing if routes exist.
    record_rider()  Remember a student/teacher who opened the map (insert, or refresh name and last-seen time).
    list_riders()  Students and teachers, most recently seen first (for the admin's Users tab).

services/tracker_service.py  -  Background GPS for drivers, with the free Traccar Client app (Android and iPhone).
    class TrackerService  The drivers' tracker keys (one instance per process, kept in memory).
        .load()  Read the keys from the database. Called once by create_app().
        .key_for()  The driver's key; made on first use, or replaced when `renew` (the old one stops working).
        .driver_for()  The driver_id a key belongs to (None for an unknown key).
        .forget()  The driver was deleted: their key stops working.
    parse_fix()  One position from Traccar Client, in either request style, as {"key", "latitude", "longitude", "speed_kmh", "heading_deg", "accuracy_m", …
    _number()  
    _positive()  
    _timestamp()  Unix seconds / milliseconds or ISO text -> Unix seconds (None if unreadable).

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
        .show_driver_on_bus()  Show a driver on their bus (and on no other bus). bus_id=None just removes them.
        ._clean_bus_fields()  Check the bus form from the admin panel. Raises ValueError with a readable message.
        .update_location()  Record a GPS position from the driver's phone (or a test drive). Returns the bus, or None.
        ._speedometer()  The speed filter of one bus (created on first use).
        ._forget_trip()  A new trip starts (or one ended): empty trail, fresh speed and road filters.
        ._sample_time()  When a fix was taken, on the server's clock. The phone's own fix times are exact but its clock may be a little off, so they are shifted by the …
        ._route_path()  The measurable road line of a route (rebuilt when the admin changes the route).
        .start_trip()  Driver went online: the bus shows on the maps from its next GPS position.
        .start_auto_offline()  Background check, every 30 s: a live bus with no GPS for AUTO_OFFLINE_MINUTES goes offline (its phone app was switched off, the battery died ...). …
        .stop_trip()  Driver went offline (or logged out): hide the bus, clear its trail, end any test drive.
        ._update_next_stop()  Work out which stop the bus is heading for (the nearest one, or the one after it if already there).
        ._park_at_route_start()  Place an idle bus at the first point of its route.
        ._bus_dict()  A bus as JSON, with its route's name/colour and (while live) its trail.
        ._add_trail_point()  Grow the red trail behind a bus; returns the points added (sent to the open maps). Tiny GPS wobbles are skipped. A jump longer than …
        ._fill_gap_by_road()  Off the route: ask the road router for the road between two trail points, in the background.
        ._bump()  Note that something changed and wake every waiting live stream (lock must be held). bus_id: only this bus moved (trail_added = its new trail …
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

services/user_service.py  -  Driver accounts: admin setup, front-end sign-in with a one-phone lock, and daily duty notices.
    class LoginError  A driver sign-in was refused. `status` is the HTTP status code to answer with.
    class UserService  All driver accounts (one instance per process).
        .load()  (Re)load all drivers from the database. Called once by create_app().
        .all_drivers()  Every driver account.
        .get_driver()  The driver with this ID, or None.
        .find_driver()  Exact (case-insensitive) match on driver ID, full name or username. No partial matches.
        .search_drivers()  Name suggestions for the driver login page: drivers whose name/username/ID contains `query`.
        .drivers_of_bus()  Drivers whose assigned bus is `bus_id`.
        .name_taken()  True if another driver already uses this name (names must be unique to sign in by name).
        .create_driver()  Add a driver (the form is already checked by the admin controller).
        .update_driver()  Change a driver's details. Only the given fields change. A new bus counts as a duty change.
        .delete_driver()  Remove a driver account. False if it doesn't exist.
        .mark_duty_changed()  The route of this driver's bus changed: show "Changed today" on their duty card.
        .mark_duty_seen()  The driver opened their duty card: the change notice is read.
        .sign_in()  Sign a driver in with exactly what the admin set up: * their name (or username / driver ID) - exact match only * their PIN * the route of their bus …
        .touch()  Note activity from the driver's phone (keeps the lock alive). False if this phone no longer holds the account (logged out, unlocked, or taken over).
        .sign_out()  Free the account, but only if this phone is the one holding it.
        .unlock()  Admin override: free a locked account so the driver can sign in on another phone.
        ._release()  Free the account: forget the phone that held it and save.
    new_session_token()  Random token that identifies one browser session (one phone) for the driver lock.
    _parse_iso()  A saved ISO date text as a datetime (None if empty or unreadable).

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
        .shown_speed()  Speed for the maps: 0 when the phone has sent nothing for a while (content/rules.py).
        .live_dict()  Only what changes while a bus drives (sent to open maps many times a second, so kept small).
        .to_dict()  JSON form sent to the browser (no private driver details such as phone numbers).
        .from_record()  Build the in-memory bus from its database row (live state starts empty).
        .to_record()  Database row for this bus's setup (saved with `db.session.merge`).

models/records.py  -  Database tables (Flask-SQLAlchemy).
    class RouteRecord  A bus route: its name, colour, road line and named places along it.
    class BusRecord  A bus and which route it drives today.
    class DriverRecord  A driver account created by the admin. The PIN is stored only as a hash.
    class RiderRecord  A student or teacher who has opened the live map (shown to the admin).
    class TimetableRecord  The bus timetable of one route, set day by day in the backend.
    class TrackerKeyRecord  The secret "device identifier" a driver types into the Traccar Client app, so their phone can send its location in the background (screen off). See …

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

models/seed_data.py  -  Turns the starting data in content/starting_data.py into routes, buses and drivers. Used once, when the …
    default_routes()  The built-in KU routes, drawn along the real roads (see route_paths.py).
    default_buses()  The built-in KU buses (all for the first rider type, e.g. students, to begin with).
    demo_drivers()  Four demo drivers, one per bus, all with PIN 1234 (for trying the app out only).

models/user.py  -  Driver accounts.
    class DriverUser  A driver account as used while the app runs (see the module notes above).
        .is_logged_in()  True while a phone holds this account.
        .set_pin()  Store a new PIN as a salted hash.
        .check_pin()  True if `pin` is this driver's PIN (constant-time comparison inside Werkzeug).
        .to_dict()  JSON form for the admin panel and the driver's own page (never includes the PIN).
        .from_record()  Build the in-memory driver from their database row.
        .to_record()  Database row for this driver (saved with `db.session.merge`).


JAVASCRIPT (browser)
--------------------
static/js/admin.js  -  Backend admin panel (/backend): drivers, routes (map editor), buses, schedules.
    switchTab()  Shows one tab (Drivers, Routes, Buses, Schedules, Users) and remembers it for the next reload.
    openModal()  Opens a pop-up form by its id.
    closeModal()  Closes a pop-up form (and any open place suggestions).
    showFormError()  Shows a red message inside a form (empty message hides it).
    toast()  Short message at the bottom of the screen (red when isError).
    api()  Sends JSON to the server and returns its reply; a server error becomes a readable message.
    updateDriverRouteNote()  Under the bus picker in the driver form: which route that bus drives today.
    openDriverModal()  Opens the Add / Edit driver form (filled in when a driver is given).
    unlockDriver()  Frees a driver account that is stuck on another phone.
    deleteDriver()  Deletes a driver after asking to confirm.
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
    changeBusRoute()  Bus table: sends a bus on another route today (its driver sees "Changed today").
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
    openTrackerModal()  Shows the Traccar Client settings (server URL + secret key) for one driver.
    renewTrackerKey()  Replaces the driver's key (after asking): the old key stops working at once.
    copyTracker()  Copies the server URL or key to the clipboard.

static/js/common.js  -  Shared by every page, loaded first
    fetch() wrapper  adds the CSRF token (X-CSRFToken header) to every POST / PUT / DELETE
    words()  look-up function for one page's words from content/words/ (fills {blanks})

static/js/driver_tracker.js  -  BusPlus driver page: full-screen map, GPS on automatically, one bus icon with a menu
    class DriverApp  The driver page: map, GPS sending, menu, duty notification and session handling.
        readSetting()  localStorage that never throws (private mode just means nothing is remembered).
        writeSetting()  Saves a setting on this phone (ignored if storage is blocked).
        init()  Starts the page: map, menu, live feed, GPS and the duty card.
        bindMenu()  Wires up the logo button, menu buttons, online switch and log out.
        toggleMenu()  Opens or closes the menu under the logo.
        openMenu()  Opens the menu (and marks a new duty as seen).
        closeMenu()  Closes the menu.
        applyView()  Switches between "Your bus" and "All buses" and redraws the map.
        shownRouteIds()  Route lines: only for routes with a bus online (your own route while you are online).
        drawBuses()  Puts the buses for the current view, their trails and route lines on the map.
        startLiveStream()  Live bus feed pushed by the server (the 3-second poll only runs while it is down).
        handleBuses()  New bus list from the stream or the poll: redraw, and re-fit if the admin moved this bus to another route.
        setGpsState()  Updates the GPS dot on the logo and the GPS line in the menu.
        showBanner()  Shows (or hides, with empty text) the red message at the bottom.
        startGps()  Turns the trip on and starts watching the phone's GPS.
        onPosition()  New GPS fix from the phone: sends it to the server, at most about once a second.
        sendFix()  Sends one GPS position to the server.
        flushPending()  Sends the newest waiting GPS position once the last one is done.
        renderOnline()  Shows the Online / Offline switch and title.
        setOnline()  The driver flipped the switch: start or stop sharing location.
        goOffline()  Stops sharing location; the bus disappears from students' maps.
        onGpsError()  Explains why GPS stopped (blocked, no signal, unavailable).
        requestWakeLock()  Keeps the screen awake while driving (where the browser allows it).
        loadDuty()  Fetches today's duty (bus, route, start time) from the server.
        renderDuty()  Fills the duty card in the menu.
        markDutySeen()  Tells the server the driver has seen a changed duty.
        post()  POST JSON; a lost session (401/409) sends the driver back to the login page. Returns the reply or null.
        sessionLost()  Another phone took over or the sign-in ended: back to the login page.
        logout()  Stops GPS, signs out and goes to the start page.

static/js/google_maps_helper.js  -  BusPlus map helper, used by the rider map (student/teacher) and the driver map
    escapeHtml()  Makes text safe to put inside HTML (names, messages, anything from the server).
    googleTileUrl()  Google tile URL. lyrs: m = map, y = satellite with labels, "m,traffic" = map with live traffic.
    class RoadLine  A route's road line that we can measure along (same maths as services/route_geometry.py), so a bus between two GPS fixes moves ALONG the road, …
        pointAt()  {lat, lng, bearing} at `m` metres from the start of the route.
    metresBetween()  
    bearingBetween()  
    turnBetween()  Shortest turn from angle a to angle b, in degrees (-180..180).
    class BusFeed  The live bus feed for a map page. One EventSource connection: the server first sends every bus ("snapshot"), then only what moved ("delta": new …
        start()  Opens the live connection and starts the fallback timer.
        connect()  
        poll()  
        merge()  Adds what the page learnt another way (the driver's own location reply) to a known bus.
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
        frame()  
        drawFrame()  Moves one marker for this frame. The marker travels WITH the bus (the change of the predicted position since the last frame) and works off any …
        busPopupHtml()  Popup shown when a bus is tapped on the driver map.
        updateTrails()  Draws a red trail behind each given bus (bus.trail = [[lat, lng], ...]) and removes the rest. Each bus has its own trail, so buses that drove the …
        updateStudentLocationMarker()  Shows the rider's GPS position (blue pulsing dot + accuracy circle) and flies there.
        updateHomeLocationMarker()  Shows Home as a small dot (no label, no popup) and flies there. It sits below bus markers so a bus waiting at your stop can still be tapped.
        drawRoutes()  Draws every route as a coloured line (white casing underneath so it stands out on the map). Lines are created once; showRoutes() chooses which ones …
        showRoutes()  Shows only the given route lines (array of route_ids), or every route when routeIds is null.
        fitToPoints()  Zooms the map to fit the given points ([[lat, lng], ...]), keeping clear of the top bar, the bottom sheet (bottomPadding px) and a side panel …
        getRoutePoints()  All points of the given routes (all routes when routeIds is null), for fitToPoints().

static/js/schedule.js  -  "Bus schedule" pop-up (templates/_schedule_popup.html) for students, teachers and drivers
    BusSchedule()  The "Bus schedule" pop-up: open({ routeId, audience }) and close().
        clock()  "13:30" -> ["01:30", "PM"]
        make()  Creates an element with a class and plain text (never HTML).
        render()  Draws today's trips of the chosen route for the chosen part of the day.
        open()  Opens on a route (or the first one), on Morning before noon and Afternoon after.
        close()  Hides the pop-up.

static/js/student_tracker.js  -  BusPlus rider map (students and teachers; APP_DATA.audience says which)
    isWideScreen()  Screens this wide show the sheet as a fixed side panel (must match the @media rule in student.css).
    class BottomSheet  Google-Maps-style bottom sheet with three resting heights: peek (just the header), half (about half the screen) and full. Drag the handle/header, …
        onResize()  
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
        updateMenuSummaries()  Refreshes the small summary lines under "Home" and "Notification" in the main menu.
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
        setHomeAddress()  Saves the Home address (called by the page's Save button). If it matches a known stop, the Home dot moves there; otherwise the text is kept as …
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
        busDetailHtml()  Bus details: speed, next stop, route and driver.
        playProximityAlertChime()  Two-tone chime made with the Web Audio API (no sound file needed).
        triggerBrowserNotification()  System notification (only if the rider allowed notifications for this site).
        showToast()  Small pop-up under the top bar that disappears after a few seconds. type: toast-info | toast-success | toast-warning


HTML TEMPLATES (templates/)
---------------------------
    _map_assets.html        map pages: Leaflet, google_maps_helper.js and window.APP_CONFIG (map settings from content/)
    _schedule_popup.html    the "Bus schedule" pop-up (included by both map pages)
    _theme.html             browser-tab icon and THEME colours as CSS variables (included in every page's <head>)
    _ui.html                logo() and icon() macros (logo emoji tile, line icons)
    admin_dashboard.html    backend panel: Live map, Drivers, Routes, Buses, Schedules, Users tabs and their pop-ups
    admin_login.html        backend sign-in page
    base.html               shared page frame: <head>, CSRF token, common.js, window.WORDS, common.css
    driver_dashboard.html   driver's map and menu (duty card, views, schedule, online switch)
    driver_login.html       driver sign-in with name suggestions
    landing.html            start page
    student_dashboard.html  student / teacher map: top bar, menu (Home, Notification, Bus schedule), bottom sheet
    student_login.html      sign-in page for every rider type (name + ID)

STYLES (static/css/)
--------------------
    admin.css  -  Backend admin panel (/backend). Shared styles come from common.css.
    common.css  -  BusPlus shared styles, loaded on every page (including the admin page). Holds the colour/spacing variables, the page …
    driver.css  -  BusPlus driver page (templates/driver_dashboard.html). Full-screen map with a single bus icon in the corner; tapping …
    landing.css  -  Start page (templates/landing.html) and the sign-in pages (templates/driver_login.html, templates/student_login.html). …
    schedule.css  -  "Bus schedule" pop-up (templates/_schedule_popup.html) on the rider and driver maps.
    student.css  -  BusPlus rider map (templates/student_dashboard.html, for students and teachers). Full-screen map with a top bar …
