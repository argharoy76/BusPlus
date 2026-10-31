"""
ON EVERY MAP - the student / teacher map and the driver's map
(bus markers, the pop-up when a driver taps a bus, the rider's own position).
The Map / Satellite / Traffic buttons and the corner label are in content/map_settings.py.
Change only the right side of each line. (Help: content/words/__init__.py)
"""

WORDS = {
    # ---- Bus markers ----
    "{speed} km/h": "{speed} km/h",               # small speed tag under a moving bus

    # ---- Pop-up when a bus is tapped (driver map) ----
    "Live": "Live",
    "Route": "Route",
    "Speed": "Speed",
    "Next stop": "Next stop",
    "On the way": "On the way",                   # when the next stop isn't known yet

    # ---- The rider's own position ("Locate me") ----
    "Your location": "Your location",
    "Accurate to about {meters} m": "Accurate to about {meters} m",
}
