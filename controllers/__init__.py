"""
BusPlus controllers (Flask blueprints): each file groups the URLs of one area.

  view_controller   front-end pages
  auth_controller   sign-in / sign-out
  bus_controller    live buses + the driver's phone API
  route_controller  routes + arrival alerts
  admin_controller  the backend admin panel and its API
"""

from controllers.admin_controller import admin_bp
from controllers.auth_controller import auth_bp
from controllers.bus_controller import bus_bp
from controllers.route_controller import route_bp
from controllers.view_controller import view_bp

ALL_BLUEPRINTS = (view_bp, auth_bp, bus_bp, route_bp, admin_bp)
