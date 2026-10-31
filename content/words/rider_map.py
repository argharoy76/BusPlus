"""
STUDENT / TEACHER MAP - the live map every rider type sees after signing in
(top bar, the menu under the logo, Home and Notification settings, the bus list at the bottom, alerts).
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    # ---- Browser tab and top bar ----
    "{who} map": "{who} map",                      # tab title; {who} = Student / Teacher ...
    "Menu": "Menu",
    "Log out": "Log out",

    # ---- Menu under the logo ----
    "Home": "Home",
    "Notification": "Notification",
    "Bus schedule": "Bus schedule",
    "Back": "Back",

    # ---- Menu > Home ----
    "Home address": "Home address",
    "Start typing a stop name": "Start typing a stop name",
    "Save": "Save",
    "Home saved": "Home saved",

    # ---- Menu > Notification ----
    "Notify me": "Notify me",
    "minutes before the bus arrives": "minutes before the bus arrives",
    "Type how many minutes before arrival you want the alert.":
        "Type how many minutes before arrival you want the alert.",
    "Enter a whole number from 1 to {max}.": "Enter a whole number from 1 to {max}.",
    "You'll be notified 1 minute before the bus reaches {stop}.":
        "You'll be notified 1 minute before the bus reaches {stop}.",
    "You'll be notified {minutes} minutes before the bus reaches {stop}.":
        "You'll be notified {minutes} minutes before the bus reaches {stop}.",
    "Repeat": "Repeat",
    "Once": "Once",
    "{count} times": "{count} times",
    "Until the bus arrives": "Until the bus arrives",
    "Notification updated": "Notification updated",
    " (alert {count})": " (alert {count})",        # added to a repeated alert's title

    # ---- "Locate me" button ----
    "Show my location": "Show my location",
    "Locate me": "Locate me",
    "Locating…": "Locating…",
    "Location on": "Location on",
    "Location found": "Location found",
    "Could not get your location. Please allow location access for this site.":
        "Could not get your location. Please allow location access for this site.",
    "This browser can't share your location.": "This browser can't share your location.",

    # ---- Bus list at the bottom ----
    "Buses": "Buses",
    "Expand or collapse": "Expand or collapse",
    "Select route": "Select route",
    "Route name": "Route name",                    # grey hint in the route box
    "Clear route": "Clear route",
    "No route found": "No route found",
    "All buses": "All buses",
    "Bus": "Bus",
    "live": "live",
    "offline": "offline",

    # ---- Your Home stop line (arrival time) ----
    "Here": "Here",
    "< 1 min": "< 1 min",
    "{minutes} min": "{minutes} min",

    # ---- One bus's details ----
    "Speed": "Speed",
    "{speed} km/h": "{speed} km/h",
    "Next stop": "Next stop",
    "Route": "Route",
    "Driver": "Driver",
}
