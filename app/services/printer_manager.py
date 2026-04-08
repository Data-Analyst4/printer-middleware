import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict

from app.services.connection_manager import ConnectionManager
from app.services.printer_protocol import extract_single_command
from app.utils.logger import log
from app.utils.validator import validate_request

PERSIST_PRINTERS = os.getenv("PERSIST_PRINTERS", "true").lower() == "true"
CONFIG_PATH = "config/printers.json"
SEND_RETRIES = max(1, int(os.getenv("PRINTER_SEND_RETRIES", "1")))

# printer_id -> {"ip": str, "port": int, "last_status": str, "connection": ConnectionManager}
PRINTERS: Dict[str, Dict[str, Any]] = {}

# Lightweight in-memory request history for compatibility with /job and /jobs.
REQUEST_RESULTS: Dict[str, Dict[str, Any]] = {}
RESULTS_LOCK = threading.Lock()


def load_printers() -> Dict[str, Dict[str, Any]]:
    if not PERSIST_PRINTERS:
        return {}
    if not os.path.exists(CONFIG_PATH):
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception as exc:
        log(f"Error loading printers config: {exc}")
        return {}


def save_printers():
    if not PERSIST_PRINTERS:
        return
    data = {printer_id: {"ip": p["ip"], "port": p["port"]} for printer_id, p in PRINTERS.items()}
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def register_printer(printer_id: str, ip: str, port: int):
    if printer_id in PRINTERS:
        existing = PRINTERS[printer_id]
        existing["ip"] = ip
        existing["port"] = port
        existing["connection"].update_target(ip, port)
        return

    PRINTERS[printer_id] = {
        "ip": ip,
        "port": port,
        "last_status": "idle",
        "connection": ConnectionManager(printer_id, ip, port),
    }


def _store_result(result: Dict[str, Any]):
    with RESULTS_LOCK:
        REQUEST_RESULTS[result["job_id"]] = result


def _build_metrics() -> Dict[str, int]:
    with RESULTS_LOCK:
        total = len(REQUEST_RESULTS)
        completed = sum(1 for value in REQUEST_RESULTS.values() if value.get("status") == "completed")
        failed = sum(1 for value in REQUEST_RESULTS.values() if value.get("status") == "failed")
    return {"total": total, "completed": completed, "failed": failed}


def _send_command(printer_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
    printer = PRINTERS[printer_id]
    connection: ConnectionManager = printer["connection"]

    for attempt in range(1, SEND_RETRIES + 1):
        try:
            response = connection.send_command(command)
            result = {
                "attempt": attempt,
                "command": command,
                "ok": response.get("ok", False),
                "reason": response.get("reason"),
                "response_command": response.get("response_command"),
                "response_status": response.get("response_status"),
                "protocol_error_code": response.get("protocol_error_code"),
                "protocol_error_description": response.get("protocol_error_description"),
                "raw_response": response.get("raw_response"),
                "response": response.get("response"),
                "details": response,
            }

            printer["last_status"] = "connected" if result["ok"] else "error"
            if result["ok"] or attempt >= SEND_RETRIES:
                return result

            printer["last_status"] = "error"
        except Exception as exc:
            printer["last_status"] = "error"
            message = str(exc)
            result = {
                "attempt": attempt,
                "command": command,
                "ok": False,
                "reason": message,
                "error_type": "transport_exception",
                "raw_response": None,
                "response": None,
                "details": None,
            }
            if attempt >= SEND_RETRIES:
                return result

    return {
        "attempt": SEND_RETRIES,
        "command": command,
        "ok": False,
        "reason": "Command send failed",
        "raw_response": None,
        "response": None,
        "details": None,
    }


def handle_print_request(data: Dict[str, Any]) -> Dict[str, Any]:
    valid, error = validate_request(data)
    if not valid:
        return {"success": False, "error": error}

    printer_id = data["printer_id"]
    ip = data["printer"]["ip"]
    port = data["printer"]["port"]
    job_id = str(uuid.uuid4())

    try:
        command = extract_single_command(data)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    register_printer(printer_id, ip, port)
    save_printers()

    log(
        f"Direct send request {job_id}: printer={printer_id} target={ip}:{port} "
        f"command={command.get('command')}"
    )

    command_result = _send_command(printer_id, command)
    success = command_result["ok"]

    result = {
        "success": success,
        "job_id": job_id,
        "status": "completed" if success else "failed",
        "execution_mode": "sync",
        "printer_id": printer_id,
        "printer": {"ip": ip, "port": port},
        "command": command,
        "response": command_result,
        "printer_ok": command_result.get("ok"),
        "printer_reason": command_result.get("reason"),
        "printer_response_command": command_result.get("response_command"),
        "printer_response_status": command_result.get("response_status"),
        "printer_protocol_error_code": command_result.get("protocol_error_code"),
        "printer_protocol_error_description": command_result.get("protocol_error_description"),
        "printer_raw_response": command_result.get("raw_response"),
        "printer_response_payload": command_result.get("response"),
        "error": None if success else command_result.get("reason"),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    _store_result(result)
    return result


def get_all_printers() -> Dict[str, Dict[str, Any]]:
    return {
        printer_id: {
            "ip": printer["ip"],
            "port": printer["port"],
            "connection_status": str(printer.get("last_status", "idle")),
            "socket_connected": bool(printer["connection"].connected),
        }
        for printer_id, printer in PRINTERS.items()
    }


def get_job_result(job_id: str) -> Dict[str, Any]:
    with RESULTS_LOCK:
        result = REQUEST_RESULTS.get(job_id)
    if not result:
        return {"success": False, "error": "Job not found"}
    return {"success": True, **result}


def get_all_jobs() -> Dict[str, Any]:
    with RESULTS_LOCK:
        jobs = list(REQUEST_RESULTS.values())
    return {"success": True, "jobs": jobs}


def get_metrics() -> Dict[str, Any]:
    return {"success": True, **_build_metrics()}


# Load printer targets from config on startup.
for printer_id, cfg in load_printers().items():
    register_printer(printer_id, cfg["ip"], cfg["port"])
