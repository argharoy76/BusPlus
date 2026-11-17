"""
RULES AND TIMINGS
"""

# ---- GPS tracker boxes (ESP32 + NEO-6M, services/device_service.py) ----------
# Each box sends its position this often (seconds). The box is told this value in every
# answer, so changing it here changes every box without re-flashing it.
DEVICE_SEND_EVERY_SECONDS = 2
# A box that has sent nothing for this many seconds shows as "Offline" in the backend.
DEVICE_OFFLINE_SECONDS = 60
# Positions older than this (seconds) when they arrive are not shown live (only noted).
DEVICE_MAX_FIX_AGE_SECONDS = 120
# Reports per minute one box (one key) may send to /api/device/location.
DEVICE_LIMIT = "120 per minute"
# Requests per minute a box without a key may send to /api/device/pair while it asks to join.
DEVICE_PAIR_LIMIT = "30 per minute"
# The NEO-6M reports its precision as HDOP. Accuracy in metres is about HDOP x this.
GPS_HDOP_TO_METERS = 5.0

# ---- Speed shown on the maps (services/speedometer.py) ------------------------
# A parked bus's GPS still wobbles a few metres. The bus counts as STOPPED (speed 0,
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

# ---- Going offline ------------------------------------------------------------
# A live bus whose GPS box has sent no position for this many minutes goes offline by itself
# (e.g. the bus was switched off, or the box lost power or signal). 0 = never.
AUTO_OFFLINE_MINUTES = 5

# ---- Keeping buses on the road (services/route_geometry.py) -------------------
# GPS this close (metres) to the bus's route line is put exactly on the road, so the bus
# glides along the road instead of wobbling beside it. Further away = off its route: shown as is.
ROUTE_SNAP_METERS = 35
# When the red trail would jump further than this (metres) - e.g. the GPS box lost its signal
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

# ---- Riders (students, teachers, staff) ----------------------------------------------------
# "Notify me N minutes before the bus arrives": the starting value.
DEFAULT_ALERT_MINUTES = 5
# The largest number of minutes a rider may type there.
MAX_ALERT_MINUTES = 120

# ---- Backend sign-in -----------------------------------------------------------
# The admin is signed out of the backend this many hours after signing in (also when the
# browser stays open, and whatever else is signed in in the same browser).
ADMIN_SESSION_HOURS = 12

# ---- Login protection (attempts allowed per IP address) ---------------------
ADMIN_LOGIN_LIMIT = "5 per minute; 30 per hour"
RIDER_LOGIN_LIMIT = "20 per minute"
