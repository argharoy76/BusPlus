"""
MESSAGES FROM THE SERVER - errors, "saved" notes and arrival alerts that pop up on the pages.
Change only the right side of each line. (Help: content/words/__init__.py)
"""

# fmt: off
WORDS = {
    # ---- Sign-in (riders and admin) ----
    "Welcome, {name}": "Welcome, {name}",
    "Logged out.": "Logged out.",
    "Wrong username or password.": "Wrong username or password.",
    "Admin sign-in required.": "Admin sign-in required.",
    "Please enter your name and {id_label}.": "Please enter your name and {id_label}.",

    # ---- GPS devices (backend) ----
    "Device '{name}' added.": "Device '{name}' added.",
    "Device '{name}' updated.": "Device '{name}' updated.",
    "Device {id} not found.": "Device {id} not found.",
    "Device {id} deleted.": "Device {id} deleted.",
    "Device name is required.": "Device name is required.",
    "{bus} already has {device}. Take that device off the bus first.": "{bus} already has {device}. Take that device off the bus first.",  # noqa: E501
    "New key made. The old one no longer works.": "New key made. The old one no longer works.",

    # ---- Buses (backend) ----
    "{bus} added.": "{bus} added.",
    "{bus} updated.": "{bus} updated.",
    "Bus {id} not found.": "Bus {id} not found.",
    "Bus {id} deleted.": "Bus {id} deleted.",
    "{device} is fitted to this bus. Move it to another bus in GPS devices first.": "{device} is fitted to this bus. Move it to another bus in GPS devices first.",  # noqa: E501
    "{bus} is on a live trip. Stop the trip before changing its route.": "{bus} is on a live trip. Stop the trip before changing its route.",  # noqa: E501
    "{bus} is on a live trip. Stop the trip before deleting it.": "{bus} is on a live trip. Stop the trip before deleting it.",  # noqa: E501
    "Bus number is required (e.g. KU Bus #05).": "Bus number is required (e.g. KU Bus #05).",
    "Please choose a route for the bus.": "Please choose a route for the bus.",
    "Colour must look like #E11D48.": "Colour must look like #E11D48.",
    "A bus must be for one of: {types}.": "A bus must be for one of: {types}.",
    "Capacity must be a whole number.": "Capacity must be a whole number.",
    "Capacity must be between 1 and {max}.": "Capacity must be between 1 and {max}.",
    "{bus} test drive stopped.": "{bus} test drive stopped.",
    "{bus}'s route has no line to drive along.": "{bus}'s route has no line to drive along.",
    "{bus} is test-driving its route to {stop}.": "{bus} is test-driving its route to {stop}.",

    # ---- Routes (backend route editor) ----
    "Route '{name}' added.": "Route '{name}' added.",
    "Route '{name}' updated.": "Route '{name}' updated.",
    "Route {id} not found.": "Route {id} not found.",
    "Route {id} doesn't exist.": "Route {id} doesn't exist.",
    "Route deleted.": "Route deleted.",
    "{buses} use this route. Move them to another route in Buses first.": "{buses} use this route. Move them to another route in Buses first.",  # noqa: E501
    "Route name is required.": "Route name is required.",
    "Route colour must look like #2563EB.": "Route colour must look like #2563EB.",
    "Route points must be a list.": "Route points must be a list.",
    "Point {number}": "Point {number}",
    "Point {number} is not valid.": "Point {number} is not valid.",
    "Time for point {number} must look like 08:35 AM.": "Time for point {number} must look like 08:35 AM.",
    "Click the map to draw the route.": "Click the map to draw the route.",
    "The route line": "The route line",
    "The route line is not valid.": "The route line is not valid.",
    "{place} needs a map position.": "{place} needs a map position.",
    "{place} is outside Bangladesh.": "{place} is outside Bangladesh.",
    "Points are not valid.": "Points are not valid.",
    "Use 2 to 60 points inside Bangladesh.": "Use 2 to 60 points inside Bangladesh.",
    "Road map not reachable ({reason}).": "Road map not reachable ({reason}).",
    "No road route found between these points.": "No road route found between these points.",

    # ---- Bus schedules (backend Schedules tab; {day} = day name, {part} = morning / afternoon) ----
    "Schedule of '{name}' saved.": "Schedule of '{name}' saved.",
    "The timetable is not valid.": "The timetable is not valid.",
    "Unknown day: {days}.": "Unknown day: {days}.",
    "{day} {part}: at most {count} buses.": "{day} {part}: at most {count} buses.",
    "{day} {part}: enter a time for every bus.": "{day} {part}: enter a time for every bus.",
    "{day} {part}: bus {bus} doesn't exist.": "{day} {part}: bus {bus} doesn't exist.",

    # ---- Answers to the GPS boxes (shown on the ESP32's serial monitor) ----
    "Unknown device key.": "Unknown device key.",
    "Send the report as JSON.": "Send the report as JSON.",
    "Valid latitude and longitude are required.": "Valid latitude and longitude are required.",
    "The GPS has no position yet (0, 0).": "The GPS has no position yet (0, 0).",
    "This device is not fitted to a bus. Choose its bus in the backend.": "This device is not fitted to a bus. Choose its bus in the backend.",  # noqa: E501

    # ---- Arrival alerts (rider map; {bus} = bus name, {stop} = their Home stop) ----
    "{bus} is offline": "{bus} is offline",
    "{bus} has passed {stop}": "{bus} has passed {stop}",
    "{bus} is at {stop}!": "{bus} is at {stop}!",
    "Your bus has reached your stop. Please board now.": "Your bus has reached your stop. Please board now.",
    "{bus} arrives in ~{minutes} min!": "{bus} arrives in ~{minutes} min!",
    "Only {km} km from {stop}. Be ready at the curb (about {clock}).": "Only {km} km from {stop}. Be ready at the curb (about {clock}).",  # noqa: E501
    "{bus} is ~{minutes} min from {stop}": "{bus} is ~{minutes} min from {stop}",
    "About {minutes} minutes away ({km} km). Expected at {clock}.": "About {minutes} minutes away ({km} km). Expected at {clock}.",  # noqa: E501
    "{bus} is on the way": "{bus} is on the way",
    "Heading to {stop}. ETA {minutes} min ({clock}).": "Heading to {stop}. ETA {minutes} min ({clock}).",

    # ---- Errors ----
    "Not found.": "Not found.",
    "Page not found.": "Page not found.",
    "This page has expired. Please reload it and try again.": "This page has expired. Please reload it and try again.",
    "Too many attempts. Please wait a minute and try again.": "Too many attempts. Please wait a minute and try again.",
    "Something went wrong on the server. Please try again.": "Something went wrong on the server. Please try again.",

    # ---- GPS boxes that join by themselves, quick add, on / off the map ----
    "Another box with this chip ID is already waiting.": "Another box with this chip ID is already waiting.",
    "Box {chip} rejected.": "Box {chip} rejected.",
    "GPS box {number}": "GPS box {number}",
    "Say whether to show the bus on the map.": "Say whether to show the bus on the map.",
    "Send the box's chip ID and its pairing token.": "Send the box's chip ID and its pairing token.",
    "That box is no longer waiting. It may have stopped asking.": "That box is no longer waiting. It may have stopped asking.",
    "The admin did not approve this box.": "The admin did not approve this box.",
    "Too many boxes are waiting. Approve or reject some in the backend.": "Too many boxes are waiting. Approve or reject some in the backend.",
    "Tracker in {bus}": "Tracker in {bus}",
    "{name} approved. The box gets its key in a few seconds.": "{name} approved. The box gets its key in a few seconds.",
    "{name} is off the map. Its bus is hidden on every map.": "{name} is off the map. Its bus is hidden on every map.",
    "{name} is on the map. Its bus shows with its next GPS position.": "{name} is on the map. Its bus shows with its next GPS position.",

    # ---- Rider sign-in checks ----
    "Please enter your real name (letters only).": "Please enter your real name (letters only).",
    "{id_label} may only use letters, numbers and - _ / .": "{id_label} may only use letters, numbers and - _ / .",
}
# fmt: on
