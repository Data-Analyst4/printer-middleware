from functools import wraps

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
from app.services.user_manager import (
    create_user,
    delete_user,
    ensure_seed_admin,
    list_users,
    update_user,
)
from app.utils.auth import (
    PUBLIC_PATHS,
    current_session_user,
    dashboard_auth_enabled,
    is_admin,
    login_user,
    logout_user,
    request_authorized,
    session_authenticated,
    session_user_id,
    verify_dashboard_credentials,
)

api = Blueprint("api", __name__)


def _wants_html() -> bool:
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "text/html" and (
        request.accept_mimetypes["text/html"] >= request.accept_mimetypes["application/json"]
    )


def _wants_json() -> bool:
    if request.is_json:
        return True
    return (
        request.accept_mimetypes.best == "application/json"
        and request.accept_mimetypes["application/json"]
        > request.accept_mimetypes["text/html"]
    )


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not dashboard_auth_enabled():
            return jsonify({
                "success": False,
                "error": "User management requires dashboard auth. "
                         "Set DASHBOARD_USER and DASHBOARD_PASSWORD, then restart.",
            }), 403
        if not session_authenticated() or not is_admin():
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return fn(*args, **kwargs)

    return wrapper


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
    ensure_seed_admin()

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

    user = verify_dashboard_credentials(username, password)
    if not user:
        if _wants_json():
            return jsonify({"success": False, "error": "Invalid username or password"}), 401
        return redirect("/login?error=1")

    login_user(user["username"], role=user.get("role") or "admin", user_id=user.get("id"))
    if _wants_json():
        return jsonify({
            "success": True,
            "user": {
                "id": user.get("id"),
                "username": user["username"],
                "role": user.get("role") or "admin",
            },
        })
    return redirect("/")


@api.route("/logout", methods=["GET", "POST"])
def logout():
    logout_user()
    if request.method == "POST" and _wants_json():
        return jsonify({"success": True})
    if dashboard_auth_enabled():
        return redirect("/login")
    return redirect("/")


@api.route("/api/me", methods=["GET"])
def me():
    if not dashboard_auth_enabled():
        return jsonify({
            "success": True,
            "auth_enabled": False,
            "user": None,
        })
    user = current_session_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return jsonify({"success": True, "auth_enabled": True, "user": user})


@api.route("/api/users", methods=["GET"])
@admin_required
def api_list_users():
    return jsonify({"success": True, "users": list_users()})


@api.route("/api/users", methods=["POST"])
@admin_required
def api_create_user():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    result = create_user(
        username=str(data.get("username") or ""),
        password=str(data.get("password") or ""),
        role=str(data.get("role") or "operator"),
    )
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result), 201


@api.route("/api/users/<int:user_id>", methods=["PUT"])
@admin_required
def api_update_user(user_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Invalid JSON payload"}), 400

    kwargs = {}
    if "password" in data:
        kwargs["password"] = str(data.get("password") or "")
    if "role" in data:
        kwargs["role"] = str(data.get("role") or "")
    if "is_active" in data:
        kwargs["is_active"] = bool(data.get("is_active"))

    result = update_user(user_id, **kwargs)
    if not result.get("success"):
        status = 404 if result.get("error") == "User not found" else 400
        return jsonify(result), status
    return jsonify(result)


@api.route("/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id):
    if session_user_id() is not None and session_user_id() == user_id:
        return jsonify({"success": False, "error": "Cannot delete your own account"}), 400

    result = delete_user(user_id)
    if not result.get("success"):
        status = 404 if result.get("error") == "User not found" else 400
        return jsonify(result), status
    return jsonify(result)


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
