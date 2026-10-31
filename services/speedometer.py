"""
A steady, honest speed for each bus from the driver's phone GPS.

Why this is needed: a phone standing still still "moves" a few metres every second
(GPS wobble). Dividing that wobble by one second gives 4-15 km/h for a bus that is
parked. This filter looks at the last few seconds instead of the last fix:

  1. Fixes that are far too inaccurate (content/rules.py: GPS_IGNORE_ACCURACY_M) are ignored.
  2. A straight line is fitted through the fixes of the last few seconds (least squares),
     so the wobble averages out and the bus's real velocity is left.
  3. STOPPED: if that velocity moved the bus less than a small circle (the GPS accuracy,
     between SPEED_STOPPED_RADIUS_M and twice that) over those seconds, the speed is 0 and
     the marker stays where it is instead of wobbling.
  4. MOVING: the phone's own speed is used when it gives one (it comes from the Doppler
     shift of the satellite signals - far more exact than distance / time); otherwise the
     fitted speed.
  5. Speeds under SPEED_MIN_KMH count as 0, and the result is smoothed a little so the
     number doesn't jump around.
"""

import math
import statistics
import time
from collections import deque
from dataclasses import dataclass, field

from content import rules

WINDOW_S = rules.SPEED_WINDOW_SECONDS          # look back this many seconds
STOP_RADIUS_M = rules.SPEED_STOPPED_RADIUS_M   # smallest "standing still" circle
MIN_MOVING_KMH = rules.SPEED_MIN_KMH           # slower than this shows as 0
IGNORE_ACCURACY_M = rules.GPS_IGNORE_ACCURACY_M
MAX_KMH = 120.0                                # nothing on the road here goes faster
SMOOTHING = 0.6                                # 1 = no smoothing, lower = calmer number
MIN_SPAN_S = 2.5                               # need at least this much history to judge
ACCURACY_FACTOR = 1.5                          # GPS "accuracy" is a 68% circle: allow a bit more wobble


@dataclass
class Reading:
    """What the filter decided for one GPS fix."""

    use_fix: bool               # False: the fix was too inaccurate and was ignored
    speed_kmh: float            # speed to show (0 when stopped)
    stopped: bool               # True while the bus stands still
    heading_deg: float | None   # direction of travel (None: keep the old one)
    latitude: float             # position to show (the old one while stopped, so it doesn't wobble)
    longitude: float


