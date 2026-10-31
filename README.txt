BUSPLUS - Khulna University live bus tracker
============================================

WHAT IT DOES
  Drivers share their phone's GPS; students and teachers see the buses move live on a map,
  get "your bus is coming" alerts, and the admin manages drivers, routes and buses at /backend.
  Every route ends at Hadi Chattar. Works on phones and PCs.

RUN IT
  pip install -r requirements.txt      (once, and again after the libraries change)
  python app.py                        then open http://localhost:5000
  Backend: http://localhost:5000/backend   user: admin   password: instance/admin_password.txt
  Demo drivers (your computer only): e.g. "Md. Rafiqul Islam", PIN 1234
  Tests: pip install -r requirements-dev.txt, then: pytest

CHANGE THE WEBSITE  ->  the content/ folder (plain settings, open in VS Code, restart after saving)
  site_text.py      app name, university name, and the words on pages, map menus and driver menu
  user_types.py     start-page buttons. Add "passenger" there and it gets a button, sign-in page,
                    live map, a choice in the backend's Buses tab and an entry in its Users tab.
  map_settings.py   map centre + start zoom, Map/Satellite/Traffic layers (tile URLs),
                    final stop (Hadi Chattar), time zone, country box
  colors.py         bus / route / app colours
  rules.py          PIN length, driver lock time, GPS send speed, map refresh, bus seats,
                    test-drive speed, trail length, alert minutes, login limits
  starting_data.py  routes, buses, demo drivers and starting bus schedules for a new database
  How it reaches the pages: Python files read content/ directly; HTML gets it through
  app.py (content_for_templates); map JavaScript gets it as window.APP_CONFIG
  (templates/_map_assets.html).


HOW IT WORKS (one request, start to end)
  Phone/PC browser --> Flask (Python) --> services (logic) --> SQLite database / memory
  1. A driver's phone sends its GPS about once a second (POST /api/driver/location).
  2. TrackingService stores the position in memory and wakes every open map.
  3. Each map keeps one live connection (GET /api/buses/stream, "Server-Sent Events")
     and moves the bus marker within ~0.1 s. No page reload, no polling.


LIBRARIES (what each is used for)
  Python (requirements.txt)
    Flask              web framework: pages, URLs, sessions (cookies)
    Werkzeug           Flask's base; generate_password_hash / check_password_hash for driver PINs;
                       ProxyFix so the app sees real visitor IPs behind nginx
    Flask-SQLAlchemy   database access (SQLAlchemy ORM); SQLite file instance/busplus.db
    Flask-WTF          CSRF protection (blocks other sites from sending requests as a signed-in user)
    Flask-Limiter      limits login attempts per IP (stops PIN/password guessing)
    flask-talisman     security headers: Content-Security-Policy, HSTS, https redirect
    python-dotenv      reads settings/secrets from the .env file
    requests           asks the OSRM road router for the road line in the route editor
    tzdata / zoneinfo  Bangladesh time (Asia/Dhaka) for "today" and arrival times
    gunicorn + gevent  production server on Linux (one process, many live connections)
    pytest, ruff       tests and code checks (requirements-dev.txt)
    Standard library   math (distances), difflib (forgiving stop names), threading (live updates,
                       test drives), secrets (random tokens), hmac (safe password compare)
  Browser
    Leaflet 1.9.4      the interactive map (static/vendor/leaflet, served by us, no CDN)
    Inter font         static/vendor/inter
    Browser APIs       navigator.geolocation.watchPosition (driver GPS), EventSource (live feed),
                       Wake Lock (driver screen on), Notification + Web Audio (arrival alerts),
                       localStorage (home address, settings on the phone)

MAPS - where they come from
  Map pictures (tiles): Google Maps tile servers  https://mt0-3.google.com/vt/...
      layers Map / Satellite / Traffic, set in content/map_settings.py (MAP_LAYERS)
  Map engine: Leaflet draws the tiles, bus markers, route lines and red trails.
  Road-following routes: OSRM public router (OpenStreetMap data), called by the server
      in services/road_router.py when the admin draws a route. Built-in route lines are
      stored in models/route_paths.py.
  Distances/ETA: our own maths in services/geo.py (haversine distance, bearing, ETA).


