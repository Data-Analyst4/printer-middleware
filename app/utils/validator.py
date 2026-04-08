import re

from app.services.printer_protocol import extract_single_command


def validate_request(data):
    if not isinstance(data, dict):
        return False, "Invalid JSON payload"

    if "printer_id" not in data:
        return False, "Missing printer_id"

    if "printer" not in data or not isinstance(data["printer"], dict):
        return False, "Missing printer info"

    ip = data["printer"].get("ip") if data.get("printer") else None
    port = data["printer"].get("port") if data.get("printer") else None

    if not ip or not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", ip):
        return False, "Invalid IP"

    if port is None or not str(port).isdigit():
        return False, "Invalid Port"

    try:
        extract_single_command(data)
    except ValueError as exc:
        return False, str(exc)

    # Validate priority if provided
    priority = data.get("priority")
    if priority and priority.lower() not in ["high", "normal"]:
        return False, "Priority must be 'high' or 'normal'"

    return True, None
