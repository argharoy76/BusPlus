"""
BusPlus - live bus tracker for Khulna University.

`create_app()` builds the Flask app (the "application factory"):
  1. loads settings from config.py / .env
  2. switches on security: CSRF tokens, login rate limits, security headers, secure cookies
  3. opens the database, creates the tables and fills an empty database once
  4. loads routes, buses and drivers into memory and registers all URLs

Run on your computer:   python app.py
Run on the server:      gunicorn -c gunicorn.conf.py wsgi:app   (see DEPLOYMENT.md)
"""

import os
from pathlib import Path

try:
    from flask import Flask, jsonify, request
    from flask_wtf.csrf import CSRFError
    from werkzeug.middleware.proxy_fix import ProxyFix

    from config import Config
    from content import branding, colors, map_settings, rules
    from controllers import ALL_BLUEPRINTS
    from extensions import csrf, db, limiter, talisman
    from models.rider_types import DRIVER, RIDER_TYPES
    from services import schedule_service, store, trackers, tracking, users
    from services.words import fill, page_words, say, words
except ModuleNotFoundError as missing:
    # A library from requirements.txt isn't installed yet: say how to fix it instead of a long error.
    raise SystemExit(f"\nMissing library: {missing.name}\nInstall BusPlus's libraries first, then start again:\n"
                     "    pip install -r requirements.txt\n    python app.py\n") from missing

# Content-Security-Policy: the browser may only load scripts, styles, fonts and
# data from this site, plus map tiles from Google. Blocks injected third-party code.
CONTENT_SECURITY_POLICY = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",        # pages keep a few small inline scripts
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: https://*.google.com",  # Google map tiles: mt0..mt3.google.com
    "font-src": "'self'",
    "connect-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'",
    "frame-ancestors": "'none'",
}

# Phones need location access for the driver's GPS; nothing else is allowed.
PERMISSIONS_POLICY = {"geolocation": "(self)", "camera": "()", "microphone": "()"}


def create_app(config_class: type[Config] = Config) -> Flask:
    """Build and return the BusPlus Flask app."""
    config_class.check_production()

    app = Flask(__name__)
    app.config.from_object(config_class)

    # Behind nginx: trust its X-Forwarded-For / -Proto headers so we see real IPs and https.
    if app.config["TRUSTED_PROXIES"]:
        hops = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

    # Security extensions
    csrf.init_app(app)
    limiter.init_app(app)
    talisman.init_app(
        app,
        force_https=app.config["FORCE_HTTPS"],
        strict_transport_security=app.config["FORCE_HTTPS"],
        session_cookie_secure=app.config["SESSION_COOKIE_SECURE"],
        content_security_policy=CONTENT_SECURITY_POLICY,
        permissions_policy=PERMISSIONS_POLICY,
        referrer_policy="strict-origin-when-cross-origin",
    )

    # Database: create missing tables, add the built-in routes/buses on the very first start,
    # then load everything into memory for the live map.
    db.init_app(app)
    with app.app_context():
        db.create_all()
        store.seed_defaults(with_demo_drivers=app.config["SEED_DEMO_DRIVERS"])
        tracking.load()
        users.load()
        trackers.load()
        schedule_service.seed_timetables()
        for driver in users.all_drivers():
            tracking.show_driver_on_bus(driver.driver_id, driver.full_name, driver.assigned_bus_id)

    tracking.start_auto_offline()          # buses whose GPS stopped long ago go offline by themselves

    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)
    _register_error_handlers(app)
    _add_static_versions(app)

    @app.template_filter("clock")
    def clock(hhmm: str) -> str:
        """24-hour "13:30" -> "01:30 PM" (used for bus schedule times in templates)."""
        hours, minutes = (int(part) for part in hhmm.split(":"))
        return f"{hours % 12 or 12:02d}:{minutes:02d} {'AM' if hours < 12 else 'PM'}"

    @app.context_processor
    def content_for_templates() -> dict:
        """Settings from the content/ folder, available in every HTML template."""
        return {
            "brand": branding,                    # {{ brand.APP_NAME }}, {{ brand.LOGO_EMOJI }} (content/branding.py)
            "theme": colors.THEME,                # colours -> CSS variables (templates/_theme.html)
            "words": words,                       # {% set t = words("rider_map") %} {{ t("Home") }}
            "page_words": page_words,             # the same words for the page's JavaScript
            "tab_title": _tab_title,              # browser tab title (content/branding.py)
            "rider_types": RIDER_TYPES,           # Student, Teacher, ... (content/user_types.py)
            "driver_button": DRIVER,
            "pin_rules": {"min": rules.PIN_MIN_DIGITS, "max": rules.PIN_MAX_DIGITS},
            # Map and timing settings for the map pages' JavaScript (templates/_map_assets.html)
            "map_config": {
                "layers": map_settings.MAP_LAYERS,
                "zoom": map_settings.MAP_START_ZOOM,
                "credit": map_settings.MAP_CREDIT,
                "defaultHome": map_settings.DEFAULT_HOME,
                "trailColor": colors.THEME["bus_trail"],
                "gpsSendEveryMs": int(rules.GPS_SEND_EVERY_SECONDS * 1000),
                "gpsSendAfterMeters": rules.GPS_SEND_AFTER_METERS,
                "refreshMs": int(rules.MAP_REFRESH_SECONDS * 1000),
                "alertMinutesMax": rules.MAX_ALERT_MINUTES,
            },
        }

    return app


