"""
Live buses: the public bus feed for the maps (no sign-in, read only).

  GET  /api/buses            every bus right now (?audience=student|teacher|staff)
  GET  /api/buses/stream     the same, pushed live as Server-Sent Events

The positions come from the GPS box in each bus: see controllers/device_controller.py.
"""

import time

from flask import Blueprint, Response, stream_with_context

from controllers.helpers import audience_arg, ok
from services import tracking

bus_bp = Blueprint("buses", __name__)

STREAM_KEEPALIVE_S = 15.0    # send a comment line this often so proxies keep the connection open
STREAM_COALESCE_S = 0.08     # group changes that arrive together (several buses at once)


@bus_bp.get("/api/buses")
def list_buses():
    """Every bus (or only one rider type's buses) with live position, route and trail."""
    buses = tracking.all_buses(audience_arg())
    return ok(count=len(buses), buses=buses, now=time.time())


@bus_bp.get("/api/buses/stream")
def stream_buses():
    """
    Live bus feed (Server-Sent Events). The browser's EventSource keeps this open.
    First message: every bus ("snapshot"). After that only what moved ("delta", a few
    hundred bytes), pushed the moment a bus's GPS box sends a position.
    See TrackingService.feed_message().
    """
    audience = audience_arg()

    def events():
        yield "retry: 2000\n\n"                      # browser reconnects after 2 s if the line drops
        version = -1
        while True:
            new_version, message = tracking.feed_message(version, audience)
            if new_version != version:
                version = new_version
                if message:
                    yield f"data: {message}\n\n"
                time.sleep(STREAM_COALESCE_S)
                continue
            if tracking.wait_for_change(version, timeout=STREAM_KEEPALIVE_S) == version:
                # keep-alive: holds the line open through proxies, and syncs the map's clock
                yield f'data: {{"type":"ping","now":{time.time():.3f}}}\n\n'

    return Response(stream_with_context(events()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
