from flask import Blueprint, request, jsonify, send_file
from app.services.printer_manager import (
    handle_print_request,
    get_all_printers,
    get_job_result,
    get_all_jobs,
    get_metrics,
    upsert_printer_config,
    delete_printer_config,
)
from app.services.test_print_manager import (
    handle_test_print_request,
    get_test_job_result,
    get_all_test_jobs,
    list_test_scenarios,
    set_test_scenario,
    reset_test_printer,
    get_test_printer_state,
)
from app.services.log_reader import read_app_json_logs

api = Blueprint("api", __name__)

@api.route("/print", methods=["POST"])
def print_label():
    data = request.json
    result = handle_print_request(data)
    return jsonify(result)


@api.route("/test-print", methods=["POST"])
def test_print_label():
    data = request.json
    result = handle_test_print_request(data)
    return jsonify(result)


@api.route("/test-print/job/<job_id>", methods=["GET"])
def get_test_job_status(job_id):
    result = get_test_job_result(job_id)
    return jsonify(result)


@api.route("/test-print/jobs", methods=["GET"])
def get_test_jobs():
    result = get_all_test_jobs()
    return jsonify(result)


@api.route("/test-print/scenarios", methods=["GET"])
def get_test_scenarios():
    result = list_test_scenarios()
    return jsonify(result)


@api.route("/test-print/scenario/<printer_id>", methods=["PUT"])
def update_test_scenario(printer_id):
    data = request.json or {}
    result = set_test_scenario(printer_id, data)
    return jsonify(result)


@api.route("/test-print/state/<printer_id>", methods=["GET"])
def test_printer_state(printer_id):
    result = get_test_printer_state(printer_id)
    return jsonify(result)


@api.route("/test-print/state/<printer_id>/reset", methods=["POST"])
def reset_test_printer_state(printer_id):
    result = reset_test_printer(printer_id)
    return jsonify(result)


@api.route("/logs/app.json", methods=["GET"])
@api.route("/logs/app.jsonl", methods=["GET"])
def read_app_json_logs_endpoint():
    result = read_app_json_logs(request.args.to_dict())
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

@api.route("/printers", methods=["POST"])
def upsert_printer():
    data = request.json
    result = upsert_printer_config(data)
    return jsonify(result)

@api.route("/printers/<printer_id>", methods=["PUT"])
def update_printer(printer_id):
    data = request.json or {}
    result = upsert_printer_config(data, printer_id_override=printer_id)
    return jsonify(result)

@api.route("/printers/<printer_id>", methods=["DELETE"])
def delete_printer(printer_id):
    result = delete_printer_config(printer_id)
    return jsonify(result)

@api.route("/metrics", methods=["GET"])
def metrics():
    return jsonify(get_metrics())

@api.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "printer-middleware"})

@api.route("/")
def dashboard():
    return send_file("dashboard/index.html")
