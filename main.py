#!/usr/bin/env python3
"""
Printer Middleware - Enterprise-grade printer management system
"""

import sys
import argparse
import os
from datetime import timedelta
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from app.api.routes import api
from app.version import get_version, get_version_info
from app.utils.auth import api_key_expected, dashboard_auth_enabled, flask_secret_key
from app.utils.logger import log

def create_app():
    """Create and configure the Flask application"""
    load_dotenv()

    app = Flask(__name__)
    app.secret_key = flask_secret_key()
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    cors_origins = os.getenv("CORS_ORIGINS", "*")
    CORS(app, origins=cors_origins, supports_credentials=True)

    # Register blueprints
    app.register_blueprint(api)

    # Add version endpoint
    @app.route("/version")
    def version():
        return get_version_info()

    if dashboard_auth_enabled():
        log("Dashboard login enabled (DASHBOARD_USER / DASHBOARD_PASSWORD)")
        if not api_key_expected():
            log(
                "API_KEY is not set - ERP/print clients must use a logged-in session "
                "or set API_KEY for machine access",
                level="WARNING",
            )
    elif api_key_expected():
        log("API key auth enabled (API_KEY)")

    return app

def main():
    """Main entry point for the application"""
    parser = argparse.ArgumentParser(description="Printer Middleware Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind to")
    parser.add_argument("--cert", help="Path to SSL certificate (PEM)")
    parser.add_argument("--key", help="Path to SSL key (PEM)")
    parser.add_argument("--version", action="store_true", help="Show version information")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    if args.version:
        version_info = get_version_info()
        print(f"Printer Middleware v{version_info['version']}")
        print(f"Built for enterprise-grade printer management")
        return

    app = create_app()

    log(f"Starting Printer Middleware v{get_version()}")
    log(f"Server will be available at http://{args.host}:{args.port}")

    ssl_context = None
    cert_path = args.cert or os.getenv("SSL_CERT")
    key_path = args.key or os.getenv("SSL_KEY")
    if cert_path and key_path:
        ssl_context = (cert_path, key_path)
        log(f"TLS enabled with cert={cert_path}, key={key_path}")

    if args.debug:
        app.run(host=args.host, port=args.port, debug=True, threaded=True, ssl_context=ssl_context)
    elif ssl_context:
        app.run(host=args.host, port=args.port, threaded=True, ssl_context=ssl_context)
    else:
        from waitress import serve

        log("Using Waitress WSGI server (Windows service mode)")
        serve(app, host=args.host, port=args.port, threads=8)

if __name__ == "__main__":
    main()
    
