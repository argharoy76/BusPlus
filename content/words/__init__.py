"""
WORDS - every piece of text on the website, one file per page.

    login_pages.py       driver, student and teacher sign-in pages
    rider_map.py         student / teacher live map: bottom sheet, menu, Home, alerts
    driver_map.py        driver's map: duty card, online switch, GPS messages
    bus_schedule.py      the "Bus schedule" pop-up, and the day names
    map.py               things on every map: layer buttons, bus pop-up, "Your location"
    backend_login.py     the admin sign-in page (/backend/login)
    backend.py           the admin panel (/backend): tabs, tables, forms, pop-ups
    server_messages.py   messages the server sends: errors, "saved", arrival alerts

HOW TO EDIT
  Each line looks like      "Original text": "Text shown on the page",
  * Change ONLY the right side. The left side is how the code finds the line.
  * Keep the quotes and the comma at the end.
  * Words in curly brackets, like {name} or {minutes}, are filled in by the app.
    Keep them (you may move them) - e.g. "{name} added." -> "Added {name}!"
  * To put a " inside the text, write \\" (or use ' instead).
  * Save, then refresh the browser (python app.py reloads by itself; on the server
    run: sudo systemctl restart busplus).

Names of the app and university: content/branding.py.  Rider buttons: content/user_types.py.
"""
