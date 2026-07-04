"""Request validation."""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import PrinterConfig
from app.printer.protocol import extract_single_command


def validate_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def validate_port(port: Any) -> bool:
    if port is None or not str(port).isdigit():
        return False
    value = int(port)
    return 1 <= value <= 65535


def validate_print_request(data: Any) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Invalid JSON payload"
    if "printer_id" not in data:
        return False, "Missing printer_id"
    if "printer" not in data or not isinstance(data["printer"], dict):
        return False, "Missing printer info"

    ip = data["printer"].get("ip")
    port = data["printer"].get("port")
    if not validate_ip(str(ip)):
        return False, "Invalid IP"
    if not validate_port(port):
        return False, "Invalid port (must be 1-65535)"

    try:
        extract_single_command(data)
    except ValueError as exc:
        return False, str(exc)

    priority = data.get("priority")
    if priority and str(priority).lower() not in {"high", "normal"}:
        return False, "Priority must be 'high' or 'normal'"
    return True, None


def validate_data_enqueue(data: Any, printer_cfg: Optional[PrinterConfig]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    if not isinstance(data, dict):
        return False, "Invalid JSON payload", {}

    printer_id = data.get("printer_id")
    if not printer_id:
        return False, "Missing printer_id", {}

    payload = data.get("data")
    if not isinstance(payload, dict) or not payload:
        return False, "Missing or empty 'data' object", {}

    if printer_cfg and printer_cfg.required_data_fields:
        missing = [field for field in printer_cfg.required_data_fields if not str(payload.get(field, "")).strip()]
        if missing:
            return False, f"Missing required data fields: {', '.join(missing)}", {}

    command = {"command": "DATA", "data": payload}
    if data.get("erp_ref"):
        command["erp_ref"] = data["erp_ref"]

    priority = 1 if str(data.get("priority", "normal")).lower() == "high" else 2
    return True, None, {
        "printer_id": str(printer_id),
        "command": command,
        "priority": priority,
        "erp_ref": data.get("erp_ref"),
    }
