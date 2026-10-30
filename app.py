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

from pathlib import Path

try:
    from flask import Flask, jsonify, request
    from flask_wtf.csrf import CSRFError
    from werkzeug.middleware.proxy_fix import ProxyFix

    from config import Config
    from content import colors, rules, site_text
    from controllers import ALL_BLUEPRINTS
    from extensions import csrf, db, limiter, talisman
    from models.rider_types import DRIVER, RIDER_TYPES
    from services import store, tracking, users
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
        for driver in users.all_drivers():
            tracking.show_driver_on_bus(driver.driver_id, driver.full_name, driver.assigned_bus_id)

    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)
    _register_error_handlers(app)
    _add_static_versions(app)

    @app.context_processor
    def content_for_templates() -> dict:
        """Settings from the content/ folder, available in every HTML template."""
        return {
            "site": site_text,                    # {{ site.APP_NAME }}, {{ site.UNIVERSITY_NAME }}, ...
            "rider_types": RIDER_TYPES,           # Student, Teacher, ... (content/user_types.py)
            "driver_button": DRIVER,
            "brand_color": colors.BRAND_COLOR,
            "pin_rules": {"min": rules.PIN_MIN_DIGITS, "max": rules.PIN_MAX_DIGITS},
        }

    return app


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
        message = "This page has expired. Please reload it and try again."
        return (jsonify(success=False, message=message), 400) if wants_json() else (message, 400)

    @app.errorhandler(429)
    def too_many_requests(err):
        message = "Too many attempts. Please wait a minute and try again."
        return (jsonify(success=False, message=message), 429) if wants_json() else (message, 429)

    @app.errorhandler(404)
    def not_found(err):
        return (jsonify(success=False, message="Not found."), 404) if wants_json() else ("Page not found.", 404)

    @app.errorhandler(500)
    def server_error(err):
        message = "Something went wrong on the server. Please try again."
        return (jsonify(success=False, message=message), 500) if wants_json() else (message, 500)


if __name__ == "__main__":
    application = create_app()
    print("=" * 60)
    print(" BusPlus - Khulna University bus tracker")
    print(f" App:     http://localhost:{Config.PORT}")
    print(f" Backend: http://localhost:{Config.PORT}/backend")
    print(f"          username: {Config.ADMIN_USERNAME}")
    print("          password: in instance/admin_password.txt (or BUSPLUS_ADMIN_PASSWORD in .env)")
    print("=" * 60)
    # threaded: every open map keeps one live connection for instant bus updates
    application.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)
