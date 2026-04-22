import json
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.printer_protocol import extract_commands
from app.utils.validator import validate_request

MAX_SIMULATED_PAGES = 1000

SCENARIOS: Dict[str, Dict[str, str]] = {
    "auto": {"description": "State-based realistic simulation"},
    "rsal_011": {"description": "STAR returns RSAL alarm 011"},
    "sysn_007": {"description": "STAR returns SYSN with code 007"},
    "nyes": {"description": "All commands rejected with NYES"},
    "timeout": {"description": "All commands return read timeout"},
    "transport_closed": {"description": "All commands fail with closed connection"},
    "mixed": {"description": "Every third command fails with RSAL 011"},
}

TEST_PRINTERS: Dict[str, Dict[str, Any]] = {}
TEST_RESULTS: Dict[str, Dict[str, Any]] = {}
TEST_LOCK = threading.Lock()

PROTOCOL_ERROR_DESCRIPTIONS = {
    "000": "Unknown",
    "001": "Open template failed",
    "002": "Start page or end page is invalid",
    "003": "No printhead selected",
    "004": "Speed limit",
    "005": "Printhead disconnected",
    "006": "Unknown printhead",
    "007": "No cartridges",
    "008": "Invalid cartridges",
    "009": "Out of ink",
    "010": "Cartridges are locked",
    "011": "Invalid version",
    "012": "Incorrect printhead",
    "013": "Start print processing error",
    "014": "Invalid loop value",
    "015": "Ink low",
    "016": "No response",
    "017": "Incorrect start key",
    "018": "Conflict cartridge",
}


def _default_state() -> Dict[str, Any]:
    return {
        "scenario": "auto",
        "loaded_pages": 0,
        "is_printing": False,
        "last_data": {},
        "command_counter": 0,
    }


def _get_or_create_state(printer_id: str) -> Dict[str, Any]:
    with TEST_LOCK:
        state = TEST_PRINTERS.get(printer_id)
        if state is None:
            state = _default_state()
            TEST_PRINTERS[printer_id] = state
        return state


def _snapshot_state(printer_id: str) -> Optional[Dict[str, Any]]:
    with TEST_LOCK:
        state = TEST_PRINTERS.get(printer_id)
        if state is None:
            return None
        return dict(state)


def _store_result(result: Dict[str, Any]) -> None:
    with TEST_LOCK:
        TEST_RESULTS[result["job_id"]] = result


def _as_raw(response_obj: Dict[str, Any]) -> str:
    return json.dumps(response_obj, ensure_ascii=False, separators=(",", ":"))


def _success_response(
    command: Dict[str, Any],
    response_obj: Dict[str, Any],
    reason: str = "Command acknowledged by printer",
) -> Dict[str, Any]:
    return {
        "attempt": 1,
        "command": command,
        "ok": True,
        "reason": reason,
        "response_command": str(response_obj.get("command", "")).upper() or None,
        "response_status": str(response_obj.get("status", "")).upper() or None,
        "protocol_error_code": None,
        "protocol_error_description": None,
        "raw_response": _as_raw(response_obj),
        "response": response_obj,
        "error_type": None,
    }


def _failure_response(
    command: Dict[str, Any],
    reason: str,
    response_command: Optional[str] = None,
    response_status: Optional[str] = None,
    protocol_error_code: Optional[str] = None,
    error_type: Optional[str] = None,
    response_obj: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "attempt": 1,
        "command": command,
        "ok": False,
        "reason": reason,
        "response_command": response_command,
        "response_status": response_status,
        "protocol_error_code": protocol_error_code,
        "protocol_error_description": PROTOCOL_ERROR_DESCRIPTIONS.get(protocol_error_code)
        if protocol_error_code
        else None,
        "raw_response": _as_raw(response_obj) if response_obj is not None else None,
        "response": response_obj,
        "error_type": error_type,
    }


def _build_rsfp_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    data = {}
    last_data = state.get("last_data") or {}
    for idx in range(1, 21):
        key = f"POD{idx}"
        data[f"col{idx}"] = str(last_data.get(key, ""))
    return {
        "command": "RSFP",
        "value": f"{state.get('loaded_pages', 0)}/{MAX_SIMULATED_PAGES}",
        "data": data,
    }


