"""HTTP API routes — v1-compatible sync print + v2 async queue."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request, send_file

from app.core.bootstrap import get_context
from app.version import get_version_info

api = Blueprint("api", __name__)


def _check_api_key() -> bool:
    ctx = get_context()
    expected = ctx.settings.api_key
    if not expected:
        return True
    provided = request.headers.get("X-API-Key") or request.args.get("api_key")
    return provided == expected


@api.before_request
def _auth_guard():
    if request.path in {"/health", "/version", "/"}:
        return None
    if not _check_api_key():
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return None


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
    dashboard_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "dashboard", "index.html")
    return send_file(os.path.abspath(dashboard_path))
