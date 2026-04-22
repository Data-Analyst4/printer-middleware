import json
import os
import threading
import time
import uuid
import ipaddress
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.connection_manager import ConnectionManager
from app.services.printer_protocol import extract_commands
from app.utils.logger import log
from app.utils.validator import validate_request

PERSIST_PRINTERS = os.getenv("PERSIST_PRINTERS", "true").lower() == "true"
CONFIG_PATH = "config/printers.json"
SEND_RETRIES = max(1, int(os.getenv("PRINTER_SEND_RETRIES", "1")))
LOG_PRINTER_PAYLOADS = os.getenv("LOG_PRINTER_PAYLOADS", "true").lower() == "true"

# printer_id -> {"ip": str, "port": int, "last_status": str, "connection": ConnectionManager}
PRINTERS: Dict[str, Dict[str, Any]] = {}

# Lightweight in-memory request history for compatibility with /job and /jobs.
REQUEST_RESULTS: Dict[str, Dict[str, Any]] = {}
RESULTS_LOCK = threading.Lock()
PRINTERS_LOCK = threading.Lock()


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
    with PRINTERS_LOCK:
        data = {printer_id: {"ip": p["ip"], "port": p["port"]} for printer_id, p in PRINTERS.items()}
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def register_printer(printer_id: str, ip: str, port: int) -> bool:
    with PRINTERS_LOCK:
        if printer_id in PRINTERS:
            existing = PRINTERS[printer_id]
            target_changed = (existing["ip"] != ip) or (existing["port"] != port)
            existing["ip"] = ip
            existing["port"] = port
            existing["connection"].update_target(ip, port)
            return target_changed

        PRINTERS[printer_id] = {
            "ip": ip,
            "port": port,
            "last_status": "idle",
            "connection": ConnectionManager(printer_id, ip, port),
        }
        return True


def _extract_printer_target(payload: Dict[str, Any], printer_id_override: Optional[str] = None):
    if not isinstance(payload, dict):
        return None, None, None, "Invalid JSON payload"

    printer_id = printer_id_override or payload.get("printer_id")
    if not isinstance(printer_id, str) or not printer_id.strip():
        return None, None, None, "Missing printer_id"

    printer_obj = payload.get("printer")
    if printer_obj is not None and not isinstance(printer_obj, dict):
        return None, None, None, "Invalid printer object"

    source = printer_obj if isinstance(printer_obj, dict) else payload
    ip = source.get("ip")
    port = source.get("port")

    if not isinstance(ip, str) or not ip.strip():
        return None, None, None, "Invalid IP"
    try:
        ipaddress.ip_address(ip.strip())
    except ValueError:
        return None, None, None, "Invalid IP"

    if port is None or not str(port).isdigit():
        return None, None, None, "Invalid Port"

    return printer_id.strip(), ip.strip(), int(port), None


def upsert_printer_config(payload: Dict[str, Any], printer_id_override: Optional[str] = None) -> Dict[str, Any]:
    printer_id, ip, port, error = _extract_printer_target(payload, printer_id_override)
    if error:
        return {"success": False, "error": error}

    with PRINTERS_LOCK:
        existed = printer_id in PRINTERS

    changed = register_printer(printer_id, ip, port)
    if changed:
        save_printers()

    return {
        "success": True,
        "printer_id": printer_id,
        "printer": {"ip": ip, "port": port},
        "updated": existed,
        "message": "Printer updated" if existed else "Printer created",
    }


def delete_printer_config(printer_id: str) -> Dict[str, Any]:
    if not isinstance(printer_id, str) or not printer_id.strip():
        return {"success": False, "error": "Missing printer_id"}

    normalized_id = printer_id.strip()
    with PRINTERS_LOCK:
        printer = PRINTERS.get(normalized_id)
        if not printer:
            return {"success": False, "error": "Printer not found"}

        try:
            printer["connection"].close()
        except Exception:
            pass
        del PRINTERS[normalized_id]

    save_printers()
    return {"success": True, "printer_id": normalized_id, "message": "Printer deleted"}


def _store_result(result: Dict[str, Any]):
    with RESULTS_LOCK:
        REQUEST_RESULTS[result["job_id"]] = result


def _build_metrics() -> Dict[str, int]:
    with RESULTS_LOCK:
        total = len(REQUEST_RESULTS)
        completed = sum(1 for value in REQUEST_RESULTS.values() if value.get("status") == "completed")
        failed = sum(1 for value in REQUEST_RESULTS.values() if value.get("status") == "failed")
    return {"total": total, "completed": completed, "failed": failed}


