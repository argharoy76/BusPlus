"""
The speed shown for a bus: 0 while parked (even with GPS wobble), right while moving.
"""

import math
import random
import time

from services.speedometer import Speedometer

START = (22.7725, 89.5855)
M_PER_DEG_LAT = 111_320


def _offset(lat, lng, north_m, east_m):
    return lat + north_m / M_PER_DEG_LAT, lng + east_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))


def test_parked_bus_with_gps_wobble_shows_zero_and_does_not_move():
    meter, rng, t0 = Speedometer(), random.Random(1), time.time()
    shown = set()
    for i in range(30):                                   # 30 s parked, GPS jumps up to ~6 m each second
        lat, lng = _offset(*START, rng.uniform(-6, 6), rng.uniform(-6, 6))
        r = meter.update(lat, lng, accuracy_m=12, fix_time=t0 + i)
        if i >= 4:
            assert r.speed_kmh == 0 and r.stopped
            shown.add((r.latitude, r.longitude))
    assert len(shown) == 1                                # the marker stays put


def test_parked_bus_ignores_small_gps_speed_noise():
    meter, t0 = Speedometer(), time.time()
    for i in range(10):
        r = meter.update(*_offset(*START, i % 2 * 3, 0), accuracy_m=10, gps_speed_kmh=4.0, fix_time=t0 + i)
    assert r.speed_kmh == 0


def test_moving_bus_speed_from_positions():
    meter, t0 = Speedometer(), time.time()
    for i in range(20):                                   # 30 km/h = 8.33 m/s, no GPS speed
        r = meter.update(*_offset(*START, 8.333 * i, 0), accuracy_m=8, fix_time=t0 + i)
    assert 28 <= r.speed_kmh <= 32
    assert abs(r.heading_deg - 0) < 2                     # driving north


def test_moving_bus_uses_gps_speed():
    meter, t0 = Speedometer(), time.time()
    for i in range(10):
        r = meter.update(*_offset(*START, 11.1 * i, 0), accuracy_m=5, gps_speed_kmh=40.0, fix_time=t0 + i)
    assert r.speed_kmh == 40.0


def test_bus_stops_then_shows_zero():
    meter, t0 = Speedometer(), time.time()
    for i in range(10):
        meter.update(*_offset(*START, 8.333 * i, 0), accuracy_m=8, fix_time=t0 + i)
    stop = _offset(*START, 8.333 * 9, 0)
    for i in range(10, 20):
        r = meter.update(*stop, accuracy_m=8, fix_time=t0 + i)
    assert r.speed_kmh == 0


def test_very_inaccurate_fix_is_ignored():
    meter, t0 = Speedometer(), time.time()
    for i in range(5):
        meter.update(*START, accuracy_m=8, fix_time=t0 + i)
    r = meter.update(*_offset(*START, 400, 0), accuracy_m=500, fix_time=t0 + 5)
    assert not r.use_fix and (r.latitude, r.longitude) == START


def test_parked_gps_box_shows_zero_on_the_map(gps_box):
    """End to end: a parked bus whose GPS box sends wobbly fixes every second shows 0 km/h to riders."""
    rng = random.Random(7)
    for _ in range(12):
        lat, lng = _offset(*START, rng.uniform(-5, 5), rng.uniform(-5, 5))
        assert gps_box(lat=lat, lng=lng, speed_kmh=rng.uniform(0, 1.5), hdop=2.0).status_code == 200
    from services import tracking
    assert tracking.get_bus("KU-BUS-01").to_dict()["speed_kmh"] == 0
