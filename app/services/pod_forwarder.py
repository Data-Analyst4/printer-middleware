import os
import socket
import threading
from typing import Any, Dict, Optional

from app.utils.logger import log

CONNECT_TIMEOUT = float(os.getenv("POD_FORWARD_CONNECT_TIMEOUT", "5"))


def _pod_sort_key(key: str) -> int:
    upper = key.upper()
    if upper.startswith("POD"):
        suffix = upper[3:]
        if suffix.isdigit():
            return int(suffix)
    return 10**9


def has_pod_fields(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return any(str(key).upper().startswith("POD") for key in data)


def should_forward_pod(command: Dict[str, Any]) -> bool:
    if str(command.get("command", "")).upper() != "DATA":
        return False
    return has_pod_fields(command.get("data"))


def build_pod_string(data: Dict[str, Any]) -> str:
    pod_keys = [key for key in data if str(key).upper().startswith("POD")]
    if not pod_keys:
        return ""

    sorted_keys = sorted(pod_keys, key=_pod_sort_key)
    return "".join(str(data[key]) for key in sorted_keys)


def send_pod_string(ip: str, port: int, payload: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "reason": None,
        "target_ip": ip,
        "target_port": port,
        "bytes_sent": 0,
    }

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect((ip, int(port)))
            encoded = payload.encode("utf-8")
            sock.sendall(encoded)
            result["ok"] = True
            result["bytes_sent"] = len(encoded)
            result["reason"] = "Payload sent"
    except Exception as exc:
        result["reason"] = str(exc)

    return result


def forward_pod_async(
    job_id: str,
    ip: str,
    port: int,
    pod_string: str,
    *,
    device_id: Optional[str] = None,
    printer_id: Optional[str] = None,
) -> None:
    def _run() -> None:
        result = send_pod_string(ip, port, pod_string)
        level = "INFO" if result["ok"] else "ERROR"
        log(
            (
                f"POD forward {'succeeded' if result['ok'] else 'failed'} "
                f"target={ip}:{port} bytes={result.get('bytes_sent', 0)}"
            ),
            level=level,
            job_id=job_id,
            printer_id=printer_id,
            extra_data={
                "pod_device_id": device_id,
                "pod_forward": result,
                "pod_payload_length": len(pod_string),
            },
        )

    threading.Thread(target=_run, daemon=True, name=f"pod-forward-{job_id[:8]}").start()
