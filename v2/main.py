#!/usr/bin/env python3
"""Printer Middleware v2 — production entry point."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import Flask
from flask_cors import CORS

from app.api.routes import api
from app.core.bootstrap import init_app, shutdown_app
from app.utils.auth import api_key_expected, dashboard_auth_enabled, flask_secret_key
from app.utils.logger import log
from app.version import VERSION, get_version_info


def create_app() -> Flask:
    ctx = init_app()
    app = Flask(__name__)
    app.secret_key = flask_secret_key()
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    CORS(app, origins=ctx.settings.cors_origins, supports_credentials=True)
    app.register_blueprint(api)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Printer Middleware v2")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()

    if args.version:
        info = get_version_info()
        print(f"Printer Middleware v{info['version']} ({info['build']})")
        return

    app = create_app()
    from app.core.bootstrap import get_context

    ctx = get_context()
    host = args.host or ctx.settings.host
    port = args.port or ctx.settings.port

    log(f"Starting Printer Middleware v{VERSION} on http://{host}:{port}")

    try:
        if args.debug:
            app.run(host=host, port=port, debug=True, threaded=True)
        else:
            try:
                from waitress import serve

                log("Using Waitress WSGI server")
                serve(app, host=host, port=port, threads=8)
            except ImportError:
                log("Waitress not installed; using Flask threaded server", level="WARNING")
                app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        shutdown_app()


if __name__ == "__main__":
    main()
