"""
CONTENT FOLDER - change the whole website from here, without touching the code.

Open a file in VS Code, change a value between the quotes (or a number), save, and refresh
the browser. (`python app.py` reloads by itself; on the server run: sudo systemctl restart busplus)

WHAT TO OPEN FOR WHAT
    branding.py          app name, university name, logo emoji, browser-tab titles
    colors.py            the website's colours (brand, background, text, ...) and bus / route colours
    user_types.py        Driver / Student / Teacher buttons and sign-in pages - add "Passenger" here
    map_settings.py      map start point and zoom, Map/Satellite/Traffic layers, final stop, default Home
    rules.py             PIN length, bus seats, GPS speed, alert minutes, login limits, timings
    starting_data.py     routes, buses, demo drivers and bus schedules for a NEW (empty) database
    words/               EVERY piece of text, one file per page:
        login_pages.py       driver / student / teacher sign-in pages
        rider_map.py         student / teacher live map, its menu, Home, notifications
        driver_map.py        driver's map, duty card, online switch, GPS messages
        bus_schedule.py      "Bus schedule" pop-up, day names, month names
        map.py               things on every map (bus pop-up, speed tags, "Your location")
        backend_login.py     admin sign-in page (/backend/login)
        backend.py           admin panel (/backend): tabs, tables, forms, pop-ups
        server_messages.py   errors, "saved" notes and arrival alerts sent by the server
    (The start page is made of branding.py + user_types.py.)

PAGE BY PAGE
    Start page ............ branding.py, user_types.py, colors.py
    Sign-in pages ......... words/login_pages.py, user_types.py ("id_label"), rules.py (PIN length)
    Student/teacher map ... words/rider_map.py, words/map.py, words/bus_schedule.py, map_settings.py
    Driver's map .......... words/driver_map.py, words/map.py, words/bus_schedule.py, rules.py (GPS)
    Backend ............... words/backend.py, words/backend_login.py, rules.py (seats), colors.py
    Messages / alerts ..... words/server_messages.py, rules.py (alert minutes)

RULES OF THUMB
  * Keep the quotes "..." around text and the comma at the end of each line.
  * In words/ files change only the RIGHT side:   "Original": "What the page shows",
  * Keep {blanks} like {name} - the app fills them in.
  * Colours are hex codes like "#2563EB" (pick one at https://htmlcolorcodes.com).
  * If the app won't start after an edit, the error message names the file and line.
  * `pytest` checks that every text on the site is listed here and nothing is left over.
"""
