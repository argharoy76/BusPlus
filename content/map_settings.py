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

# A rider's Home stop before they choose their own (menu > Home on the student / teacher map).
DEFAULT_HOME = {"stop_name": "Malabotha More", "latitude": 22.7725, "longitude": 89.5855}

# Local time zone (used for "today" on the driver's duty card and arrival clock times).
TIMEZONE = "Asia/Dhaka"

# Rough box around the country. Route points and GPS outside it are refused (catches typos).
COUNTRY_BOUNDS = {"lat": (20.0, 27.0), "lng": (88.0, 93.0)}

# How close the map starts (bigger number = closer; 13 shows the city, 16 shows streets).
MAP_START_ZOOM = 13

# The Map / Satellite / Traffic buttons on every map. The first one is shown when a map opens.
# "url" is where the map pictures (tiles) come from - here Google Maps. {s}, {x}, {y}, {z} are
# filled in by the map. "clean": True hides shop/business icons on that layer.
# Remove a block to remove its button; reorder blocks to change the order.
MAP_LAYERS = [
    {"key": "roadmap", "label": "Map", "url": "https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", "clean": True},
    {"key": "satellite", "label": "Satellite", "url": "https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"},
    {"key": "traffic", "label": "Traffic", "url": "https://mt{s}.google.com/vt/lyrs=m,traffic&x={x}&y={y}&z={z}"},
]

# Small label in the map's corner.
MAP_CREDIT = "Google Maps · Khulna Transit"
