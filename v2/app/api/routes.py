"""HTTP API routes — v1-compatible sync print + v2 async queue."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, redirect, request, send_file

from app.core.bootstrap import get_context
from app.utils.auth import (
    PUBLIC_PATHS,
    dashboard_auth_enabled,
    login_user,
    logout_user,
    request_authorized,
    session_authenticated,
    verify_dashboard_credentials,
)
from app.version import get_version_info

api = Blueprint("api", __name__)


def _dashboard_dir() -> str:
    return os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "dashboard")
    )


def _wants_html() -> bool:
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "text/html" and (
        request.accept_mimetypes["text/html"] >= request.accept_mimetypes["application/json"]
    )


@api.before_request
def _auth_guard():
    path = request.path
    if path in PUBLIC_PATHS or path == "/logout":
        return None

    if request_authorized(request):
        return None

    if dashboard_auth_enabled() and (path == "/" or _wants_html()):
        return redirect("/login")
    return jsonify({"success": False, "error": "Unauthorized"}), 401


@api.route("/login", methods=["GET", "POST"])
def login():
    if not dashboard_auth_enabled():
        return redirect("/")

    if request.method == "GET":
        if session_authenticated():
            return redirect("/")
        return send_file(os.path.join(_dashboard_dir(), "login.html"))

    data = request.get_json(silent=True)
    if isinstance(data, dict):
        username = str(data.get("username") or "")
        password = str(data.get("password") or "")
    else:
        username = request.form.get("username", "")
        password = request.form.get("password", "")

    if not verify_dashboard_credentials(username, password):
        if request.is_json or request.accept_mimetypes.best == "application/json":
            return jsonify({"success": False, "error": "Invalid username or password"}), 401
        return redirect("/login?error=1")

    login_user(username.strip())
    if request.is_json or (
        request.accept_mimetypes.best == "application/json"
        and request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]
    ):
        return jsonify({"success": True})
    return redirect("/")


@api.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    if request.method == "POST" and (
        request.is_json or request.accept_mimetypes.best == "application/json"
    ):
        return jsonify({"success": True})
    if dashboard_auth_enabled():
        return redirect("/login")
    return redirect("/")


@api.route("/health", methods=["GET"])
def health():
    ctx = get_context()
    return jsonify(
        {
            "status": "healthy",
            "service": "printer-middleware-v2",
            "version": get_version_info()["version"],
            "network": ctx.network.snapshot(),
            "queue_enabled": ctx.settings.queue_enabled,
        }
    )


@api.route("/version", methods=["GET"])
def version():
    return jsonify(get_version_info())


@api.route("/print", methods=["POST"])
def print_sync():
    ctx = get_context()
    result = ctx.print_service.handle_sync_print(request.get_json(silent=True) or {})
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@api.route("/print/data", methods=["POST"])
def print_data_async():
    ctx = get_context()
    data = request.get_json(silent=True) or {}
    printer_id = data.get("printer_id")
    if printer_id:
        ctx.consumers.ensure_consumer(str(printer_id))
    result = ctx.print_service.enqueue_data(data)
    status = 202 if result.get("status") == "queued" else 400
    return jsonify(result), status


@api.route("/print/item/<item_id>", methods=["GET"])
def get_print_item(item_id):
    ctx = get_context()
    return jsonify(ctx.print_service.get_item(item_id))


@api.route("/print/items", methods=["GET"])
def list_print_items():
    ctx = get_context()
    printer_id = request.args.get("printer_id")
    status = request.args.get("status")
    items = ctx.store.list_items(printer_id=printer_id, status=status, limit=200)
    return jsonify({"success": True, "items": items})


@api.route("/job/<job_id>", methods=["GET"])
def get_job(job_id):
    ctx = get_context()
    return jsonify(ctx.print_service.get_job(job_id))


@api.route("/jobs", methods=["GET"])
def list_jobs():
    ctx = get_context()
    return jsonify(ctx.print_service.list_jobs())


@api.route("/printers", methods=["GET"])
def printers():
    ctx = get_context()
    depths = ctx.store.queue_depths()
    return jsonify({"success": True, "printers": ctx.registry.all_status(depths)})


@api.route("/metrics", methods=["GET"])
def metrics():
    ctx = get_context()
    return jsonify(ctx.print_service.metrics())


@api.route("/")
def dashboard():
    return send_file(os.path.join(_dashboard_dir(), "index.html"))
