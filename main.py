#!/usr/bin/env python3
"""
Printer Middleware - Enterprise-grade printer management system
"""

import sys
import argparse
import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from app.api.routes import api
from app.version import get_version, get_version_info
from app.utils.logger import log

def create_app():
    """Create and configure the Flask application"""
    load_dotenv()

    app = Flask(__name__)
    cors_origins = os.getenv("CORS_ORIGINS", "*")
    CORS(app, origins=cors_origins)

    # Register blueprints
    app.register_blueprint(api)

    # Add version endpoint
    @app.route("/version")
    def version():
        return get_version_info()

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
    else:
        # Production mode - could use Waitress here
        app.run(host=args.host, port=args.port, threaded=True, ssl_context=ssl_context)

if __name__ == "__main__":
    main()
    
