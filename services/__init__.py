"""
BusPlus services: the app's logic, shared by all controllers.

There is exactly one instance of each service per server process. `create_app()`
calls `load()` on them to fill them from the database.

Note: because live bus data is kept in memory, run the app as ONE process
(gunicorn.conf.py does this). Many open maps are still fine - gevent handles them.
"""

from services.tracking_service import TrackingService
from services.user_service import UserService

tracking = TrackingService()
users = UserService()

__all__ = ["tracking", "users"]
