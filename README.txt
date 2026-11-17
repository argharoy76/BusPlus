BUSPLUS - Khulna University live bus tracker
============================================

WHAT IT DOES
  A GPS box in every bus (ESP32 + NEO-6M) sends the bus's position every 2 seconds; students,
  teachers and staff see the buses move live on a map, get "your bus is coming" alerts, and the
  admin manages GPS boxes, routes and buses at /backend.
  Every route ends at Hadi Chattar. Works on phones and PCs.

RUN IT
  pip install -r requirements.txt      (once, and again after the libraries change)
  python app.py                        then open http://localhost:5000
  Backend: http://localhost:5000/backend   user: admin   password: instance/admin_password.txt
  No GPS box yet? Backend > GPS devices > Add a device, then: python tools/simulate_gps_box.py <key>
  (or with no key: it asks to join; approve it under Add a device > Automatically)
  The GPS box itself (wiring, firmware, upload): firmware/README.md
  Tests: pip install -r requirements-dev.txt, then: pytest

CHANGE THE WEBSITE  ->  the content/ folder (no code needed; save, then refresh the browser)
  branding.py       app name, university name, logo emoji, browser-tab titles
  colors.py         website colours (brand, background, text, ...), bus and route colours
  user_types.py     start-page buttons. Add "passenger" there and it gets a button, sign-in page,
                    live map, a choice in the backend's Buses tab and an entry in its Users tab.
  map_settings.py   map centre + zoom, Map/Satellite/Traffic layers (tile URLs), final stop
                    (Hadi Chattar), default Home stop, time zone, country box
  rules.py          GPS boxes (send interval, offline after, rate limit), speed filter (when a
                    bus counts as stopped), auto-offline, map refresh, bus seats, test-drive
                    speed, trail length, alert minutes, login limits
  starting_data.py  routes, buses and starting bus schedules for a new database
  words/            EVERY text on the site, one file per page: login_pages, rider_map,
                    bus_schedule, map, backend_login, backend, server_messages.
                    Each line is  "Original": "Shown text"  - change only the right side.
  How it reaches the pages: Python reads content/ directly; HTML gets it through app.py
  (content_for_templates); JavaScript gets map settings as window.APP_CONFIG and words as
  window.WORDS. services/words.py does the word look-ups; tests/test_words.py checks that every
  text on the site is in content/words/ and nothing there is unused.
  Full guide: content/__init__.py.   Every function and library in detail: README_SPECS.txt


HOW IT WORKS (one request, start to end)
  GPS box / browser --> Flask (Python) --> services (logic) --> SQLite database / memory
  1. The bus's GPS box sends its position every 2 seconds (POST /api/device/location, with its
     secret key in the X-Device-Key header). device_controller.py checks the key and the report.
  2. TrackingService cleans it (wobble filter, puts it on the road), stores it in memory
     and wakes every open map.
  3. Each map keeps one live connection (GET /api/buses/stream, "Server-Sent Events") and
     gets only what changed. The bus glides along the road at its real speed, 60 frames a
     second (google_maps_helper.js). No page reload, no polling.


