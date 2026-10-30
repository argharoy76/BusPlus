"""
MAP SETTINGS
"""

# Where the map is centred before any bus or home is known (latitude, longitude).
# Find coordinates: right-click a place in Google Maps and click the numbers to copy them.
MAP_CENTER = {"latitude": 22.8010, "longitude": 89.5345}

# The last stop of EVERY route. All buses drive here. Change it once to move it for all routes.
FINAL_DESTINATION = {
    "stop_name": "Hadi Chattar",
    "latitude": 22.80209,
    "longitude": 89.53398,
    "landmark_hint": "Khulna University · Hadi Chattar",
}

# Local time zone (used for "today" on the driver's duty card and arrival clock times).
TIMEZONE = "Asia/Dhaka"

# Rough box around the country. Route points and GPS outside it are refused (catches typos).
COUNTRY_BOUNDS = {"lat": (20.0, 27.0), "lng": (88.0, 93.0)}

# The map pictures ("tiles") come from Google Maps: see googleTileUrl in static/js/google_maps_helper.js.
