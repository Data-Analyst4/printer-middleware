from flask import Blueprint, request, jsonify, send_file
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

@api.route("/")
def dashboard():
    return send_file("dashboard/index.html")