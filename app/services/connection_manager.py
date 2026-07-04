"""TCP JSON connection manager for printers.

The printer receives JSON command payloads and returns protocol responses either
as JSON or as raw protocol frames (for example STX/ETX delimited messages).
This module captures the raw response plus parsed metadata so job APIs can
report exact printer acknowledgements and error codes.
"""

import json
import os
import socket
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from app.services.printer_protocol import normalize_single_command, serialize_command
from app.utils.logger import log

CONNECT_TIMEOUT = float(os.getenv("PRINTER_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("PRINTER_READ_TIMEOUT", "5"))
# Simple middleware mode: do not wait for printer read/ack by default.
# Set PRINTER_FIRE_AND_FORGET=false if you need to wait for device response.
FIRE_AND_FORGET = os.getenv("PRINTER_FIRE_AND_FORGET", "false").lower() == "true"

# If enabled, a command without printer reply is treated as an unsuccessful
# attempt so retry/failure logic can surface the real root cause.
REQUIRE_PRINTER_RESPONSE = os.getenv("PRINTER_REQUIRE_RESPONSE", "true").lower() == "true"

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


def _normalize_raw_text(text: str) -> str:
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


def _extract_response_fields(parsed: Any, raw_text: str) -> Dict[str, Optional[str]]:
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
        parts = [p.strip() for p in clean.split(";") if p.strip()]
        if parts:
            command = parts[0].upper()
            response_fields = parts[1:] if len(parts) > 1 else []
        if len(parts) > 1:
            status = parts[1].upper()
        if command == "RSAL" and len(parts) > 1:
            # RSAL;<alarmCode>;<headIndex>
            protocol_error_code = parts[1]
        elif len(parts) > 2 and status == "SYSN":
            protocol_error_code = parts[2]
        elif command == "RSMPOD" and len(parts) > 1:
            # RSMPOD;<page>;...
            protocol_error_code = parts[1]

    return {
        "response_command": command,
        "response_status": status,
        "protocol_error_code": protocol_error_code,
        "response_fields": response_fields,
    }


def _classify_result(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    command = (result.get("response_command") or "").upper()
    status = (result.get("response_status") or "").upper()
    protocol_error_code = result.get("protocol_error_code")
    fields = result.get("response_fields") or []

    if result.get("error_type") in {"read_timeout", "empty_response"} and REQUIRE_PRINTER_RESPONSE:
        result["ok"] = False
        result["reason"] = result.get("reason") or "No response received from printer"
        return result

    if command == "RSAL":
        result["ok"] = False
        head_index = fields[1] if len(fields) > 1 else None
        if protocol_error_code:
            msg = f"Printer alarm RSAL code {protocol_error_code}"
        else:
            msg = "Printer alarm RSAL"
        if head_index is not None:
            msg += f" on head {head_index}"
        result["reason"] = msg
        return result

    if command == "RSMPOD":
        result["ok"] = False
        page = fields[0] if fields else protocol_error_code
        result["reason"] = (
            f"Printer reported missing POD data{f' at page {page}' if page else ''}"
        )
        return result

    if command == "NYES":
        result["ok"] = False
        result["reason"] = "Printer returned NYES (command rejected)"
        return result

    # RQLP reply: RSFP with value "X/Y" and optional data cols
    if command == "RSFP":
        result["ok"] = True
        result["reason"] = result.get("reason") or "RQLP last-print status received"
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


class ConnectionManager:
    def __init__(self, printer_id: str, ip: str, port: int):
        self.printer_id = printer_id
        self.ip = ip
        self.port = port
        self.connected = False  # reflects last successful call
        self.lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

    def _open_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((self.ip, self.port))
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connected = True
        return sock

    def _close_socket(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.connected = False

    def _ensure_socket(self) -> socket.socket:
        if self._sock is None:
            self._sock = self._open_socket()
            log(f"Opened persistent connection for {self.printer_id} -> {self.ip}:{self.port}")
        return self._sock

    def send_command(self, command_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Send one command and return detailed response diagnostics.

        Raises socket errors on network/transport failures; caller decides retry
        policy. Protocol-level failures (timeout, NYES, SYSN, etc.) are
        returned as structured unsuccessful results so callers can persist exact
        device feedback.
        """
        with self.lock:
            command_dict = normalize_single_command(command_dict)

            result: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "target_ip": self.ip,
                "target_port": self.port,
                "request_command": command_dict.get("command"),
                "request_payload": command_dict,
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

            try:
                sock = self._ensure_socket()
                payload = serialize_command(command_dict)
                sock.sendall(payload)
                result["request_bytes"] = len(payload)

                if FIRE_AND_FORGET:
                    result["ok"] = True
                    result["reason"] = "Sent in fire-and-forget mode"
                    return result

                sock.settimeout(READ_TIMEOUT)
                try:
                    data = sock.recv(4096)
                except socket.timeout:
                    result["error_type"] = "read_timeout"
                    result["reason"] = f"Printer read timeout after {READ_TIMEOUT}s"
                    log(f"Read timeout from printer {self.printer_id}")
                    return _classify_result(result)

                if not data:
                    # Peer closed connection. Mark disconnected so retry path can reconnect.
                    self._close_socket()
                    result["error_type"] = "empty_response"
                    result["reason"] = "Printer closed connection without response"
                    return _classify_result(result)

                text = data.decode("utf-8", errors="replace")
                normalized = _normalize_raw_text(text)
                result["raw_response"] = normalized

                try:
                    parsed = json.loads(text)
                    result["response"] = parsed
                    result["response_type"] = "json"
                except Exception:
                    result["response"] = normalized
                    result["response_type"] = "text"
                    parsed = None

                result.update(_extract_response_fields(parsed, normalized))
                return _classify_result(result)

            except Exception as e:
                self._close_socket()
                log(f"Send error for {self.printer_id}: {e}")
                raise

    def close(self):
        self._close_socket()
        log(f"Closed connection for {self.printer_id}")

    def update_target(self, ip: str, port: int):
        with self.lock:
            target_changed = (self.ip != ip) or (self.port != port)
            if target_changed:
                self._close_socket()
                log(
                    f"Printer target updated for {self.printer_id}: "
                    f"{self.ip}:{self.port} -> {ip}:{port}"
                )
            self.ip = ip
            self.port = port