def _send_command(
    printer_id: str,
    command: Dict[str, Any],
    wait_for_response: bool = True,
) -> Dict[str, Any]:
    printer = PRINTERS[printer_id]
    connection: ConnectionManager = printer["connection"]

    for attempt in range(1, SEND_RETRIES + 1):
        try:
            response = connection.send_command(command, wait_for_response=wait_for_response)
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
    await_response = data.get("await_response", True)
    continue_on_error = data.get("continue_on_error", True)

    try:
        commands = extract_commands(data)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    printer_changed = register_printer(printer_id, ip, port)
    if printer_changed:
        save_printers()

    request_payload_for_log = None
    if LOG_PRINTER_PAYLOADS:
        request_payload_for_log = commands[0] if len(commands) == 1 else commands

    log(
        f"Direct send request {job_id}: printer={printer_id} target={ip}:{port} "
        f"commands={len(commands)} await_response={await_response}",
        job_id=job_id,
        printer_id=printer_id,
        extra_data={
            "event": "printer_request",
            "execution_mode": "sync",
            "target_ip": ip,
            "target_port": port,
            "commands_count": len(commands),
            "await_response": await_response,
            "continue_on_error": continue_on_error,
            "request_payload": request_payload_for_log,
        },
    )

    started = time.perf_counter()
    command_results = []
    first_error = None

    for index, command in enumerate(commands):
        command_result = _send_command(
            printer_id,
            command,
            wait_for_response=await_response,
        )
        command_record = {
            "index": index,
            "attempt": command_result.get("attempt"),
            "command": command,
            "ok": command_result.get("ok", False),
            "reason": command_result.get("reason"),
            "response_command": command_result.get("response_command"),
            "response_status": command_result.get("response_status"),
            "protocol_error_code": command_result.get("protocol_error_code"),
            "protocol_error_description": command_result.get("protocol_error_description"),
            "raw_response": command_result.get("raw_response"),
            "response": command_result.get("response"),
            "error_type": command_result.get("error_type"),
        }
        command_results.append(command_record)

        if not command_record["ok"] and first_error is None:
            first_error = command_record.get("reason") or "Unsuccessful printer response"
            if not continue_on_error:
                break

    duration_ms = int((time.perf_counter() - started) * 1000)
    requested_commands = len(commands)
    processed_commands = len(command_results)
    success = (
        processed_commands == requested_commands
        and all(item.get("ok", False) for item in command_results)
    )
    last_result = command_results[-1] if command_results else {}
    failure_reason = first_error
    if not failure_reason and processed_commands < requested_commands:
        failure_reason = "Stopped early due to command failure"
    if not failure_reason and not success:
        failure_reason = "One or more commands failed"

    result = {
        "success": success,
        "job_id": job_id,
        "status": "completed" if success else "failed",
        "execution_mode": "sync",
        "printer_id": printer_id,
        "printer": {"ip": ip, "port": port},
        "await_response": await_response,
        "continue_on_error": continue_on_error,
        "requested_commands": requested_commands,
        "processed_commands": processed_commands,
        "duration_ms": duration_ms,
        "commands": commands,
        "responses": command_results,
        # Backward compatibility for single-command clients.
        "command": commands[0] if len(commands) == 1 else None,
        "response": command_results[0] if len(commands) == 1 and command_results else None,
        "printer_ok": success,
        "printer_reason": None if success else failure_reason,
        "printer_response_command": last_result.get("response_command"),
        "printer_response_status": last_result.get("response_status"),
        "printer_protocol_error_code": last_result.get("protocol_error_code"),
        "printer_protocol_error_description": last_result.get("protocol_error_description"),
        "printer_raw_response": last_result.get("raw_response"),
        "printer_response_payload": last_result.get("response"),
        "error": None if success else failure_reason,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    _store_result(result)

    response_payload_for_log = None
    if LOG_PRINTER_PAYLOADS:
        if len(commands) == 1:
            response_payload_for_log = command_results[0] if command_results else None
        else:
            response_payload_for_log = [
                {
                    "index": item.get("index"),
                    "ok": item.get("ok"),
                    "reason": item.get("reason"),
                    "response_command": item.get("response_command"),
                    "response_status": item.get("response_status"),
                    "protocol_error_code": item.get("protocol_error_code"),
                    "raw_response": item.get("raw_response"),
                    "response": item.get("response"),
                }
                for item in command_results
            ]

    log(
        f"Direct send response {job_id}: printer={printer_id} ok={success} "
        f"processed={processed_commands}/{requested_commands} duration_ms={duration_ms}",
        level="INFO" if success else "ERROR",
        job_id=job_id,
        printer_id=printer_id,
        extra_data={
            "event": "printer_response",
            "execution_mode": "sync",
            "target_ip": ip,
            "target_port": port,
            "commands_count": requested_commands,
            "processed_commands": processed_commands,
            "duration_ms": duration_ms,
            "await_response": await_response,
            "continue_on_error": continue_on_error,
            "request_payload": request_payload_for_log,
            "response_payload": response_payload_for_log,
            "printer_ok": success,
            "printer_reason": None if success else failure_reason,
            "response_command": last_result.get("response_command"),
            "response_status": last_result.get("response_status"),
            "protocol_error_code": last_result.get("protocol_error_code"),
            "protocol_error_description": last_result.get("protocol_error_description"),
        },
    )
    return result


def get_all_printers() -> Dict[str, Dict[str, Any]]:
    with PRINTERS_LOCK:
        snapshot = dict(PRINTERS)
    return {
        printer_id: {
            "ip": printer["ip"],
            "port": printer["port"],
            "connection_status": str(printer.get("last_status", "idle")),
            "socket_connected": bool(printer["connection"].connected),
        }
        for printer_id, printer in snapshot.items()
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
