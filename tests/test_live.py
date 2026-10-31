"""
Live tracking: small messages for open maps, buses kept on the road, trail gaps filled along the road.
"""

import json
import time

from services import tracking
from services.route_geometry import RoutePath


def _route_and_bus():
    bus = tracking.all_buses()[0]
    route = tracking.get_route(bus["assigned_route_id"])
    return bus["bus_id"], [(p["lat"], p["lng"]) for p in route.polyline_waypoints]


def test_route_path_measures_along_the_road():
    path = RoutePath([(22.80, 89.50), (22.80, 89.51), (22.81, 89.51)])
    on = path.project(22.8003, 89.505)                     # ~33 m north of the first leg
    assert 30 < on.distance_m < 36 and abs(on.latitude - 22.80) < 1e-9
    lat, lng, heading = path.point_at(path.cum[1] + 100)    # 100 m up the second leg, heading north
    assert abs(lng - 89.51) < 1e-9 and lat > 22.80 and round(heading) == 0
    assert path.between(0, path.length) == [[22.80, 89.51]]


def test_maps_get_small_deltas_after_the_first_snapshot(app):
    with app.app_context():
        bus_id, line = _route_and_bus()
        version, first = tracking.feed_message(-1)
        assert json.loads(first)["type"] == "snapshot"
        tracking.start_trip(bus_id)
        version, _ = tracking.feed_message(version)
        t0 = time.time()
        tracking.update_location(bus_id, *line[3], speed_kmh=30, accuracy_m=5, fix_time=t0)
        tracking.update_location(bus_id, *line[6], speed_kmh=30, accuracy_m=5, fix_time=t0 + 1)
        version2, delta = tracking.feed_message(version)
        data = json.loads(delta)
        assert data["type"] == "delta" and len(data["buses"]) == 1
        bus = data["buses"][0]
        assert {"current_latitude", "progress_m", "sample_t", "trail_add"} <= set(bus)
        assert "bus_name" not in bus and len(delta) < 2000
        assert tracking.feed_message(version)[1] is delta    # made once, shared by every map
        assert tracking.feed_message(version2) == (version2, None)


def test_trail_gap_follows_the_road_not_a_straight_line(app):
    with app.app_context():
        bus_id, line = _route_and_bus()
        tracking.start_trip(bus_id)
        t0 = time.time()
        tracking.update_location(bus_id, *line[2], speed_kmh=30, accuracy_m=5, fix_time=t0)
        tracking.update_location(bus_id, *line[30], speed_kmh=30, accuracy_m=5, fix_time=t0 + 20)  # phone was off
        trail = next(b for b in tracking.all_buses() if b["bus_id"] == bus_id)["trail"]
        assert len(trail) > 10                                 # the road between, not 2 points
        road = {(round(lat, 5), round(lng, 5)) for lat, lng in line}
        assert sum((round(p[0], 5), round(p[1], 5)) in road for p in trail) >= len(trail) - 2
