"""
Pretend to be a GPS box (ESP32 + NEO-6M) - for testing BusPlus without the hardware.

It sends exactly what the real firmware sends: one report every 2 seconds to
/api/device/location with the device's key, driving along its bus's route at ~30 km/h.

    1. Start BusPlus:                     python app.py
    2. In the backend: GPS devices > Add a device (Manually or Quick add), copy the Device key.
    3. In another terminal:               python tools/simulate_gps_box.py <device key>
       (other server:                     python tools/simulate_gps_box.py <key> --server https://bus.example.com)
    4. Watch the bus move on the Live map / a student map. Ctrl+C stops it.

Without a key it asks to join by itself, like a new box:
    python tools/simulate_gps_box.py
    -> it prints a pairing code; approve it in the backend (GPS devices > Add a device > Automatically).
"""

import argparse
import math
import secrets
import sys
import time
from datetime import UTC, datetime

import requests

EARTH_RADIUS_M = 6_371_008.8


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Straight-line distance between two (lat, lng) points in metres."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Compass direction from a to b in degrees."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def points_along(line: list[tuple[float, float]], step_m: float):
    """(lat, lng, course) every step_m metres along the line."""
    carry = 0.0
    for a, b in zip(line, line[1:], strict=False):
        length = distance_m(a, b)
        if length <= 0:
            continue
        course = bearing(a, b)
        pos = carry
        while pos < length:
            t = pos / length
            yield a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, course
            pos += step_m
        carry = pos - length
    yield line[-1][0], line[-1][1], 0.0


def report(server: str, key: str, body: dict) -> dict:
    resp = requests.post(f"{server}/api/device/location", json=body, headers={"X-Device-Key": key}, timeout=10)
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200:
        sys.exit(f"Server answered {resp.status_code}: {data.get('error') or resp.text[:200]}")
    return data


def ask_to_join(server: str, chip_id: str) -> str:
    """Ask to join like a new box, until the admin approves it. Returns the device key."""
    token = secrets.token_hex(16)
    print(f"Asking to join as chip {chip_id}. Approve it in the backend: GPS devices > Add a device > Automatically.")
    shown = False
    while True:
        resp = requests.post(f"{server}/api/device/pair", json={"chip_id": chip_id, "token": token, "fw": "simulator"},
                             timeout=10)
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if data.get("status") == "approved":
            print(f"Approved as {data.get('device_id')}. Key received.")
            return data["key"]
        if resp.status_code != 200:
            sys.exit(f"Server answered {resp.status_code}: {data.get('error') or resp.text[:200]}")
        if not shown:
            print(f"Pairing code: {data['code']}  (the backend shows the same code)")
            shown = True
        time.sleep(float(data.get("retry_s", 5)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pretend to be a BusPlus GPS box.")
    parser.add_argument("key", nargs="?", help="the Device key from the backend (leave out: ask to join by itself)")
    parser.add_argument("--chip", default=None, help="chip ID to ask to join with (default: a random one)")
    parser.add_argument("--server", default="http://127.0.0.1:5000", help="BusPlus address (default: %(default)s)")
    parser.add_argument("--speed", type=float, default=30.0, help="driving speed in km/h (default: %(default)s)")
    args = parser.parse_args()
    server = args.server.rstrip("/")
    if not args.key:
        try:
            args.key = ask_to_join(server, (args.chip or secrets.token_hex(6)).upper())
        except KeyboardInterrupt:
            print("\nStopped.")
            return

    # 1. A heartbeat without position (like the real box while it searches for satellites)
    first = report(server, args.key, {"fix": False, "sats": 3, "fw": "simulator"})
    bus_id, every = first["bus_id"], float(first.get("send_every_s", 2))
    bus = next(b for b in requests.get(f"{server}/api/buses", timeout=10).json()["buses"] if b["bus_id"] == bus_id)
    route = next(r for r in requests.get(f"{server}/api/routes", timeout=10).json()["routes"]
                 if r["route_id"] == bus["assigned_route_id"])
    line = [(p["lat"], p["lng"]) for p in route["polyline_waypoints"]]
    print(f"Driving {bus['bus_number']} along {route['route_name']} ({route['length_km']} km) "
          f"at {args.speed:.0f} km/h, one report every {every:g} s. Ctrl+C to stop.")

    # 2. Drive along the route
    step_m = args.speed / 3.6 * every
    try:
        for lat, lng, course in points_along(line, step_m):
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            report(server, args.key, {"fix": True, "lat": round(lat, 6), "lng": round(lng, 6),
                                      "speed_kmh": args.speed, "course": round(course, 1), "sats": 9,
                                      "hdop": 0.9, "age_ms": 150, "time": now, "fw": "simulator"})
            print(f"  {lat:.6f}, {lng:.6f}", end="\r")
            time.sleep(every)
    except KeyboardInterrupt:
        print("\nStopped. The bus goes offline by itself after a few minutes without GPS.")
        return
    print("\nArrived at the end of the route.")


if __name__ == "__main__":
    main()
