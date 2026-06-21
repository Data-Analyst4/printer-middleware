#!/usr/bin/env python3
"""
Mock printer server for end-to-end middleware testing.

This simulator listens on a TCP socket, accepts the same JSON command payloads
the middleware sends to real printers, and returns configurable responses that
match the middleware's parser expectations.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple


DEFAULT_STATE: Dict[str, Any] = {
    "template_loaded": False,
    "last_command": None,
}


def build_success_response(command: Dict[str, Any], response_mode: str) -> bytes:
    command_name = str(command.get("command", "")).upper()

    if response_mode == "json":
        return json.dumps(
            {
                "command": command_name,
                "status": "YES",
                "value": "ACK",
            },
            separators=(",", ":"),
        ).encode("utf-8")

    return f"{command_name};YES".encode("utf-8")


def build_failure_response(failure_mode: str) -> bytes:
    if failure_mode == "nysn":
        return b"NYES"
    if failure_mode == "sysn":
        return b"RSP;SYSN;001"
    if failure_mode == "alarm":
        return b"RSAL;015;1"
    if failure_mode == "missing_pod":
        return b"RSMPOD;1;POD1"
    raise ValueError(f"Unsupported failure mode: {failure_mode}")


def handle_command(
    command: Dict[str, Any],
    state: Dict[str, Any],
    response_mode: str,
    failure_mode: str | None,
) -> Tuple[bytes | None, str]:
    command_name = str(command.get("command", "")).upper()
    state["last_command"] = command_name

    if failure_mode:
        return build_failure_response(failure_mode), "failure"

    if command_name == "STAR":
        state["template_loaded"] = True
    elif command_name == "DATA" and not state["template_loaded"]:
        return b"RSP;SYSN;001", "failure"

    return build_success_response(command, response_mode), "success"


def client_worker(
    conn: socket.socket,
    addr: Tuple[str, int],
    state: Dict[str, Any],
    response_mode: str,
    failure_mode: str | None,
    response_delay: float,
    close_without_response: bool,
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
                conn.sendall(b"RSP;SYSN;011")
                continue

            if close_without_response:
                print("Configured to close without response")
                return

            response_payload, status = handle_command(
                command=command,
                state=state,
                response_mode=response_mode,
                failure_mode=failure_mode,
            )

            if response_delay > 0:
                time.sleep(response_delay)

            if response_payload is not None:
                conn.sendall(response_payload)
                print(f"Sent {status} response: {response_payload.decode('utf-8', errors='replace')}")


def load_state_file(path: str | None) -> Dict[str, Any]:
    if not path:
        return dict(DEFAULT_STATE)

    state_path = Path(path)
    if not state_path.exists():
        return dict(DEFAULT_STATE)

    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_STATE)

    if not isinstance(loaded, dict):
        return dict(DEFAULT_STATE)

    result = dict(DEFAULT_STATE)
    result.update(loaded)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mock printer TCP server")
    parser.add_argument("--host", default="127.0.0.1", help="IP address to bind")
    parser.add_argument("--port", type=int, default=9100, help="TCP port to bind")
    parser.add_argument(
        "--response-mode",
        choices=["text", "json"],
        default="text",
        help="Format used for successful responses",
    )
    parser.add_argument(
        "--failure-mode",
        choices=["nysn", "sysn", "alarm", "missing_pod"],
        help="Always return a failure response",
    )
    parser.add_argument(
        "--response-delay",
        type=float,
        default=0.0,
        help="Seconds to wait before sending a response",
    )
    parser.add_argument(
        "--close-without-response",
        action="store_true",
        help="Accept command and close the socket without replying",
    )
    parser.add_argument(
        "--state-file",
        help="Optional JSON file to pre-seed simulator state",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    state = load_state_file(args.state_file)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen()

    print(f"Mock printer listening on {args.host}:{args.port}")
    print(
        "Mode:",
        json.dumps(
            {
                "response_mode": args.response_mode,
                "failure_mode": args.failure_mode,
                "response_delay": args.response_delay,
                "close_without_response": args.close_without_response,
            }
        ),
    )

    try:
        while True:
            conn, addr = server.accept()
            worker = threading.Thread(
                target=client_worker,
                args=(
                    conn,
                    addr,
                    state,
                    args.response_mode,
                    args.failure_mode,
                    args.response_delay,
                    args.close_without_response,
                ),
                daemon=True,
            )
            worker.start()
    except KeyboardInterrupt:
        print("Shutting down mock printer")
        return 0
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
