"""
CONTENT FOLDER - change the website from here.

Every file in this folder is a short list of settings written as plain Python.
Open a file in VS Code, change a value between the quotes (or a number), save,
and restart the app (`python app.py`, or on the server: sudo systemctl restart busplus).

    site_text.py        app name, university, and the words on the pages and menus
    user_types.py       Driver / Student / Teacher buttons - add "Passenger" etc. here
    map_settings.py     map start point and zoom, Map/Satellite/Traffic layers, final stop, time zone
    colors.py           colours for buses, routes and the app
    rules.py            PIN length, bus seats, GPS speed, login limits, timings
    starting_data.py    routes, buses, demo drivers and starting bus schedules for a new database

Rules of thumb:
  * Keep the quotes "..." around text and the commas at the end of lines.
  * Colours are hex codes like "#2563EB" (pick one at https://htmlcolorcodes.com).
  * If the app won't start after an edit, the error message names the file and line.
"""
