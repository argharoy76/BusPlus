"""
BACKEND (/backend) - the admin panel: Live map, GPS devices, Routes, Buses, Schedules and Users tabs,
their tables, the Add / Edit pop-ups and the small messages at the bottom.
Change only the right side of each line. (Help: content/words/__init__.py)
{app} = the app's name (content/branding.py), {stop} = the final stop (content/map_settings.py).
"""

WORDS = {
    # ---- Browser tab and left menu ----
    "{app} Backend": "{app} Backend",
    "Backend": "Backend",
    "GPS devices": "GPS devices",
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
    "Edit {name}": "Edit {name}",

    # ---- GPS devices tab (ESP32 + NEO-6M boxes, one per bus) ----
    "Add device": "Add device",
    "Devices": "Devices",
    "Sending GPS now": "Sending GPS now",
    "Buses without a device": "Buses without a device",
    "Device": "Device",
    "Sending GPS": "Sending GPS",                              # status: good positions are arriving
    "Searching for satellites": "Searching for satellites",    # status: connected, but no GPS position yet
    "Never connected": "Never connected",                      # status: nothing heard since the server started
    "{count} satellites": "{count} satellites",
    "HDOP {hdop}": "HDOP {hdop}",                              # GPS precision: 1 = excellent, above 5 = poor
    "key …{hint}": "key …{hint}",
    "firmware {version}": "firmware {version}",
    "{hours} h ago": "{hours} h ago",
    "New key": "New key",
    "Make a new key (the old one stops working)": "Make a new key (the old one stops working)",
    "Make a new key for {name}? The old key stops working at once, so the device must be updated.":
        "Make a new key for {name}? The old key stops working at once, so the device must be updated.",
    "Delete {name}? Its key stops working and its bus goes offline.":
        "Delete {name}? Its key stops working and its bus goes offline.",
    "Could not delete the device.": "Could not delete the device.",

    # ---- Add / Edit device pop-up ----
    "Device name": "Device name",
    "e.g. Tracker in Bus #01": "e.g. Tracker in Bus #01",
    "Fitted to bus": "Fitted to bus",
    "Not fitted to a bus": "Not fitted to a bus",
    "Its positions move this bus on every map. One device per bus.":
        "Its positions move this bus on every map. One device per bus.",
    "Could not save the device.": "Could not save the device.",

    # ---- Device settings pop-up (shown once, right after a key is made) ----
    "Device settings": "Device settings",
    "Device settings · {name}": "Device settings · {name}",
    "Put these into firmware/busplus_tracker/secrets.h, add your Wi-Fi name and password, then upload the sketch to the ESP32.":
        "Put these into firmware/busplus_tracker/secrets.h, add your Wi-Fi name and password, then upload the sketch to the ESP32.",
    "Server URL": "Server URL",
    "Device key": "Device key",
    "Copy": "Copy",
    "Copy all": "Copy all",
    "Copied": "Copied",
    "This computer calls itself \"localhost\", which the ESP32 can't reach, so its network address is used instead. Start BusPlus with HOST=0.0.0.0 so the ESP32 can connect (see firmware/README.md).":
        "This computer calls itself \"localhost\", which the ESP32 can't reach, so its network address is used instead. Start BusPlus with HOST=0.0.0.0 so the ESP32 can connect (see firmware/README.md).",
    "This key is shown only now. Keep it secret: anyone with it can move this bus on the map. Lost it? Make a new key.":
        "This key is shown only now. Keep it secret: anyone with it can move this bus on the map. Lost it? Make a new key.",
    "Device saved. Copy its key now.": "Device saved. Copy its key now.",
    "Done": "Done",
    "Something went wrong.": "Something went wrong.",

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
    "Riders and the admin both see this name.": "Riders and the admin both see this name.",
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
    "Choose each bus's route for today. The maps change straight away.":
        "Choose each bus's route for today. The maps change straight away.",
    "Add bus": "Add bus",
    "Live now": "Live now",
    "Final destination": "Final destination",
    "For": "For",
    "GPS device": "GPS device",
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

    # ---- Live map tab ----
    "Live map": "Live map",
    "Every bus that is online right now, moving live.": "Every bus that is online right now, moving live.",
    "Speed": "Speed",
    "Next stop": "Next stop",
    "Last GPS": "Last GPS",
    "No bus is online.": "No bus is online.",
    "{speed} km/h": "{speed} km/h",
    "now": "now",
    "{seconds} s ago": "{seconds} s ago",
    "{minutes} min ago": "{minutes} min ago",

    # ---- GPS devices tab: add manually / automatically, boxes asking to join, on / off the map ----
    "Add a device": "Add a device",
    "Approve": "Approve",
    "Asked": "Asked",
    "Automatically": "Automatically",
    "Boxes asking to join": "Boxes asking to join",
    "Chip ID": "Chip ID",
    "chip {chip}": "chip {chip}",
    "Connected devices": "Connected devices",
    "Edit device": "Edit device",
    "Give the device a name.": "Give the device a name.",
    "How to add a device": "How to add a device",
    "joined before as {name}": "joined before as {name}",
    "Made for you if empty": "Made for you if empty",
    "Manually": "Manually",
    "Off the map": "Off the map",
    "On the map": "On the map",
    "Operations": "Operations",
    "Pairing code": "Pairing code",
    "People": "People",
    "Quick add": "Quick add",
    "Reject": "Reject",
    "Reject box {chip}? It is ignored for an hour.": "Reject box {chip}? It is ignored for an hour.",
    "Remove from map": "Remove from map",
    "Remove {name} from the map? Its bus disappears from every map until you show it again.": "Remove {name} from the map? Its bus disappears from every map until you show it again.",
    "Setup": "Setup",
    "Show on map": "Show on map",
    "View live": "View live",
    "Waiting for approval": "Waiting for approval",
    "{bus} (has {device})": "{bus} (has {device})",
    "{bus} now drives {route}.": "{bus} now drives {route}.",

    # ---- GPS devices tab (more) ----
    "GPS / signal": "GPS / signal",
    "Last report {ago}": "Last report {ago}",

    # ---- GPS devices tab (short empty messages) ----
    "No box is waiting.": "No box is waiting.",
    "No GPS devices yet.": "No GPS devices yet.",
}
