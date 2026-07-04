import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.utils.logger import log
from app.utils.network import validate_device_id, validate_ip_port

PERSIST_POD_DEVICES = os.getenv("PERSIST_POD_DEVICES", "true").lower() == "true"
CONFIG_PATH = "config/pod_devices.json"

POD_DEVICES: Dict[str, Dict[str, Any]] = {}
DEVICES_LOCK = threading.Lock()


def _ensure_config_dir() -> None:
    config_dir = os.path.dirname(CONFIG_PATH)
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)


def load_pod_devices() -> Dict[str, Dict[str, Any]]:
    if not PERSIST_POD_DEVICES or not os.path.exists(CONFIG_PATH):
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            if not isinstance(data, dict):
                return {}
            return data
    except Exception as exc:
        log(f"Error loading pod devices config: {exc}", level="ERROR")
        return {}


def save_pod_devices() -> None:
    if not PERSIST_POD_DEVICES:
        return

    _ensure_config_dir()
    with DEVICES_LOCK:
        snapshot = {
            device_id: {
                "name": device.get("name", device_id),
                "ip": device["ip"],
                "port": device["port"],
                "enabled": bool(device.get("enabled", True)),
                "updated_at": device.get("updated_at"),
            }
            for device_id, device in POD_DEVICES.items()
        }

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(snapshot, file, indent=2)


def _normalize_device_record(device_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": str(data.get("name") or device_id),
        "ip": str(data["ip"]),
        "port": int(data["port"]),
        "enabled": bool(data.get("enabled", True)),
        "updated_at": data.get("updated_at") or datetime.now().isoformat(),
    }


def get_all_pod_devices() -> Dict[str, Any]:
    with DEVICES_LOCK:
        devices = {
            device_id: dict(record)
            for device_id, record in POD_DEVICES.items()
        }
    return {"success": True, "devices": devices}


def get_pod_device(device_id: str) -> Optional[Dict[str, Any]]:
    with DEVICES_LOCK:
        record = POD_DEVICES.get(device_id)
        return dict(record) if record else None


def upsert_pod_device(device_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    valid_id, id_error = validate_device_id(device_id)
    if not valid_id:
        return {"success": False, "error": id_error}

    if not isinstance(data, dict):
        return {"success": False, "error": "Invalid JSON payload"}

    ip = data.get("ip")
    port = data.get("port")
    valid_target, target_error = validate_ip_port(ip, port)
    if not valid_target:
        return {"success": False, "error": target_error}

    record = _normalize_device_record(
        device_id,
        {
            "name": data.get("name", device_id),
            "ip": ip,
            "port": port,
            "enabled": data.get("enabled", True),
            "updated_at": datetime.now().isoformat(),
        },
    )

    with DEVICES_LOCK:
        POD_DEVICES[device_id] = record

    save_pod_devices()
    log(f"Updated POD device {device_id}: {record['ip']}:{record['port']}")

    return {
        "success": True,
        "device_id": device_id,
        "device": record,
    }


def delete_pod_device(device_id: str) -> Dict[str, Any]:
    with DEVICES_LOCK:
        if device_id not in POD_DEVICES:
            return {"success": False, "error": "Device not found"}
        del POD_DEVICES[device_id]

    save_pod_devices()
    log(f"Deleted POD device {device_id}")
    return {"success": True, "device_id": device_id}


def resolve_pod_target(request_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    inline = request_data.get("pod_device")
    if isinstance(inline, dict):
        ip = inline.get("ip")
        port = inline.get("port")
        valid, _ = validate_ip_port(ip, port)
        if valid:
            return {"ip": str(ip), "port": int(port)}, request_data.get("pod_device_id"), "request"

    device_id = request_data.get("pod_device_id")
    if isinstance(device_id, str) and device_id:
        device = get_pod_device(device_id)
        if device and device.get("enabled", True):
            return {"ip": device["ip"], "port": device["port"]}, device_id, "registry"

    return None, None, None


def _bootstrap_pod_devices() -> None:
    loaded = load_pod_devices()
    with DEVICES_LOCK:
        POD_DEVICES.clear()
        for device_id, record in loaded.items():
            try:
                POD_DEVICES[device_id] = _normalize_device_record(device_id, record)
            except (KeyError, TypeError, ValueError) as exc:
                log(f"Skipping invalid pod device config for {device_id}: {exc}", level="ERROR")


_bootstrap_pod_devices()
