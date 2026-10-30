"""
Snap a route to real roads for the admin's route editor.

Asks the public OSRM router (OpenStreetMap road data) for the driving route
through the points the admin clicked. The call is made from the server
because browsers block it (CORS). Needs internet access on the server.
"""

import requests

from config import Config

USER_AGENT = "BusPlus-KU/1.0 (route editor)"
TIMEOUT_S = 15


class RoadRouterError(Exception):
    """The road router could not be reached or found no route."""


def road_path(points: list[tuple[float, float]]) -> tuple[list[list[float]], float]:
    """
    Driving line through `points` ([(lat, lng), ...]).

    Returns (path, distance_km) where path is [[lat, lng], ...] along the roads.
    Raises RoadRouterError if the router is unreachable or finds nothing.
    """
    coordinates = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)     # OSRM wants lng,lat
    try:
        response = requests.get(
            Config.ROAD_ROUTER_URL + coordinates,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as err:
        raise RoadRouterError(f"Road map not reachable ({err.__class__.__name__}).") from err

    if result.get("code") != "Ok" or not result.get("routes"):
        raise RoadRouterError("No road route found between these points.")
    best = result["routes"][0]
    path = [[round(lat, 6), round(lng, 6)] for lng, lat in best["geometry"]["coordinates"]]
    return path, round(best.get("distance", 0) / 1000, 2)
