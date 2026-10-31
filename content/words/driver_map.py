"""
DRIVER'S MAP - the driver's full-screen map and the menu under the logo
(today's duty card, Your bus / All buses, online switch, GPS messages).
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    # ---- Logo button ----
    "Menu": "Menu",
    "GPS": "GPS",                                  # tooltip of the small dot on the logo

    # ---- Today's duty card ----
    "Today's duty": "Today's duty",
    "Changed today": "Changed today",
    "The admin changed your bus or route today.": "The admin changed your bus or route today.",
    "Your bus": "Your bus",
    "Bus no. {number}": "Bus no. {number}",
    "Plate {plate}": "Plate {plate}",
    "No bus assigned yet": "No bus assigned yet",
    "Ask the admin to assign you a bus.": "Ask the admin to assign you a bus.",
    "Your route": "Your route",
    "No route assigned yet": "No route assigned yet",
    "From {from} at {time} to {to}": "From {from} at {time} to {to}",
    "From {from} to {to}": "From {from} to {to}",
    "Ends at {stop}": "Ends at {stop}",

    # ---- Map view buttons ----
    "Map view": "Map view",
    "All buses": "All buses",

    # ---- Bus schedule button ----
    "Bus schedule": "Bus schedule",

    # ---- Online / offline switch ----
    "You are online": "You are online",
    "You are offline": "You are offline",
    "Online. Tap to go offline": "Online. Tap to go offline",
    "Offline. Tap to go online": "Offline. Tap to go online",
    "Try again": "Try again",
    "Log out": "Log out",

    # ---- GPS state (small line under the switch) ----
    "Starting GPS…": "Starting GPS…",
    "GPS on · sharing location": "GPS on · sharing location",
    "Not sharing location": "Not sharing location",
    "Waiting for GPS signal…": "Waiting for GPS signal…",
    "Location blocked": "Location blocked",
    "GPS unavailable": "GPS unavailable",
    "GPS needs HTTPS": "GPS needs HTTPS",
    "No GPS on this device": "No GPS on this device",
    "No bus assigned": "No bus assigned",

    # ---- Red message at the bottom when GPS can't work ----
    "GPS can't start: phones only share location with sites opened over HTTPS (or on this computer as localhost).":
        "GPS can't start: phones only share location with sites opened over HTTPS (or on this computer as localhost).",
    "This device or browser can't share its location.": "This device or browser can't share its location.",
    "Location is blocked for this site. Allow location in your browser settings, then open the menu and tap Try again.":
        "Location is blocked for this site. Allow location in your browser settings, then open the menu and tap Try again.",
    "Can't get a GPS position right now. Move to an open area, then open the menu and tap Try again.":
        "Can't get a GPS position right now. Move to an open area, then open the menu and tap Try again.",
}
