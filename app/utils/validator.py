import re

def validate_request(data):
    if "printer_id" not in data:
        return False, "Missing printer_id"

    if "printer" not in data:
        return False, "Missing printer info"

    ip = data["printer"].get("ip")
    port = data["printer"].get("port")

    if not ip or not re.match(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$", ip):
        return False, "Invalid IP"

    if not str(port).isdigit():
        return False, "Invalid Port"

    # Check for either "command" (single) or "commands" (list)
    if "command" not in data and "commands" not in data:
        return False, "Missing command or commands"

    if "command" in data and "commands" in data:
        return False, "Cannot have both command and commands"

    command = data.get("command") or data.get("commands")
    if isinstance(command, list):
        if not all(isinstance(c, dict) for c in command):
            return False, "Commands must be a list of objects"
    elif not isinstance(command, dict):
        return False, "Command must be an object or list of objects"

    # Validate priority if provided
    priority = data.get("priority")
    if priority and priority.lower() not in ["high", "normal"]:
        return False, "Priority must be 'high' or 'normal'"

    return True, None