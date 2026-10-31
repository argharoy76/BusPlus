"""
BACKEND (/backend) - the admin panel: Drivers, Routes, Buses, Schedules and Users tabs,
their tables, the Add / Edit pop-ups and the small messages at the bottom.
Change only the right side of each line. (Help: content/words/__init__.py)
{app} = the app's name (content/branding.py), {stop} = the final stop (content/map_settings.py).
"""

WORDS = {
    # ---- Browser tab and left menu ----
    "{app} Backend": "{app} Backend",
    "Backend": "Backend",
    "Drivers": "Drivers",
    "Routes": "Routes",
    "Buses": "Buses",
    "Schedules": "Schedules",
    "Users": "Users",
    "Signed in as": "Signed in as",
    "Open the {app} app": "Open the {app} app",
    "Sign out": "Sign out",

    # ---- Words used in many places ----
    "Actions": "Actions",
    "Edit": "Edit",
    "Delete": "Delete",
    "Save": "Save",
    "Cancel": "Cancel",
    "Close": "Close",
    "Status": "Status",
    "Route": "Route",
    "Route today": "Route today",
    "Bus": "Bus",
    "Driver": "Driver",
    "Edit {name}": "Edit {name}",

    # ---- Drivers tab ----
    "Drivers sign in on the {app} app (not here) with the name and PIN you set.":
        "Drivers sign in on the {app} app (not here) with the name and PIN you set.",
    "Add driver": "Add driver",
    "Signed in now": "Signed in now",
    "Phone": "Phone",
    "Bus today": "Bus today",
    "No bus": "No bus",
    "Signed in": "Signed in",
    "Available": "Available",
    "Unlock": "Unlock",
    "Sign {name} out of their device so they can log in again?":
        "Sign {name} out of their device so they can log in again?",
    "Could not unlock.": "Could not unlock.",
    "Delete driver {name}?": "Delete driver {name}?",
    "Could not delete.": "Could not delete.",

    # ---- Add / Edit driver pop-up ----
    "Driver name": "Driver name",
    "e.g. Md. Tariqul Islam": "e.g. Md. Tariqul Islam",
    "+880 17xx-xxxxxx": "+880 17xx-xxxxxx",
    "Login PIN": "Login PIN",
    "{min}–{max} digits": "{min}–{max} digits",
    "New PIN (optional)": "New PIN (optional)",
    "Leave empty to keep the current PIN.": "Leave empty to keep the current PIN.",
    "Route today: {route}": "Route today: {route}",
    "Could not save the driver.": "Could not save the driver.",

    # ---- Routes tab ----
    "Add or remove routes. Every route ends at {stop}.": "Add or remove routes. Every route ends at {stop}.",
    "Add route": "Add route",
    "Length": "Length",
    "Ends at": "Ends at",
    "Buses today": "Buses today",
    "{km} km": "{km} km",
    "None": "None",
    "Remove the route {name}?": "Remove the route {name}?",
    "Could not remove the route.": "Could not remove the route.",

    # ---- Add / Edit route pop-up (map editor) ----
    "Route name": "Route name",
    "e.g. Rupsha - {stop}": "e.g. Rupsha - {stop}",
    "Riders, drivers and the admin all see this name.": "Riders, drivers and the admin all see this name.",
    "Colour": "Colour",
    "Click the map where the route starts.": "Click the map where the route starts.",
    "Undo last point": "Undo last point",
    "Clear": "Clear",
    "Click along the roads the bus takes, starting where the route begins. The line follows the roads to {stop}. "
    "Drag a point to move it, double-click it to remove it.":
        "Click along the roads the bus takes, starting where the route begins. The line follows the roads to {stop}. "
        "Drag a point to move it, double-click it to remove it.",
    "Finding the roads…": "Finding the roads…",
    "{km} km along the roads": "{km} km along the roads",
    "Couldn't reach the road map, so the line is drawn straight. It will still save.":
        "Couldn't reach the road map, so the line is drawn straight. It will still save.",
    "Start · drag to move, double-click to remove": "Start · drag to move, double-click to remove",
    "Drag to move, double-click to remove": "Drag to move, double-click to remove",
    "Remove all points of this route?": "Remove all points of this route?",
    "Give the route a name.": "Give the route a name.",
    "Click the map to draw the route.": "Click the map to draw the route.",
    "Could not save the route.": "Could not save the route.",

    # ---- Buses tab ----
    "Choose each bus's route for today. Its driver sees the change on the app.":
        "Choose each bus's route for today. Its driver sees the change on the app.",
    "Add bus": "Add bus",
    "Live now": "Live now",
    "Final destination": "Final destination",
    "For": "For",
    "{count} seats": "{count} seats",
    "Who {bus} is for": "Who {bus} is for",
    "Choose…": "Choose…",
    "Route today for {bus}": "Route today for {bus}",
    "Stop the trip to change the route": "Stop the trip to change the route",
    "Live": "Live",
    "Offline": "Offline",
    "Drive this bus along its route (for testing)": "Drive this bus along its route (for testing)",
    "Test drive": "Test drive",
    "Stop": "Stop",
    "{bus} → {route}. Its driver has been notified.": "{bus} → {route}. Its driver has been notified.",
    "Could not change the route.": "Could not change the route.",
    "{bus} is now a bus for {group}.": "{bus} is now a bus for {group}.",
    "Could not change it.": "Could not change it.",
    "Could not start the test drive.": "Could not start the test drive.",
    "Delete {bus}? Nobody will see it on the map any more.": "Delete {bus}? Nobody will see it on the map any more.",
    "Could not delete the bus.": "Could not delete the bus.",

    # ---- Add / Edit bus pop-up ----
    "Bus number": "Bus number",
    "KU Bus #05": "KU Bus #05",
    "Bus name": "Bus name",
    "Rupsha Express": "Rupsha Express",
    "License plate": "License plate",
    "Khulna-Cha 11-6001": "Khulna-Cha 11-6001",
    "Seats": "Seats",
    "Bus for": "Bus for",
    "Each group only sees the buses meant for it.": "Each group only sees the buses meant for it.",
    "Colour on the map": "Colour on the map",
    "Colour {color}": "Colour {color}",
    "Pick any colour": "Pick any colour",
    "Could not save the bus.": "Could not save the bus.",

    # ---- Schedules tab ----
    "Bus schedules": "Bus schedules",
    "Set each route's buses for every day. Riders see today's schedule.":
        "Set each route's buses for every day. Riders see today's schedule.",
    "Morning {morning} · Afternoon {afternoon}": "Morning {morning} · Afternoon {afternoon}",
    "Add a route first.": "Add a route first.",

    # ---- Schedule pop-up (one route, day by day) ----
    "Bus schedule": "Bus schedule",
    "Morning": "Morning",
    "Reaches campus": "Reaches campus",
    "Afternoon": "Afternoon",
    "Leaves campus": "Leaves campus",
    "— Choose bus —": "— Choose bus —",
    "On this route": "On this route",
    "Other buses": "Other buses",
    "Time": "Time",
    "Remove": "Remove",
    "1 bus": "1 bus",
    "{count} buses": "{count} buses",
    "Off": "Off",
    "Copy this day to all days": "Copy this day to all days",
    "Copied to all days. Press Save to keep it.": "Copied to all days. Press Save to keep it.",
    "Could not save the schedule.": "Could not save the schedule.",

    # ---- Users tab ----
    "{groups} who have opened the live map.": "{groups} who have opened the live map.",
    "ID": "ID",
    "Name": "Name",
    "Type": "Type",
    "Last seen": "Last seen",
    "Nobody has signed in yet.": "Nobody has signed in yet.",
}
