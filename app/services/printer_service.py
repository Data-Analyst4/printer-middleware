"""Simple one-shot TCP sender for printer JSON commands.

This matches the direct test script behavior closely:
- open a socket
- send one JSON command
- wait for one response window
- close the socket
"""

import json
import os
import socket
import time
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.printer_protocol import serialize_command

CONNECT_TIMEOUT = float(os.getenv("PRINTER_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("PRINTER_READ_TIMEOUT", "5"))
IDLE_TIMEOUT = float(os.getenv("PRINTER_IDLE_TIMEOUT", "0.4"))
MAX_READ_SECONDS = float(os.getenv("PRINTER_MAX_READ_SECONDS", "8"))
RECV_SIZE = int(os.getenv("PRINTER_RECV_SIZE", "4096"))

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


def _normalize_text(text: str) -> str:
    return text.replace("\x02", "<STX>").replace("\x03", "<ETX>").replace("\x1d", "<GS>").strip()


def _parse_response_fields(normalized: str) -> Dict[str, Any]:
    clean = (
        normalized.replace("<STX>", "")
        .replace("<ETX>", "")
        .replace("\x02", "")
        .replace("\x03", "")
        .strip()
    )
    parts = [part.strip() for part in clean.split(";") if part.strip()]
    response_command = parts[0].upper() if parts else None
    response_status = parts[1].upper() if len(parts) > 1 else None
    protocol_error_code = None

    if response_command == "RSAL" and len(parts) > 1:
        protocol_error_code = parts[1]
    elif response_status == "SYSN" and len(parts) > 2:
        protocol_error_code = parts[2]
    elif response_command == "RSMPOD" and len(parts) > 1:
        protocol_error_code = parts[1]

    return {
        "response_command": response_command,
        "response_status": response_status,
        "protocol_error_code": protocol_error_code,
        "response_fields": parts[1:] if len(parts) > 1 else [],
    }


def _classify_result(result: Dict[str, Any]) -> Dict[str, Any]:
    command = (result.get("response_command") or "").upper()
    status = (result.get("response_status") or "").upper()
    protocol_error_code = result.get("protocol_error_code")
    fields = result.get("response_fields") or []

    if result.get("error_type") == "read_timeout":
        result["ok"] = False
        result["reason"] = result.get("reason") or "Printer read timeout"
        return result

    if result.get("error_type") == "empty_response":
        result["ok"] = False
        result["reason"] = result.get("reason") or "Printer closed connection without response"
        return result

    if command == "RSAL":
        result["ok"] = False
        head_index = fields[1] if len(fields) > 1 else None
        message = f"Printer alarm RSAL code {protocol_error_code}" if protocol_error_code else "Printer alarm RSAL"
        if head_index is not None:
            message += f" on head {head_index}"
        result["reason"] = message
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
            result["protocol_error_description"] = PROTOCOL_ERROR_CODES[protocol_error_code]
            result["reason"] = (
                f"Printer status {status} with error code {protocol_error_code}"
                f" ({PROTOCOL_ERROR_CODES[protocol_error_code]})"
            )
        elif protocol_error_code:
            result["reason"] = f"Printer status {status} with error code {protocol_error_code}"
        else:
            result["reason"] = f"Printer status {status}"
        return result

    result["ok"] = True
    result["reason"] = result.get("reason") or "Command acknowledged by printer"
    return result


def _read_response(sock: socket.socket) -> tuple[bytes, str]:
    sock.settimeout(READ_TIMEOUT)
    try:
        first = sock.recv(RECV_SIZE)
    except socket.timeout:
        return b"", "read_timeout"

    if not first:
        return b"", "empty_response"

    chunks = [first]
    started = time.monotonic()
    sock.settimeout(IDLE_TIMEOUT)

    while (time.monotonic() - started) < MAX_READ_SECONDS:
        try:
            chunk = sock.recv(RECV_SIZE)
        except socket.timeout:
            break

        if not chunk:
            break
        chunks.append(chunk)

    return b"".join(chunks), "ok"


def send_printer_command(ip: str, port: int, command_dict: Dict[str, Any]) -> Dict[str, Any]:
    payload = serialize_command(command_dict)
    result: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "target_ip": ip,
        "target_port": port,
        "request_command": command_dict.get("command"),
        "request_payload": command_dict,
        "request_bytes": len(payload),
        "ok": False,
        "reason": None,
        "error_type": None,
        "raw_response": None,
        "response": None,
        "response_type": None,
        "response_command": None,
        "response_status": None,
        "protocol_error_code": None,
        "protocol_error_description": None,
    }

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((ip, port))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.sendall(payload)

        response_bytes, state = _read_response(sock)
        if state == "read_timeout":
            result["error_type"] = "read_timeout"
            result["reason"] = f"Printer read timeout after {READ_TIMEOUT}s"
            return _classify_result(result)

        if state == "empty_response":
            result["error_type"] = "empty_response"
            result["reason"] = "Printer closed connection without response"
            return _classify_result(result)

        text = response_bytes.decode("utf-8", errors="replace")
        normalized = _normalize_text(text)
        result["raw_response"] = normalized

        try:
            parsed = json.loads(text)
            result["response"] = parsed
            result["response_type"] = "json"
        except Exception:
            parsed = None
            result["response"] = normalized
            result["response_type"] = "text"

        if parsed and isinstance(parsed, dict):
            response_command = parsed.get("command")
            response_status = parsed.get("status")
            protocol_error_code = parsed.get("error")
            result["response_command"] = str(response_command).strip().upper() if response_command is not None else None
            result["response_status"] = str(response_status).strip().upper() if response_status is not None else None
            result["protocol_error_code"] = str(protocol_error_code).strip() if protocol_error_code is not None else None
            if parsed.get("value") is not None:
                result["response_fields"] = [str(parsed.get("value"))]
        else:
            result.update(_parse_response_fields(normalized))

        return _classify_result(result)
