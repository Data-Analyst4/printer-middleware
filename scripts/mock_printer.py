#!/usr/bin/env python3
"""
Virtual printer simulator for end-to-end middleware and ERP testing.

Simulates real printer behaviour:
  - STAR loads a template (required before DATA)
  - DATA is validated, stored, and "printed" at items_per_minute speed
  - Protocol responses match what the middleware parser expects (STAR;YES, DATA;YES,
    RSP;SYSN;001, RSMPOD;..., RSAL;..., NYES)
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


DEFAULT_CONFIG: Dict[str, Any] = {
    "template_name": "DEMO",
    "items_per_minute": 20,
    "required_data_fields": [],
    "max_buffer_size": 500,
    "ack_mode": "processed",
    "response_mode": "text",
}


@dataclass
class PrintRecord:
    record_id: str
    command: str
    payload: Dict[str, Any]
    status: str
    response: str
    received_at: str
    printed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "command": self.command,
            "payload": self.payload,
            "status": self.status,
            "response": self.response,
            "received_at": self.received_at,
            "printed_at": self.printed_at,
        }


@dataclass
class VirtualPrinter:
    template_name: str = "DEMO"
    items_per_minute: float = 20.0
    required_data_fields: List[str] = field(default_factory=list)
    max_buffer_size: int = 500
    ack_mode: str = "processed"
    response_mode: str = "text"
    failure_mode: Optional[str] = None
    response_delay: float = 0.0
    close_without_response: bool = False

    template_loaded: bool = False
    loaded_template_name: Optional[str] = None
    buffer: Deque[PrintRecord] = field(default_factory=deque)
    history: Deque[PrintRecord] = field(default_factory=lambda: deque(maxlen=1000))
    total_received: int = 0
    total_printed: int = 0
    total_rejected: int = 0
    last_command: Optional[str] = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _next_print_slot: float = field(default=0.0, repr=False)
    _history_path: Optional[Path] = None

    @property
    def print_interval(self) -> float:
        rate = max(self.items_per_minute, 0.1)
        return 60.0 / rate

    def load_runtime_state(self, data: Dict[str, Any]) -> None:
        self.template_loaded = bool(data.get("template_loaded", False))
        self.loaded_template_name = data.get("loaded_template_name")
        self.total_received = int(data.get("total_received", 0))
        self.total_printed = int(data.get("total_printed", 0))
        self.total_rejected = int(data.get("total_rejected", 0))
        self.last_command = data.get("last_command")

    def runtime_state(self) -> Dict[str, Any]:
        return {
            "template_loaded": self.template_loaded,
            "loaded_template_name": self.loaded_template_name,
            "total_received": self.total_received,
            "total_printed": self.total_printed,
            "total_rejected": self.total_rejected,
            "last_command": self.last_command,
            "buffer_size": len(self.buffer),
            "items_per_minute": self.items_per_minute,
            "updated_at": _utc_now(),
        }

    def set_history_file(self, path: Optional[str]) -> None:
        self._history_path = Path(path) if path else None
        if self._history_path:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)

    def _append_history_file(self, record: PrintRecord) -> None:
        if not self._history_path:
            return
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def _utc_now(self) -> str:
        return _utc_now()

    def build_success_response(self, command_name: str) -> bytes:
        if self.response_mode == "json":
            return json.dumps(
                {"command": command_name, "status": "YES", "value": "ACK"},
                separators=(",", ":"),
            ).encode("utf-8")
        return f"{command_name};YES".encode("utf-8")

    def build_failure_response(self, failure_mode: str) -> bytes:
        mapping = {
            "nysn": b"NYES",
            "sysn": b"RSP;SYSN;001",
            "alarm": b"RSAL;015;1",
            "missing_pod": b"RSMPOD;1;POD1",
            "invalid_json": b"RSP;SYSN;011",
            "buffer_full": b"DATA;FULL",
        }
        if failure_mode not in mapping:
            raise ValueError(f"Unsupported failure mode: {failure_mode}")
        return mapping[failure_mode]

    def _validate_star(self, command: Dict[str, Any]) -> Optional[bytes]:
        template = str(command.get("templatename", "")).strip()
        if not template:
            return b"RSP;SYSN;002"
        if template.upper() != self.template_name.upper():
            return b"RSP;SYSN;001"
        return None

    def _validate_data(self, command: Dict[str, Any]) -> Optional[bytes]:
        if not self.template_loaded:
            return b"RSP;SYSN;001"

        data = command.get("data")
        if not isinstance(data, dict) or not data:
            return b"RSP;SYSN;011"

        for field_name in self.required_data_fields:
            value = data.get(field_name)
            if value is None or str(value).strip() == "":
                return f"RSMPOD;1;{field_name}".encode("utf-8")

        if len(self.buffer) >= self.max_buffer_size:
            return self.build_failure_response("buffer_full")

        return None

    def _reserve_print_slot(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(self._next_print_slot, now)
            self._next_print_slot = slot + self.print_interval
        wait_seconds = slot - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def _store_print(self, command: Dict[str, Any], response_text: str) -> PrintRecord:
        record = PrintRecord(
            record_id=str(uuid.uuid4()),
            command="DATA",
            payload=dict(command.get("data") or {}),
            status="printed",
            response=response_text,
            received_at=self._utc_now(),
            printed_at=self._utc_now(),
        )
        self.history.append(record)
        self._append_history_file(record)
        self.total_printed += 1
        return record

    def handle_command(self, command: Dict[str, Any]) -> Tuple[bytes, str, Optional[PrintRecord]]:
        command_name = str(command.get("command", "")).upper()
        self.last_command = command_name
        self.total_received += 1

        if self.failure_mode:
            return self.build_failure_response(self.failure_mode), "failure", None

        if command_name == "STAR":
            error = self._validate_star(command)
            if error:
                self.total_rejected += 1
                return error, "failure", None
            self.template_loaded = True
            self.loaded_template_name = str(command.get("templatename", "")).strip()
            response = self.build_success_response("STAR")
            return response, "success", None

        if command_name == "DATA":
            error = self._validate_data(command)
            if error:
                self.total_rejected += 1
                return error, "failure", None

            if self.ack_mode == "processed":
                self._reserve_print_slot()

            response = self.build_success_response("DATA")
            response_text = response.decode("utf-8", errors="replace")
            record = self._store_print(command, response_text)
            self.buffer.append(record)
            return response, "success", record

        if command_name in {"STOP", "PAUSE", "RESUME", "STATUS"}:
            response = self.build_success_response(command_name)
            return response, "success", None

        if command_name == "RQLP":
            # RSFP: last printed count + colN from last DATA payload
            last = self.history[-1] if self.history else None
            col_data: Dict[str, Any] = {}
            if last and isinstance(last.payload, dict):
                for key, value in last.payload.items():
                    upper = str(key).upper()
                    if upper.startswith("POD") and upper[3:].isdigit():
                        col_data[f"col{upper[3:]}"] = value
            printed = max(1, self.total_printed) if last else 0
            total = printed
            payload = {
                "command": "RSFP",
                "value": f"{printed}/{total}",
                "data": col_data,
            }
            return (
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                "success",
                None,
            )

        return b"NYES", "failure", None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def load_config_file(path: Optional[str]) -> Dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if not path:
        return config

    config_path = Path(path)
    if not config_path.exists():
        return config

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return config

    if isinstance(loaded, dict):
        config.update(loaded)
    return config


def load_state_file(path: Optional[str], printer: VirtualPrinter) -> None:
    if not path:
        return

    state_path = Path(path)
    if not state_path.exists():
        return

    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return

    if isinstance(loaded, dict):
        printer.load_runtime_state(loaded)


def save_state_file(path: Optional[str], printer: VirtualPrinter) -> None:
    if not path:
        return

    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(printer.runtime_state(), indent=2), encoding="utf-8")


def client_worker(
    conn: socket.socket,
    addr: Tuple[str, int],
    printer: VirtualPrinter,
    state_file: Optional[str],
) -> None:
    with conn:
        print(f"Client connected: {addr[0]}:{addr[1]}")
        while True:
            try:
                data = conn.recv(4096)
            except ConnectionResetError:
                print(f"Client reset connection: {addr[0]}:{addr[1]}")
                return

            if not data:
                print(f"Client disconnected: {addr[0]}:{addr[1]}")
                return

            payload_text = data.decode("utf-8", errors="replace").replace("\x00", "").strip()
            print(f"Received: {payload_text}")

            try:
                command = json.loads(payload_text)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON from {addr[0]}:{addr[1]}: {exc}")
                conn.sendall(printer.build_failure_response("invalid_json"))
                printer.total_rejected += 1
                continue

            if printer.close_without_response:
                print("Configured to close without response")
                return

            response_payload, status, record = printer.handle_command(command)

            if printer.response_delay > 0:
                time.sleep(printer.response_delay)

            if response_payload is not None:
                conn.sendall(response_payload)
                response_text = response_payload.decode("utf-8", errors="replace")
                if record:
                    print(
                        f"Printed item {record.record_id}: "
                        f"{json.dumps(record.payload, ensure_ascii=False)} "
                        f"-> {response_text}"
                    )
                else:
                    print(f"Sent {status} response: {response_text}")

                save_state_file(state_file, printer)
                _log_printer_stats(printer)


def _log_printer_stats(printer: VirtualPrinter) -> None:
    print(
        "Printer stats:",
        json.dumps(
            {
                "template_loaded": printer.template_loaded,
                "loaded_template": printer.loaded_template_name,
                "items_per_minute": printer.items_per_minute,
                "print_interval_sec": round(printer.print_interval, 2),
                "buffer_size": len(printer.buffer),
                "total_received": printer.total_received,
                "total_printed": printer.total_printed,
                "total_rejected": printer.total_rejected,
            }
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Virtual printer TCP server with rate-limited DATA consumption",
    )
    parser.add_argument("--host", default="127.0.0.1", help="IP address to bind")
    parser.add_argument("--port", type=int, default=9100, help="TCP port to bind")
    parser.add_argument(
        "--config",
        default="config/mock_printer.json",
        help="JSON config file (template, rate, required fields)",
    )
    parser.add_argument(
        "--items-per-minute",
        type=float,
        help="Override config: DATA items consumed per minute (e.g. 10 or 20)",
    )
    parser.add_argument(
        "--template-name",
        help="Override config: template name accepted by STAR",
    )
    parser.add_argument(
        "--required-fields",
        help="Override config: comma-separated DATA fields (e.g. POD1,POD2)",
    )
    parser.add_argument(
        "--max-buffer",
        type=int,
        help="Override config: max queued DATA items before DATA;FULL",
    )
    parser.add_argument(
        "--ack-mode",
        choices=["processed", "received"],
        help="processed = wait print slot before DATA;YES, received = immediate ACK",
    )
    parser.add_argument(
        "--response-mode",
        choices=["text", "json"],
        help="Format used for successful responses",
    )
    parser.add_argument(
        "--failure-mode",
        choices=["nysn", "sysn", "alarm", "missing_pod"],
        help="Always return a failure response (testing error paths)",
    )
    parser.add_argument(
        "--response-delay",
        type=float,
        default=0.0,
        help="Extra seconds to wait before sending a response",
    )
    parser.add_argument(
        "--close-without-response",
        action="store_true",
        help="Accept command and close the socket without replying",
    )
    parser.add_argument(
        "--state-file",
        default="logs/mock_printer_state.json",
        help="Persist template/state between restarts",
    )
    parser.add_argument(
        "--history-file",
        default="logs/mock_printer_history.jsonl",
        help="Append each printed DATA record as JSON lines",
    )
    parser.add_argument(
        "--instant",
        action="store_true",
        help="Legacy mode: no rate limit, minimal validation (fast smoke tests)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config_file(args.config if Path(args.config).exists() else None)

    printer = VirtualPrinter(
        template_name=args.template_name or config.get("template_name", "DEMO"),
        items_per_minute=float(
            args.items_per_minute if args.items_per_minute is not None else config.get("items_per_minute", 20)
        ),
        required_data_fields=_parse_required_fields(args, config),
        max_buffer_size=int(args.max_buffer if args.max_buffer is not None else config.get("max_buffer_size", 500)),
        ack_mode=args.ack_mode or config.get("ack_mode", "processed"),
        response_mode=args.response_mode or config.get("response_mode", "text"),
        failure_mode=args.failure_mode,
        response_delay=args.response_delay,
        close_without_response=args.close_without_response,
    )

    if args.instant:
        printer.items_per_minute = 6000.0
        printer.required_data_fields = []
        printer.ack_mode = "received"

    printer.set_history_file(args.history_file)
    load_state_file(args.state_file, printer)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen()

    print(f"Virtual printer listening on {args.host}:{args.port}")
    print(
        "Behaviour:",
        json.dumps(
            {
                "template_name": printer.template_name,
                "items_per_minute": printer.items_per_minute,
                "print_interval_sec": round(printer.print_interval, 2),
                "required_data_fields": printer.required_data_fields,
                "max_buffer_size": printer.max_buffer_size,
                "ack_mode": printer.ack_mode,
                "response_mode": printer.response_mode,
                "failure_mode": printer.failure_mode,
                "history_file": args.history_file,
                "state_file": args.state_file,
            },
            indent=2,
        ),
    )

    try:
        while True:
            conn, addr = server.accept()
            worker = threading.Thread(
                target=client_worker,
                args=(conn, addr, printer, args.state_file),
                daemon=True,
            )
            worker.start()
    except KeyboardInterrupt:
        print("Shutting down virtual printer")
        save_state_file(args.state_file, printer)
        return 0
    finally:
        server.close()


def _parse_required_fields(args: argparse.Namespace, config: Dict[str, Any]) -> List[str]:
    if args.required_fields:
        return [part.strip() for part in args.required_fields.split(",") if part.strip()]
    raw = config.get("required_data_fields", [])
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
