from flask import Blueprint, request, jsonify, send_file
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

api = Blueprint("api", __name__)

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