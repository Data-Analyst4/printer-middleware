from flask import Blueprint, request, jsonify, redirect, send_file

from app.services.pod_device_manager import (
    delete_pod_device,
    get_all_pod_devices,
    get_pod_device,
    upsert_pod_device,
)
from app.services.printer_manager import (
    handle_print_request,
    get_all_printers,
    get_job_result,
    get_all_jobs,
    get_metrics
)
from app.utils.auth import (
    PUBLIC_PATHS,
    dashboard_auth_enabled,
    login_user,
    logout_user,
    request_authorized,
    session_authenticated,
    verify_dashboard_credentials,
)

api = Blueprint("api", __name__)


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
        return send_file("dashboard/login.html")

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


@api.route("/print", methods=["POST"])
def print_label():
    data = request.json
    result = handle_print_request(data)
    return jsonify(result)

@api.route("/job/<job_id>", methods=["GET"])
def get_job_status(job_id):
    result = get_job_result(job_id)
    return jsonify(result)

@api.route("/jobs", methods=["GET"])
def get_jobs():
    result = get_all_jobs()
    return jsonify(result)

@api.route("/printers", methods=["GET"])
def printers():
    return jsonify(get_all_printers())

@api.route("/metrics", methods=["GET"])
def metrics():
    return jsonify(get_metrics())

@api.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "printer-middleware"})


@api.route("/pod-devices", methods=["GET"])
def list_pod_devices():
    return jsonify(get_all_pod_devices())


@api.route("/pod-devices/<device_id>", methods=["GET"])
def get_pod_device_route(device_id):
    device = get_pod_device(device_id)
    if not device:
        return jsonify({"success": False, "error": "Device not found"}), 404
    return jsonify({"success": True, "device_id": device_id, "device": device})


@api.route("/pod-devices/<device_id>", methods=["PUT"])
def upsert_pod_device_route(device_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    result = upsert_pod_device(device_id, data)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@api.route("/pod-devices/<device_id>", methods=["DELETE"])
def delete_pod_device_route(device_id):
    result = delete_pod_device(device_id)
    if not result.get("success"):
        return jsonify(result), 404
    return jsonify(result)

@api.route("/")
def dashboard():
    return send_file("dashboard/index.html")
