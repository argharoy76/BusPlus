"""
Route geometry: keep live buses on their road and measure how far along it they are.

`RoutePath` turns a route's road line into something we can measure along:
  * project(lat, lng)  -> the nearest point ON the road, and how many metres along the route it is
  * point_at(metres)   -> the position (and road direction) that many metres along the route
  * between(a, b)      -> the road line between two such distances (used to fill trail gaps)

`AlongTrack` smooths a bus's distance-along-the-route over time (an alpha-beta filter),
so GPS wobble along the road doesn't make the bus hop back and forth.

All maths is done in metres on a flat local map around the bus (fine for a city).
"""

import math
from bisect import bisect_right
from dataclasses import dataclass

M_PER_DEG = 111_320.0          # metres per degree of latitude (and of longitude at the equator)


@dataclass
class Projection:
    """Where a GPS point lands on the route."""

    distance_m: float           # how far the GPS point is from the road
    progress_m: float           # metres from the start of the route
    latitude: float             # the nearest point on the road
    longitude: float


class RoutePath:
    """A route's road line, ready for measuring along."""

    def __init__(self, points: list[tuple[float, float]]):
        self.lat = [p[0] for p in points]
        self.lng = [p[1] for p in points]
        self.cum = [0.0]                                   # metres from the start to each point
        for i in range(1, len(points)):
            self.cum.append(self.cum[-1] + _metres(self.lat[i - 1], self.lng[i - 1], self.lat[i], self.lng[i]))
        self.length = self.cum[-1]

    def __len__(self) -> int:
        return len(self.lat)

    def project(self, lat: float, lng: float, near_m: float | None = None, window_m: float = 600.0) -> Projection:
        """
        Nearest point on the road to (lat, lng). With `near_m` (where the bus was last time),
        segments around it are tried first, so a road used twice (out and back) doesn't confuse it.
        """
        best = None
        if near_m is not None:
            first = max(0, bisect_right(self.cum, near_m - window_m) - 1)
            last = min(len(self.cum) - 1, bisect_right(self.cum, near_m + window_m))
            best = self._closest(lat, lng, first, last)
            if best.distance_m <= 40:
                return best
        overall = self._closest(lat, lng, 0, len(self.cum) - 1)
        return overall if best is None or overall.distance_m < best.distance_m - 15 else best

    def _closest(self, lat: float, lng: float, first: int, last: int) -> Projection:
        kx = M_PER_DEG * math.cos(math.radians(lat))
        best = Projection(math.inf, 0.0, lat, lng)
        for i in range(first, last):
            ax, ay = (self.lng[i] - lng) * kx, (self.lat[i] - lat) * M_PER_DEG
            bx, by = (self.lng[i + 1] - lng) * kx, (self.lat[i + 1] - lat) * M_PER_DEG
            dx, dy = bx - ax, by - ay
            seg2 = dx * dx + dy * dy
            t = 0.0 if seg2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(px, py)
            if d < best.distance_m:
                best = Projection(d, self.cum[i] + t * (self.cum[i + 1] - self.cum[i]),
                                  lat + py / M_PER_DEG, lng + px / kx)
        return best

    def point_at(self, progress_m: float) -> tuple[float, float, float]:
        """(lat, lng, road direction in degrees) at `progress_m` metres along the route."""
        p = max(0.0, min(self.length, progress_m))
        i = max(0, min(len(self.cum) - 2, bisect_right(self.cum, p) - 1))
        seg = self.cum[i + 1] - self.cum[i]
        t = 0.0 if seg == 0 else (p - self.cum[i]) / seg
        lat = self.lat[i] + (self.lat[i + 1] - self.lat[i]) * t
        lng = self.lng[i] + (self.lng[i + 1] - self.lng[i]) * t
        return lat, lng, _bearing(self.lat[i], self.lng[i], self.lat[i + 1], self.lng[i + 1])

    def between(self, from_m: float, to_m: float) -> list[list[float]]:
        """Road points strictly between two distances along the route (in travel order)."""
        lo, hi = sorted((from_m, to_m))
        inside = [[round(self.lat[i], 6), round(self.lng[i], 6)] for i in range(len(self.cum)) if lo < self.cum[i] < hi]
        return inside if from_m <= to_m else inside[::-1]


@dataclass
class AlongTrack:
    """Smoothed distance along the route (metres) and speed along it (m/s, minus = driving backwards)."""

    progress: float | None = None
    velocity: float = 0.0
    time: float = 0.0

    ALPHA = 0.45       # how much of each new GPS measurement to take (1 = no smoothing)
    BETA = 0.25        # how quickly the speed estimate follows
    MAX_JUMP_M = 120   # a bigger surprise than this restarts the filter (e.g. after a GPS gap)

    def reset(self) -> None:
        self.progress, self.velocity, self.time = None, 0.0, 0.0

    def update(self, measured_m: float, t: float, stopped: bool) -> float:
        """Add one measurement (metres along the route at time t) and return the smoothed position."""
        dt = t - self.time
        if self.progress is None or dt <= 0 or dt > 30:
            self.progress, self.velocity, self.time = measured_m, 0.0, t
            return measured_m
        predicted = self.progress + self.velocity * dt
        residual = measured_m - predicted
        if abs(residual) > self.MAX_JUMP_M:
            self.progress, self.velocity, self.time = measured_m, 0.0, t
            return measured_m
        self.progress = predicted + self.ALPHA * residual
        self.velocity = 0.0 if stopped else max(-40.0, min(40.0, self.velocity + self.BETA * residual / dt))
        self.time = t
        return self.progress


def _metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    kx = M_PER_DEG * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lat2 - lat1) * M_PER_DEG, (lng2 - lng1) * kx)


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    kx = math.cos(math.radians((lat1 + lat2) / 2))
    return math.degrees(math.atan2((lng2 - lng1) * kx, lat2 - lat1)) % 360
