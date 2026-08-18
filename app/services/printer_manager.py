import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict

from app.services.connection_manager import ConnectionManager
from app.services.camera_import_forwarder import (
    forward_camera_import_after_rqlp_async,
    forward_camera_import_immediate,
    get_camera_import_flow,
    resolve_camera_target,
)
from app.services.pod_device_manager import resolve_pod_target
from app.services.pod_forwarder import build_pod_string, forward_pod_async, should_forward_pod
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


def _lock_timeout_for_command(command: Dict[str, Any]) -> float:
    """Status polls fail fast; print DATA may wait longer for the printer lock."""
    cmd = str(command.get("command", "")).upper()
    if cmd in {"RQLP", "RSAL", "RSST", "RQST", "RQAL"}:
        return float(os.getenv("PRINTER_STATUS_LOCK_TIMEOUT", "0.5"))
    return float(os.getenv("PRINTER_DATA_LOCK_TIMEOUT", "15"))


def _send_command(printer_id: str, command: Dict[str, Any]) -> Dict[str, Any]:
    printer = PRINTERS[printer_id]
    connection: ConnectionManager = printer["connection"]
    lock_timeout = _lock_timeout_for_command(command)

    for attempt in range(1, SEND_RETRIES + 1):
        try:
            response = connection.send_command(command, lock_timeout=lock_timeout)
            result = {
                "attempt": attempt,
                "command": command,
                "ok": response.get("ok", False),
                "reason": response.get("reason"),
                "error_type": response.get("error_type"),
                "response_command": response.get("response_command"),
                "response_status": response.get("response_status"),
                "protocol_error_code": response.get("protocol_error_code"),
                "protocol_error_description": response.get("protocol_error_description"),
                "raw_response": response.get("raw_response"),
                "response": response.get("response"),
                "details": response,
            }

            if response.get("error_type") == "printer_busy":
                printer["last_status"] = "busy"
                return result

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

    pod_forward_meta = None
    if should_forward_pod(command):
        target, device_id, source = resolve_pod_target(data)
        if target:
            pod_string = build_pod_string(command["data"])
            if pod_string:
                forward_pod_async(
                    job_id,
                    target["ip"],
                    target["port"],
                    pod_string,
                    device_id=device_id,
                    printer_id=printer_id,
                )
                pod_forward_meta = {
                    "attempted": True,
                    "device_id": device_id,
                    "target": f"{target['ip']}:{target['port']}",
                    "source": source,
                    "payload_length": len(pod_string),
                    "status": "sending",
                }
                log(
                    f"POD forward started {job_id}: target={target['ip']}:{target['port']} "
                    f"source={source} payload_length={len(pod_string)}",
                    job_id=job_id,
                    printer_id=printer_id,
                )

    # Default (v1.2.0): camera POST before printer send. Legacy RQLP after ACK.
    camera_import_meta = None
    cmd_name = str(command.get("command", "")).upper()
    camera_flow = get_camera_import_flow()
    if cmd_name == "DATA" and camera_flow == "immediate":
        cam_url, _cam_barcode = resolve_camera_target(data)
        if cam_url is not None:
            camera_import_meta = forward_camera_import_immediate(
                job_id,
                data,
                command.get("data"),
                printer_id=printer_id,
            )

    command_result = _send_command(printer_id, command)
    success = command_result["ok"]

    if success and cmd_name == "DATA" and camera_flow == "rqlp":
        cam_url, cam_barcode = resolve_camera_target(data)
        # Legacy: after DATA ACK, RQLP confirm then POST camera (kept for rollback)
        if cam_url is not None:
            forward_camera_import_after_rqlp_async(
                job_id,
                printer_id,
                data,
                command.get("data"),
            )
            camera_import_meta = {
                "attempted": True,
                "url": cam_url,
                "barcode": cam_barcode or "",
                "missing_barcode": not bool(cam_barcode),
                "status": "awaiting_rqlp",
                "flow": "rqlp",
                "erp_alert_recommended": not bool(cam_barcode),
                "alert_reasons": (["empty_barcode"] if not cam_barcode else []),
            }
            log(
                f"Camera import queued {job_id}: awaiting RQLP last-print confirm "
                f"barcode={cam_barcode or '(empty)'}",
                job_id=job_id,
                printer_id=printer_id,
            )

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

    if pod_forward_meta:
        result["pod_forward"] = pod_forward_meta

    if camera_import_meta:
        result["camera_import"] = camera_import_meta

    _store_result(result)
    return result


def get_all_printers() -> Dict[str, Dict[str, Any]]:
    printers = {}
    for printer_id, printer in PRINTERS.items():
        connection: ConnectionManager = printer["connection"]
        alive = connection.probe_alive()
        if not alive:
            if printer.get("last_status") == "connected":
                printer["last_status"] = "disconnected"
        printers[printer_id] = {
            "ip": printer["ip"],
            "port": printer["port"],
            "connection_status": "disconnected" if not alive else str(
                printer.get("last_status", "idle")
            ),
            "socket_connected": alive,
        }
    return printers


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
    try:
        register_printer(printer_id, cfg["ip"], cfg["port"])
    except (KeyError, TypeError, ValueError) as exc:
        log(f"Skipping invalid printer config for {printer_id}: {exc}", level="ERROR")
