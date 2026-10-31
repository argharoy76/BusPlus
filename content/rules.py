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