FILES AND THEIR MAIN FUNCTIONS
  app.py               create_app(): settings, security, database, URLs; python app.py starts it
  wsgi.py              entry point for gunicorn on the server
  config.py            Config (reads .env + content/), check_production(), TestConfig
  extensions.py        db, csrf, limiter, talisman objects

  controllers/  (the URLs)
    view_controller    landing, driver_login, driver_dashboard, rider_login, rider_dashboard, health
    auth_controller    admin_login, driver_login, rider_login, logout, search_drivers
    bus_controller     list_buses, stream_buses (live feed), driver_location, start_trip,
                       stop_trip (online/offline), driver_assignment (today's duty card)
    route_controller   list_routes, list_schedules (Bus schedule pop-up), check_arrival (alert),
                       _best_bus_for_stop
    admin_controller   portal (/backend), create/update/delete driver, bus, route,
                       unlock_driver, simulate_bus (test drive), snap_to_roads, save_schedule
    helpers            ok / fail JSON replies, driver_required check, audience_arg

  services/  (the logic)
    tracking_service   TrackingService: routes + buses in memory, update_location, start_trip,
                       stop_trip, trails, wait_for_change (live feed), start_simulation, CRUD
    user_service       UserService: drivers, sign_in (PIN + one-phone lock), touch, unlock,
                       mark_duty_changed / mark_duty_seen
    notification_service  arrival_alert(): IDLE / PASSED / ARRIVED / CRITICAL / WARNING / INFO
    geo                distance_km, bearing_deg, estimate_eta, local_now
    road_router        road_path() via OSRM
    schedule_service   todays_schedules (riders/drivers see today only), all_timetables,
                       save_timetable, seed_timetables: one weekly timetable per route, set day by
                       day; morning = bus + time it reaches campus, afternoon = bus + time it leaves
    store              save / delete / all_rows, seed_defaults (first start), record_rider

  models/  (the data)
    records.py         database tables: RouteRecord, BusRecord, DriverRecord, RiderRecord,
                       TimetableRecord (weekly bus schedules)
    route.py, bus.py, user.py   BusRoute/BusStop, Bus, DriverUser used while running
    rider_types.py     checks content/user_types.py, RIDER_KEYS
    seed_data.py, route_paths.py  built-in routes/buses and their road lines

  templates/  (HTML pages, Jinja)
    landing, driver_login, driver_dashboard, student_login + student_dashboard (used by every
    rider type), admin_login, admin_dashboard, base (shared head), _map_assets (map files),
    _schedule_popup (the "Bus schedule" pop-up for riders and drivers)
  static/js/
    common.js          adds the CSRF token to every fetch()
    google_maps_helper.js  GoogleMapsHelper: map, markers (gliding), route lines, trails
    student_tracker.js StudentTracker + BottomSheet: rider map, route search, home, alerts
    driver_tracker.js  DriverApp: GPS sending, online/offline switch, duty card
    admin.js           backend tabs, forms, route editor map, day-by-day schedule editor
    schedule.js        BusSchedule: the "Bus schedule" pop-up (route, today's Morning/Afternoon buses)
  static/css/          common, landing, student (rider map), driver, admin

DATA
  Saved (SQLite): routes, buses, drivers (PIN hashed), bus schedules, students/teachers who signed in.
  Memory only:    live GPS, speed, trails (they come back with the next GPS update).

SECURITY (details in SECURITY.md)
  Hashed PINs, login rate limits, CSRF tokens, secure cookies, HTTPS + security headers,
  drivers can only move their own bus, admin-only backend, no phone numbers in public data.

PUT IT ONLINE: see DEPLOYMENT.md (needs a Hostinger VPS, not shared web hosting).
