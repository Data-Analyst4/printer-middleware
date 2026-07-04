import re
from typing import Any, Optional, Tuple


IPV4_PATTERN = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_ipv4(ip: Any) -> bool:
    if not isinstance(ip, str) or not IPV4_PATTERN.match(ip):
        return False
    try:
        return all(0 <= int(octet) <= 255 for octet in ip.split("."))
    except ValueError:
        return False


def validate_port(port: Any) -> bool:
    if port is None:
        return False
    if not str(port).isdigit():
        return False
    value = int(port)
    return 1 <= value <= 65535


def validate_ip_port(ip: Any, port: Any) -> Tuple[bool, Optional[str]]:
    if not validate_ipv4(ip):
        return False, "Invalid IP"
    if not validate_port(port):
        return False, "Invalid port (must be 1-65535)"
    return True, None


def validate_device_id(device_id: Any) -> Tuple[bool, Optional[str]]:
    if not isinstance(device_id, str) or not device_id.strip():
        return False, "Invalid device id"
    if not DEVICE_ID_PATTERN.match(device_id):
        return False, "Device id may only contain letters, numbers, underscore, and hyphen"
    return True, None
