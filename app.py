"""
Khulna University Bus Tracker (BusPlus)
Main Application Entrypoint
"""

import os
from datetime import timedelta
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from config import AppConfig
from controllers import auth_bp, bus_bp, route_bp, view_bp, admin_bp

def create_app() -> Flask:
    """Factory creating and configuring the BusPlus Flask application."""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(AppConfig)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)

    # Enable CORS for cross-device mobile testing (e.g. driver using mobile phone)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register modular controllers
    app.register_blueprint(view_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(bus_bp)
    app.register_blueprint(route_bp)
    app.register_blueprint(admin_bp)

    @app.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "Khulna University BusPlus",
            "university": AppConfig.UNIVERSITY_NAME
        })

    @app.route("/api/config/maps-key", methods=["POST"])
    def update_maps_api_key():
        """Allows client to dynamically configure or update Google Maps API Key."""
        if not session.get("is_admin"):
            return jsonify({"success": False, "message": "Admin sign-in required."}), 401
        data = request.get_json(silent=True) or {}
        new_key = str(data.get("api_key", "")).strip()
        AppConfig.GOOGLE_MAPS_API_KEY = new_key
        return jsonify({
            "success": True,
            "message": "Google Maps API Key updated successfully.",
            "api_key_set": bool(new_key)
        })

    return app


if __name__ == "__main__":
    application = create_app()
    print(f"===========================================================")
    print(f" 🚌 Khulna University Bus Tracker (BusPlus) Starting...")
    print(f" 📍 University: {AppConfig.UNIVERSITY_NAME}")
    print(f" 🌐 Access Web App: http://localhost:{AppConfig.PORT}")
    print(f" 🔐 Backend admin: http://localhost:{AppConfig.PORT}/backend")
    print(f"    username: {AppConfig.ADMIN_USERNAME}")
    if os.environ.get("BUSPLUS_ADMIN_PASSWORD"):
        print("    password: (from BUSPLUS_ADMIN_PASSWORD)")
    else:
        print(f"    password: {AppConfig.ADMIN_PASSWORD}   (saved in instance/admin_password.txt)")
    print(f"===========================================================")
    # threaded: each open map keeps a live connection for instant bus updates
    application.run(host=AppConfig.HOST, port=AppConfig.PORT, debug=AppConfig.DEBUG, threaded=True)