def _tab_title(page: str | None = None) -> str:
    """Browser tab title, e.g. "Student login · BusPlus" (patterns in content/branding.py)."""
    pattern = branding.TAB_TITLE if page else branding.START_PAGE_TAB_TITLE
    return fill(pattern, app=branding.APP_NAME, university=branding.UNIVERSITY_NAME, page=page or "")


def _add_static_versions(app: Flask) -> None:
    """
    Add ?v=<file's last change time> to every /static/ link, e.g. /static/js/app.js?v=1730370000.

    Browsers and nginx may then cache static files for a long time, yet still pick
    up a new version right after an update (the link changes when the file changes).
    """
    static_dir = Path(app.static_folder)

    @app.url_defaults
    def static_version(endpoint: str, values: dict) -> None:
        if endpoint == "static" and "filename" in values:
            file = static_dir / values["filename"]
            if file.is_file():
                values["v"] = int(file.stat().st_mtime)


def _register_error_handlers(app: Flask) -> None:
    """Answer API errors as JSON (the pages show the message) instead of HTML error pages."""

    def wants_json() -> bool:
        return request.path.startswith("/api/")

    @app.errorhandler(CSRFError)
    def csrf_error(err):
        message = say("This page has expired. Please reload it and try again.")
        return (jsonify(success=False, message=message), 400) if wants_json() else (message, 400)

    @app.errorhandler(429)
    def too_many_requests(err):
        message = say("Too many attempts. Please wait a minute and try again.")
        return (jsonify(success=False, message=message), 429) if wants_json() else (message, 429)

    @app.errorhandler(404)
    def not_found(err):
        if wants_json():
            return jsonify(success=False, message=say("Not found.")), 404
        return say("Page not found."), 404

    @app.errorhandler(500)
    def server_error(err):
        message = say("Something went wrong on the server. Please try again.")
        return (jsonify(success=False, message=message), 500) if wants_json() else (message, 500)


if __name__ == "__main__":
    application = create_app()
    if not os.environ.get("WERKZEUG_RUN_MAIN"):          # print once, not again after each auto-restart
        print("=" * 60)
        print(" BusPlus - Khulna University bus tracker")
        print(f" App:     http://localhost:{Config.PORT}")
        print(f" Backend: http://localhost:{Config.PORT}/backend")
        print(f"          username: {Config.ADMIN_USERNAME}")
        print("          password: in instance/admin_password.txt (or BUSPLUS_ADMIN_PASSWORD in .env)")
        if Config.AUTO_RELOAD:
            print(" Auto reload is on: save your changes, then just refresh the browser.")
        print("=" * 60)
    # threaded: every open map keeps one live connection for instant bus updates.
    # use_reloader: restart by itself when you save a .py file (content/ too), see Config.AUTO_RELOAD.
    application.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG,
                    use_reloader=Config.AUTO_RELOAD, threaded=True)