def _apply_scenario(
    scenario: str,
    state: Dict[str, Any],
    command: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    cmd_name = str(command.get("command", "")).upper()
    if scenario == "nyes":
        response_obj = {"command": "NYES", "status": "NOK"}
        return _failure_response(
            command=command,
            reason="Printer returned NYES (command rejected)",
            response_command="NYES",
            response_status="NOK",
            response_obj=response_obj,
        )

    if scenario == "timeout":
        return _failure_response(
            command=command,
            reason="Printer read timeout after 5.0s",
            error_type="read_timeout",
        )

    if scenario == "transport_closed":
        return _failure_response(
            command=command,
            reason="[WinError 10054] An existing connection was forcibly closed by the remote host",
            error_type="transport_exception",
        )

    if scenario == "rsal_011" and cmd_name == "STAR":
        response_obj = {"command": "RSAL", "error": "011", "index": "0"}
        return _failure_response(
            command=command,
            reason="Printer alarm RSAL code 011",
            response_command="RSAL",
            protocol_error_code="011",
            response_obj=response_obj,
        )

    if scenario == "sysn_007" and cmd_name == "STAR":
        response_obj = {"command": "STAR", "status": "SYSN", "error": "007"}
        return _failure_response(
            command=command,
            reason="Printer status SYSN with error code 007 (No cartridges)",
            response_command="STAR",
            response_status="SYSN",
            protocol_error_code="007",
            response_obj=response_obj,
        )

    if scenario == "mixed":
        if state["command_counter"] % 3 == 0:
            response_obj = {"command": "RSAL", "error": "011", "index": "0"}
            return _failure_response(
                command=command,
                reason="Printer alarm RSAL code 011",
                response_command="RSAL",
                protocol_error_code="011",
                response_obj=response_obj,
            )

    return None


def _simulate_command(
    printer_id: str,
    command: Dict[str, Any],
    await_response: bool,
) -> Dict[str, Any]:
    state = _get_or_create_state(printer_id)
    cmd_name = str(command.get("command", "")).upper()

    with TEST_LOCK:
        state["command_counter"] += 1
        scenario = state.get("scenario", "auto")

    scenario_result = _apply_scenario(scenario, state, command)
    if scenario_result is not None:
        return scenario_result

    if not await_response:
        return {
            "attempt": 1,
            "command": command,
            "ok": True,
            "reason": "Sent without waiting for printer response",
            "response_command": None,
            "response_status": None,
            "protocol_error_code": None,
            "protocol_error_description": None,
            "raw_response": None,
            "response": None,
            "error_type": None,
        }

    if cmd_name == "DATA":
        payload = command.get("data")
        if payload is not None and not isinstance(payload, dict):
            return _failure_response(
                command=command,
                reason="Invalid DATA payload: 'data' must be a JSON object",
                response_command="NYES",
                response_status="NOK",
                response_obj={"command": "NYES", "status": "NOK"},
            )
        with TEST_LOCK:
            state["loaded_pages"] = min(MAX_SIMULATED_PAGES, state["loaded_pages"] + 1)
            if isinstance(payload, dict):
                state["last_data"] = dict(payload)
        return _success_response(command, {"command": "DATA", "status": "OK"})

    if cmd_name == "RQLP":
        state = _get_or_create_state(printer_id)
        return _success_response(command, _build_rsfp_payload(state))

    if cmd_name == "STOP":
        with TEST_LOCK:
            if not state["is_printing"]:
                response_obj = {"command": "STOP", "status": "SYSN"}
                return _failure_response(
                    command=command,
                    reason="Printer status SYSN",
                    response_command="STOP",
                    response_status="SYSN",
                    response_obj=response_obj,
                )
            state["is_printing"] = False
        return _success_response(command, {"command": "STOP", "status": "OK"})

    if cmd_name == "STAR":
        with TEST_LOCK:
            if state["loaded_pages"] <= 0:
                response_obj = {"command": "STAR", "status": "SYSN", "error": "007"}
                return _failure_response(
                    command=command,
                    reason="Printer status SYSN with error code 007 (No cartridges)",
                    response_command="STAR",
                    response_status="SYSN",
                    protocol_error_code="007",
                    response_obj=response_obj,
                )
            state["is_printing"] = True
        return _success_response(command, {"command": "STAR", "status": "OK"})

    return _failure_response(
        command=command,
        reason=f"Unsupported command '{cmd_name}' in simulator",
        response_command="NYES",
        response_status="NOK",
        response_obj={"command": "NYES", "status": "NOK"},
    )


def handle_test_print_request(data: Dict[str, Any]) -> Dict[str, Any]:
    valid, error = validate_request(data)
    if not valid:
        return {
            "success": False,
            "error": error,
            "error_type": "validation_error",
            "details": {"scope": "request"},
        }

    printer_id = data["printer_id"]
    ip = data["printer"]["ip"]
    port = data["printer"]["port"]
    job_id = str(uuid.uuid4())
    await_response = data.get("await_response", True)
    continue_on_error = data.get("continue_on_error", True)

    try:
        commands = extract_commands(data)
    except ValueError as exc:
        return {
            "success": False,
            "error": str(exc),
            "error_type": "validation_error",
            "details": {"scope": "commands"},
        }

    started = time.perf_counter()
    command_results = []
    first_error = None

    for index, command in enumerate(commands):
        command_result = _simulate_command(printer_id, command, await_response)
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

    scenario = _get_or_create_state(printer_id).get("scenario", "auto")
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
        "simulated": True,
        "simulator_scenario": scenario,
    }
    _store_result(result)
    return result


def get_test_job_result(job_id: str) -> Dict[str, Any]:
    with TEST_LOCK:
        result = TEST_RESULTS.get(job_id)
    if not result:
        return {"success": False, "error": "Job not found"}
    return {"success": True, **result}


def get_all_test_jobs() -> Dict[str, Any]:
    with TEST_LOCK:
        jobs = list(TEST_RESULTS.values())
    return {"success": True, "jobs": jobs}


def list_test_scenarios() -> Dict[str, Any]:
    return {"success": True, "scenarios": SCENARIOS}


def set_test_scenario(printer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"success": False, "error": "Invalid JSON payload"}
    scenario = payload.get("scenario")
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        return {"success": False, "error": f"Invalid scenario. Use one of: {', '.join(SCENARIOS.keys())}"}
    state = _get_or_create_state(printer_id)
    with TEST_LOCK:
        state["scenario"] = scenario
    return {"success": True, "printer_id": printer_id, "scenario": scenario}


def reset_test_printer(printer_id: str) -> Dict[str, Any]:
    with TEST_LOCK:
        TEST_PRINTERS[printer_id] = _default_state()
    return {"success": True, "printer_id": printer_id, "message": "Simulator state reset"}


def get_test_printer_state(printer_id: str) -> Dict[str, Any]:
    snapshot = _snapshot_state(printer_id)
    if snapshot is None:
        return {"success": False, "error": "Printer state not found"}
    return {"success": True, "printer_id": printer_id, "state": snapshot}
