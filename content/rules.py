"""
RULES AND TIMINGS
"""

# ---- Drivers ----------------------------------------------------------------
# A driver's PIN must be this many digits (smallest, largest).
PIN_MIN_DIGITS = 4
PIN_MAX_DIGITS = 8

# A driver account works on one phone at a time. If that phone sends nothing for
# this many minutes, the driver may sign in on another phone.
DRIVER_LOCK_MINUTES = 10

# The driver's phone sends its position at most this often (seconds) ...
GPS_SEND_EVERY_SECONDS = 1
# ... or sooner when the bus has moved this many metres.
GPS_SEND_AFTER_METERS = 8

# ---- Speed shown on the maps (services/speedometer.py) ------------------------
# A parked phone's GPS still wobbles a few metres. The bus counts as STOPPED (speed 0,
# marker stays still) while it moves less than this many metres (or its GPS accuracy, if larger)
# over the last few seconds.
SPEED_STOPPED_RADIUS_M = 10
# How many seconds of GPS fixes are looked at to decide "stopped" and to measure speed.
SPEED_WINDOW_SECONDS = 8
# Slower than this (km/h) shows as 0.
SPEED_MIN_KMH = 3
# GPS fixes less exact than this (metres) are ignored (e.g. indoors, right after GPS starts).
GPS_IGNORE_ACCURACY_M = 80
# No GPS from a live bus for this many seconds: its speed shows as 0.
SPEED_STALE_SECONDS = 15

# ---- Background GPS (Traccar Client app, services/tracker_service.py) ---------
# A live bus whose phone has sent no GPS for this many minutes goes offline by itself
# (e.g. the driver switched the app off, or the phone died). 0 = never.
AUTO_OFFLINE_MINUTES = 5
# Positions per minute one phone (IP address) may send to /api/tracker.
TRACKER_LIMIT = "240 per minute"

# ---- Keeping buses on the road (services/route_geometry.py) -------------------
# GPS this close (metres) to the bus's route line is put exactly on the road, so the bus
# glides along the road instead of wobbling beside it. Further away = off its route: shown as is.
ROUTE_SNAP_METERS = 35
# When the red trail would jump further than this (metres) - e.g. the driver's phone was locked
# for a minute - the gap is drawn along the road instead of a straight line.
TRAIL_FILL_GAP_METERS = 40

# If a map loses its live connection, it asks for the buses this often instead (seconds).
MAP_REFRESH_SECONDS = 3

# ---- Buses ------------------------------------------------------------------
DEFAULT_BUS_SEATS = 52       # seats of a new bus if the admin leaves it empty
MAX_BUS_SEATS = 120          # largest number of seats the backend accepts

# Admin "Test drive": 1.0 = 30 km/h, 2.0 = 60 km/h ...
TEST_DRIVE_SPEED = 2.0

# The red trail behind a moving bus: ignore GPS wobble smaller than this (km),
# and keep at most this many points per bus.
TRAIL_MIN_STEP_KM = 0.012
TRAIL_MAX_POINTS = 1500

# ---- Students / teachers ----------------------------------------------------
# "Notify me N minutes before the bus arrives": the starting value.
DEFAULT_ALERT_MINUTES = 5
# The largest number of minutes a rider may type there.
MAX_ALERT_MINUTES = 120

# ---- Login protection (attempts allowed per IP address) ---------------------
ADMIN_LOGIN_LIMIT = "5 per minute; 30 per hour"
DRIVER_LOGIN_LIMIT = "10 per minute; 60 per hour"
RIDER_LOGIN_LIMIT = "20 per minute"