LIBRARIES (what each is used for)
  Python (requirements.txt)
    Flask              web framework: pages, URLs, sessions (cookies)
    Werkzeug           Flask's base; ProxyFix so the app sees real visitor IPs behind nginx
    Flask-SQLAlchemy   database access (SQLAlchemy ORM); SQLite file instance/busplus.db
    Flask-WTF          CSRF protection (blocks other sites from sending requests as a signed-in user)
    Flask-Limiter      limits login attempts per IP, and GPS reports per device key
    flask-talisman     security headers: Content-Security-Policy, HSTS, https redirect
    python-dotenv      reads settings/secrets from the .env file
    requests           asks the OSRM road router for the road line in the route editor
    tzdata / zoneinfo  Bangladesh time (Asia/Dhaka) for "today" and arrival times
    gunicorn + gevent  production server on Linux (one process, many live connections)
    pytest, ruff       tests and code checks (requirements-dev.txt)
    Standard library   math (distances), difflib (forgiving stop names), threading (live updates,
                       test drives), secrets (random device keys), hashlib (stores keys hashed),
                       hmac (safe password compare)
  Browser
    Leaflet 1.9.4      the interactive map (static/vendor/leaflet, served by us, no CDN)
    Inter font         static/vendor/inter
    Browser APIs       EventSource (live feed), navigator.geolocation ("Your location" on the
                       rider map), Notification + Web Audio (arrival alerts),
                       localStorage (home address, settings on the phone)
  GPS box (firmware/busplus_tracker, Arduino IDE)
    ESP32 Arduino core WiFi, HTTPClient, WiFiClientSecure (sends the reports)
    TinyGPSPlus        reads position, speed, course, satellites, HDOP and time from the NEO-6M

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
    view_controller    landing, favicon, rider_login, rider_dashboard, health
    auth_controller    admin_login, admin_logout, rider_login, logout
    bus_controller     list_buses, stream_buses (live feed)
    device_controller  receive_report (POST /api/device/location from the GPS boxes)
    route_controller   list_routes, list_schedules (Bus schedule pop-up), check_arrival (alert),
                       _best_bus_for_stop
    admin_controller   portal (/backend), list/create/update/delete device, renew_device_key,
                       create/update/delete bus and route, simulate_bus (test drive),
                       snap_to_roads, save_schedule
    helpers            ok / fail JSON replies, audience_arg, optional_float

  services/  (the logic)
    tracking_service   TrackingService: routes + buses in memory, update_location, start_trip,
                       stop_trip, trails, wait_for_change (live feed), start_simulation, CRUD
    device_service     DeviceService: GPS boxes, create / update / new_key / delete, by_key
                       (key -> device via its SHA-256 hash), on_bus; parse_report() checks a report
    notification_service  arrival_alert(): IDLE / PASSED / ARRIVED / CRITICAL / WARNING / INFO
    geo                distance_km, bearing_deg, estimate_eta, local_now
    speedometer        Speedometer: precise speed from GPS (0 when parked, no marker wobble)
    route_geometry     RoutePath (snap to the road, distance along the route), AlongTrack (smoothing)
    road_router        road_path() via OSRM
    schedule_service   todays_schedules (riders see today only), all_timetables,
                       save_timetable, seed_timetables: one weekly timetable per route, set day by
                       day; morning = bus + time it reaches campus, afternoon = bus + time it leaves
    store              save / delete / all_rows, seed_defaults (first start), record_rider
    words              words / say / page_words: the texts from content/words/

  models/  (the data)
    records.py         database tables: RouteRecord, BusRecord, GpsDeviceRecord, RiderRecord,
                       TimetableRecord (weekly bus schedules)
    route.py, bus.py, device.py   BusRoute/BusStop, Bus, GpsDevice (setup + latest report)
    rider_types.py     checks content/user_types.py, RIDER_KEYS
    seed_data.py, route_paths.py  built-in routes/buses and their road lines

  templates/  (HTML pages, Jinja)
    landing, student_login + student_dashboard (used by every rider type), admin_login,
    admin_dashboard, base (shared head), _map_assets (map files),
    _schedule_popup (the "Bus schedule" pop-up for riders), _ui (logo + icons),
    _theme (colours + tab icon)
  static/js/
    common.js          adds the CSRF token to every fetch(); words() look-up for content/words/
    google_maps_helper.js  GoogleMapsHelper: map, markers (gliding), route lines, trails
    student_tracker.js StudentTracker + BottomSheet: rider map, route search, home, alerts
    admin.js           backend tabs, GPS devices tab (refreshes itself), forms, route editor map,
                       day-by-day schedule editor
    schedule.js        BusSchedule: the "Bus schedule" pop-up (route, today's Morning/Afternoon buses)
  static/css/          common, landing, student (rider map), schedule, admin
  firmware/busplus_tracker/   busplus_tracker.ino (ESP32 sketch), secrets.example.h
  tools/simulate_gps_box.py   pretends to be a GPS box (for testing without hardware)

GPS BOXES (ESP32 + NEO-6M, one per bus)
  Backend > GPS devices > Add a device:
    Manually       name + bus. BusPlus makes a secret key and shows it once, with the Server URL
                   and a ready secrets.h. Put that into the firmware and upload it.
    Automatically  Quick add (name + first bus without a device filled in for you), or approve a
                   box that asks to join by itself (DEVICE_KEY "" in secrets.h): check its 6-digit
                   pairing code, Approve, and the box receives its key by itself.
  Under that: the counts, then the connected devices. "Remove from map" hides that bus on every
  map (the box stays connected); "Show on map" brings it back.
  The box sends {"lat", "lng", "speed_kmh", "course", "sats", "hdop", ...} every 2 seconds; the
  bus goes online with the first position and offline by itself after 5 minutes without GPS.
  The GPS devices tab shows each box's status (Sending GPS / Searching for satellites /
  Offline / Never connected), satellites, HDOP, signal and last report, refreshed every 5 s.
  Code: controllers/device_controller.py (/api/device/location, /api/device/pair),
        services/device_service.py, models/device.py.
  Hardware guide: firmware/README.md

DATA
  Saved (SQLite): routes, buses, GPS devices (keys hashed), bus schedules, riders who signed in.
  Memory only:    live GPS, speed, trails, each box's latest report (they come back with the next one).

SECURITY (details in SECURITY.md)
  Hashed device keys, rate limits, CSRF tokens, secure cookies, HTTPS + security headers,
  a GPS box can only move the bus it is fitted to, admin-only backend, no keys in public data.

PUT IT ONLINE: see DEPLOYMENT.md (needs a Hostinger VPS, not shared web hosting).
