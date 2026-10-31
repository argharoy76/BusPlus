"""
MESSAGES FROM THE SERVER - errors, "saved" notes and arrival alerts that pop up on the pages.
Change only the right side of each line. (Help: content/words/__init__.py)
"""

# fmt: off
WORDS = {
    # ---- Sign-in (driver, student, teacher, admin) ----
    "Welcome, {name}": "Welcome, {name}",
    "Logged out.": "Logged out.",
    "Wrong username or password.": "Wrong username or password.",
    "Admin sign-in required.": "Admin sign-in required.",
    "Please enter or select your driver name.": "Please enter or select your driver name.",
    "Driver not found. Please pick your name from the list.": "Driver not found. Please pick your name from the list.",
    "Incorrect PIN.": "Incorrect PIN.",
    "That isn't your route. Please choose the route of your assigned bus.": "That isn't your route. Please choose the route of your assigned bus.",  # noqa: E501
    "Account '{name}' is already logged in on another device. Log out there first, or ask the admin to unlock it.": "Account '{name}' is already logged in on another device. Log out there first, or ask the admin to unlock it.",  # noqa: E501
    "Please enter your name and {id_label}.": "Please enter your name and {id_label}.",
    "Please log in as a driver.": "Please log in as a driver.",
    "This account was signed in on another device. Please log in again.": "This account was signed in on another device. Please log in again.",  # noqa: E501
    "No bus is assigned to you. Ask the admin.": "No bus is assigned to you. Ask the admin.",

    # ---- Driver's duty card ({day} = day name from bus_schedule.py, {date} = e.g. 31 October) ----
    "{day}, {date} {month}": "{day}, {date} {month}",

    # ---- Drivers (backend) ----
    "Driver '{name}' added.": "Driver '{name}' added.",
    "Driver '{name}' updated.": "Driver '{name}' updated.",
    "Driver {id} not found.": "Driver {id} not found.",
    "Driver {id} can now sign in on any phone.": "Driver {id} can now sign in on any phone.",
    "Driver {id} deleted.": "Driver {id} deleted.",
    "Driver name is required.": "Driver name is required.",
    "There is already a driver called {name}. Use a different name so they can log in.": "There is already a driver called {name}. Use a different name so they can log in.",  # noqa: E501
    "PIN must be {min} to {max} digits.": "PIN must be {min} to {max} digits.",
    "Please choose the driver's bus.": "Please choose the driver's bus.",

    # ---- Buses (backend) ----
    "{bus} added.": "{bus} added.",
    "{bus} updated.": "{bus} updated.",
    "Bus {id} not found.": "Bus {id} not found.",
    "Bus {id} deleted.": "Bus {id} deleted.",
    "{names} is assigned to this bus. Move them to another bus in Drivers first.": "{names} is assigned to this bus. Move them to another bus in Drivers first.",  # noqa: E501
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

    # ---- Live GPS (driver's phone) ----
    "Valid latitude and longitude are required.": "Valid latitude and longitude are required.",
    "Latitude/longitude out of range.": "Latitude/longitude out of range.",

    # ---- Arrival alerts (student / teacher map; {bus} = bus name, {stop} = their Home stop) ----
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
}
# fmt: on
