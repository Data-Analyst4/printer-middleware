"""Unified printer response parsing and classification."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

FAILED_STATUS = {"NYES", "SYSN", "FAILED", "ERROR", "FULL", "NOK"}

PROTOCOL_ERROR_CODES = {
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


def normalize_raw_text(text: str) -> str:
    return (
        text.replace("\x02", "<STX>")
        .replace("\x03", "<ETX>")
        .replace("\x1d", "<GS>")
        .strip()
    )


def _strip_frame_tokens(text: str) -> str:
    return (
        text.replace("<STX>", "")
        .replace("<ETX>", "")
        .replace("\x02", "")
        .replace("\x03", "")
        .strip()
    )


def extract_response_fields(parsed: Any, raw_text: str) -> Dict[str, Optional[Any]]:
    command = None
    status = None
    protocol_error_code = None
    response_fields = None

    if isinstance(parsed, dict):
        if parsed.get("command") is not None:
            command = str(parsed.get("command")).strip().upper()
        if parsed.get("status") is not None:
            status = str(parsed.get("status")).strip().upper()
        if parsed.get("error") is not None:
            protocol_error_code = str(parsed.get("error")).strip()
        if parsed.get("value") is not None:
            response_fields = [str(parsed.get("value"))]
    else:
        clean = _strip_frame_tokens(raw_text)
        parts = [part.strip() for part in clean.split(";") if part.strip()]
        if parts:
            command = parts[0].upper()
            response_fields = parts[1:] if len(parts) > 1 else []
        if len(parts) > 1:
            status = parts[1].upper()
        if command == "RSAL" and len(parts) > 1:
            protocol_error_code = parts[1]
        elif len(parts) > 2 and status == "SYSN":
            protocol_error_code = parts[2]
        elif command == "RSMPOD" and len(parts) > 1:
            protocol_error_code = parts[1]

    return {
        "response_command": command,
        "response_status": status,
        "protocol_error_code": protocol_error_code,
        "response_fields": response_fields,
    }


def parse_response_bytes(data: bytes) -> Dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    normalized = normalize_raw_text(text)
    try:
        parsed = json.loads(text)
        response_type = "json"
    except json.JSONDecodeError:
        parsed = None
        response_type = "text"

    fields = extract_response_fields(parsed, normalized)
    return {
        "raw_response": normalized,
        "response": parsed if parsed is not None else normalized,
        "response_type": response_type,
        **fields,
    }


def classify_result(result: Dict[str, Any], require_response: bool = True) -> Dict[str, Any]:
    command = (result.get("response_command") or "").upper()
    status = (result.get("response_status") or "").upper()
    protocol_error_code = result.get("protocol_error_code")
    fields = result.get("response_fields") or []

    if result.get("error_type") in {"read_timeout", "empty_response", "connect_error", "dns_error"}:
        if require_response:
            result["ok"] = False
            result["reason"] = result.get("reason") or "No response received from printer"
        else:
            result["ok"] = True
            result["reason"] = result.get("reason") or "Sent without waiting for response"
        return result

    if command == "RSAL":
        result["ok"] = False
        head_index = fields[1] if len(fields) > 1 else None
        msg = f"Printer alarm RSAL code {protocol_error_code}" if protocol_error_code else "Printer alarm RSAL"
        if head_index is not None:
            msg += f" on head {head_index}"
        result["reason"] = msg
        return result

    if command == "RSMPOD":
        result["ok"] = False
        page = fields[0] if fields else protocol_error_code
        result["reason"] = f"Printer reported missing POD data{f' at page {page}' if page else ''}"
        return result

    if command == "NYES":
        result["ok"] = False
        result["reason"] = "Printer returned NYES (command rejected)"
        return result

    if status in FAILED_STATUS:
        result["ok"] = False
        if protocol_error_code and protocol_error_code in PROTOCOL_ERROR_CODES:
            result["reason"] = (
                f"Printer status {status} with error code {protocol_error_code}"
                f" ({PROTOCOL_ERROR_CODES[protocol_error_code]})"
            )
            result["protocol_error_description"] = PROTOCOL_ERROR_CODES[protocol_error_code]
        elif protocol_error_code:
            result["reason"] = f"Printer status {status} with error code {protocol_error_code}"
        else:
            result["reason"] = f"Printer status {status}"
        return result

    result["ok"] = True
    if not result.get("reason"):
        result["reason"] = "Command acknowledged by printer"
    return result
