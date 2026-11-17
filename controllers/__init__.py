"""
BusPlus controllers (Flask blueprints): each file groups the URLs of one area.

  view_controller    front-end pages
  auth_controller    sign-in / sign-out
  bus_controller     live buses for the maps
  route_controller   routes + arrival alerts
  admin_controller   the backend admin panel and its API
  device_controller  positions from the GPS tracker boxes (ESP32 + NEO-6M)
"""

from controllers.admin_controller import admin_bp
from controllers.auth_controller import auth_bp
from controllers.bus_controller import bus_bp
from controllers.device_controller import device_bp
from controllers.route_controller import route_bp
from controllers.view_controller import view_bp

ALL_BLUEPRINTS = (view_bp, auth_bp, bus_bp, route_bp, admin_bp, device_bp)
