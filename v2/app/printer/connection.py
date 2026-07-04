"""High-level printer connection with circuit breaker and retries."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict, Optional

from app.core.config import Settings
from app.network.monitor import NetworkMonitor
from app.printer.protocol import normalize_single_command, serialize_command
from app.printer.response_parser import classify_result, parse_response_bytes
from app.printer.transport import TcpTransport
from app.resilience.circuit_breaker import CircuitBreaker, retry_with_backoff
from app.utils.logger import log


class PrinterConnection:
    def __init__(
        self,
        printer_id: str,
        ip: str,
        port: int,
        settings: Settings,
        network: Optional[NetworkMonitor] = None,
    ):
        self.printer_id = printer_id
        self.ip = ip
        self.port = port
        self.settings = settings
        self.transport = TcpTransport(printer_id, ip, port, settings, network)
        self.circuit = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            recovery_seconds=settings.circuit_recovery_seconds,
        )
        self.lock = threading.Lock()
        self.last_status = "idle"
        self.last_ok = False
        self.last_error: Optional[str] = None
        self.last_seen: Optional[str] = None

    def update_target(self, ip: str, port: int) -> None:
        with self.lock:
            self.ip = ip
            self.port = port
            self.transport.update_target(ip, port)

    def close(self) -> None:
        with self.lock:
            self.transport.close()

    def send_command(self, command_dict: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if not self.circuit.allow():
                return self._result(
                    command_dict,
                    ok=False,
                    reason="Printer circuit breaker open — too many recent failures",
                    error_type="circuit_open",
                )

            command_dict = normalize_single_command(command_dict)
            payload = serialize_command(command_dict, self.settings)

            def _attempt() -> Dict[str, Any]:
                raw, error_type = self.transport.send_and_receive(payload)
                result = self._result(command_dict, request_bytes=len(payload))
                if error_type:
                    result["error_type"] = error_type
                    if error_type == "read_timeout":
                        result["reason"] = f"Printer read timeout after {self.settings.read_timeout}s"
                    elif error_type == "connect_error":
                        result["reason"] = f"Could not connect to printer at {self.ip}:{self.port}"
                    else:
                        result["reason"] = "Printer closed connection without response"
                    return classify_result(result, self.settings.require_response)

                if self.settings.fire_and_forget:
                    result["ok"] = True
                    result["reason"] = "Sent in fire-and-forget mode"
                    return result

                parsed = parse_response_bytes(raw)
                result.update(parsed)
                return classify_result(result, self.settings.require_response)

            try:
                result = retry_with_backoff(
                    _attempt,
                    attempts=self.settings.send_retries,
                    base_delay=0.5,
                    max_delay=4.0,
                )
            except Exception as exc:
                self.circuit.record_failure()
                self.last_status = "error"
                self.last_ok = False
                self.last_error = str(exc)
                raise

            self.last_seen = datetime.now().isoformat()
            self.last_ok = bool(result.get("ok"))
            self.last_status = "connected" if self.last_ok else "error"
            self.last_error = None if self.last_ok else str(result.get("reason"))

            if self.last_ok:
                self.circuit.record_success()
            else:
                self.circuit.record_failure()

            return result

    def _result(
        self,
        command_dict: Dict[str, Any],
        ok: bool = False,
        reason: Optional[str] = None,
        error_type: Optional[str] = None,
        request_bytes: int = 0,
    ) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(),
            "target_ip": self.ip,
            "target_port": self.port,
            "request_command": command_dict.get("command"),
            "request_payload": command_dict,
            "request_bytes": request_bytes,
            "ok": ok,
            "reason": reason,
            "error_type": error_type,
            "raw_response": None,
            "response": None,
            "response_type": None,
            "response_command": None,
            "response_status": None,
            "protocol_error_code": None,
            "protocol_error_description": None,
        }

    def status_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "port": self.port,
            "connection_status": self.last_status,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "last_seen": self.last_seen,
            "circuit_breaker": self.circuit.status(),
            "circuit_failures": self.circuit.failures,
        }