@dataclass
class Speedometer:
    """The recent fixes of one bus and its current speed."""

    fixes: deque = field(default_factory=lambda: deque(maxlen=40))   # (t, lat, lng, accuracy_m)
    speed_kmh: float = 0.0
    shown: tuple[float, float] | None = None                         # position shown on the maps
    moving_votes: int = 0                                            # fixes in a row that looked "moving"

    def reset(self) -> None:
        """Forget everything (a new trip starts)."""
        self.fixes.clear()
        self.speed_kmh = 0.0
        self.shown = None
        self.moving_votes = 0

    def update(self, lat: float, lng: float, accuracy_m: float | None = None,
               phone_speed_kmh: float | None = None, phone_heading: float | None = None,
               fix_time: float | None = None) -> Reading:
        """Add one GPS fix and return the speed / position to show."""
        accuracy = accuracy_m if accuracy_m is not None and accuracy_m > 0 else 15.0
        if accuracy > IGNORE_ACCURACY_M and self.shown is not None:
            return Reading(False, self.speed_kmh, self.speed_kmh == 0, None, *self.shown)

        now = _fix_time(fix_time, self.fixes)
        self.fixes.append((now, lat, lng, accuracy))
        while self.fixes and now - self.fixes[0][0] > WINDOW_S:
            self.fixes.popleft()

        oldest = self.fixes[0]
        span = now - oldest[0]
        if self.shown is None or span < MIN_SPAN_S:
            # Not enough history yet: trust the phone's speed if it has one, else wait.
            speed = _clean_speed(phone_speed_kmh) if phone_speed_kmh is not None else self.speed_kmh
            return self._result(speed, lat, lng, phone_heading)

        # Fit a straight line through the recent fixes (least squares): the GPS wobble
        # averages out and what is left is the real velocity, in metres per second.
        v_north, v_east = _velocity(self.fixes)
        moved_m = math.hypot(v_north, v_east) * span          # distance the bus really covered
        typical_accuracy = statistics.median(f[3] for f in self.fixes)
        radius = min(max(STOP_RADIUS_M, typical_accuracy * ACCURACY_FACTOR), STOP_RADIUS_M * 3)
        if self.speed_kmh == 0:
            radius *= 1.3                                     # standing: need a clear move to start again

        if phone_speed_kmh is not None and phone_speed_kmh >= MIN_MOVING_KMH * 2:
            moving = True                                     # the phone's Doppler speed is clear
        elif phone_speed_kmh is not None and phone_speed_kmh < MIN_MOVING_KMH:
            moving = moved_m > radius * 2                     # phone says standing: only a big move overrules it
        else:
            moving = moved_m > radius

        # Leaving "stopped" needs two moving fixes in a row (one wobble is not a start).
        self.moving_votes = self.moving_votes + 1 if moving else 0
        if not moving or (self.speed_kmh == 0 and self.moving_votes < 2 and not _clear(phone_speed_kmh)):
            self.speed_kmh = 0.0
            return Reading(True, 0.0, True, None, *self.shown)

        # Moving: the phone's Doppler speed, or the fitted speed.
        measured = phone_speed_kmh if phone_speed_kmh is not None else math.hypot(v_north, v_east) * 3.6
        heading = phone_heading
        if heading is None:
            heading = math.degrees(math.atan2(v_east, v_north)) % 360
        return self._result(_clean_speed(measured), lat, lng, heading)

    def _result(self, measured: float, lat: float, lng: float, heading: float | None) -> Reading:
        """Smooth the speed, move the shown position, and build the reading."""
        smoothed = measured if self.speed_kmh == 0 else SMOOTHING * measured + (1 - SMOOTHING) * self.speed_kmh
        self.speed_kmh = 0.0 if smoothed < MIN_MOVING_KMH else round(min(smoothed, MAX_KMH), 1)
        self.shown = (lat, lng)
        return Reading(True, self.speed_kmh, self.speed_kmh == 0, heading, lat, lng)


def _clear(phone_speed_kmh: float | None) -> bool:
    """True when the phone itself clearly reports driving speed."""
    return phone_speed_kmh is not None and phone_speed_kmh >= MIN_MOVING_KMH * 2


def _clean_speed(kmh: float | None) -> float:
    """A speed inside 0..MAX_KMH (bad or missing values count as 0)."""
    if kmh is None or math.isnan(kmh) or kmh < 0:
        return 0.0
    return min(kmh, MAX_KMH)


def _velocity(fixes: deque) -> tuple[float, float]:
    """Least-squares velocity (north, east) in m/s through the fixes [(t, lat, lng, acc), ...]."""
    t_mean = statistics.fmean(f[0] for f in fixes)
    lat0, lng0 = fixes[-1][1], fixes[-1][2]
    m_lat = 111_320.0                                  # metres per degree of latitude
    m_lng = m_lat * math.cos(math.radians(lat0))       # ... and of longitude here
    tt = sum((f[0] - t_mean) ** 2 for f in fixes)
    if tt <= 0:
        return 0.0, 0.0
    north = sum((f[0] - t_mean) * (f[1] - lat0) * m_lat for f in fixes) / tt
    east = sum((f[0] - t_mean) * (f[2] - lng0) * m_lng for f in fixes) / tt
    return north, east


def _fix_time(fix_time: float | None, fixes: deque) -> float:
    """
    When the fix was taken, in seconds. The phone's own GPS time is best (network delays
    don't distort it); it is used when it is close to the server's clock and moves forward.
    """
    now = time.time()
    if fix_time is not None and abs(fix_time - now) < 300 and (not fixes or fix_time > fixes[-1][0]):
        return fix_time
    return max(now, fixes[-1][0] + 0.001) if fixes else now
