#!/usr/bin/env python3
"""
Direct printer socket tester for JSON command payloads.

This script bypasses the middleware queue/API flow and talks to the printer
socket directly so you can inspect exact raw responses.

Examples:
  python scripts/test_commands.py --ip 192.168.29.110 --port 2030

  python scripts/test_commands.py --ip 192.168.29.110 --port 2030 ^
    --payload-file payload.json --read-timeout 8

  python scripts/test_commands.py --ip 192.168.29.110 --port 2030 ^
    --payload '{"commands":[{"command":"STAR","templatename":"DEMO","startpage":"1","endpage":"1","loop":"true"}]}'
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.printer_protocol import extract_commands, serialize_command


DEFAULT_PAYLOAD: Dict[str, Any] = {
    "commands": [
        {
            "command": "STAR",
            "templatename": "DEMO",
            "startpage": "1",
            "endpage": "1",
            "loop": "true",
        }
    ]
}

FAILED_STATUS = {"NYES", "SYSN", "FAILED", "ERROR", "FULL", "NOK"}


def normalize_text(text: str) -> str:
    return text.replace("\x02", "<STX>").replace("\x03", "<ETX>").replace("\x1d", "<GS>").strip()


def parse_protocol_fields(normalized: str) -> Dict[str, Any]:
    clean = (
        normalized.replace("<STX>", "")
        .replace("<ETX>", "")
        .replace("\x02", "")
        .replace("\x03", "")
        .strip()
    )
    parts = [p.strip() for p in clean.split(";") if p.strip()]
    command = parts[0].upper() if parts else None
    status = parts[1].upper() if len(parts) > 1 else None
    error_code = None

    if command == "RSAL" and len(parts) > 1:
        error_code = parts[1]
    elif status == "SYSN" and len(parts) > 2:
        error_code = parts[2]
    elif command == "RSMPOD" and len(parts) > 1:
        error_code = parts[1]

    return {
        "response_command": command,
        "response_status": status,
        "protocol_error_code": error_code,
        "response_fields": parts[1:] if len(parts) > 1 else [],
    }


def classify_response(response_command: str | None, response_status: str | None) -> Tuple[bool, str]:
    cmd = (response_command or "").upper()
    status = (response_status or "").upper()

    if cmd in {"NYES", "RSAL", "RSMPOD"}:
        return False, f"Printer reported failure command {cmd}"
    if status in FAILED_STATUS:
        return False, f"Printer reported failure status {status}"
    if not cmd and not status:
        return False, "Unable to parse printer response fields"
    return True, "Command acknowledged"


def read_response(
    sock: socket.socket,
    first_timeout: float,
    idle_timeout: float,
    recv_size: int,
    max_read_seconds: float,
) -> Tuple[bytes, str]:
    sock.settimeout(first_timeout)
    try:
        first = sock.recv(recv_size)
    except socket.timeout:
        return b"", "read_timeout"

    if not first:
        return b"", "empty_response"

    chunks = [first]
    start = time.monotonic()
    sock.settimeout(idle_timeout)

    while (time.monotonic() - start) < max_read_seconds:
        try:
            chunk = sock.recv(recv_size)
        except socket.timeout:
            break

        if not chunk:
            break
        chunks.append(chunk)

    return b"".join(chunks), "ok"


def parse_payload(raw_payload: Any) -> List[Dict[str, Any]]:
    if isinstance(raw_payload, list):
        return extract_commands({"commands": raw_payload})

    if not isinstance(raw_payload, dict):
        raise ValueError("Payload must be a JSON object or array of command objects.")

    return extract_commands(raw_payload)


def load_payload(args: argparse.Namespace) -> Tuple[List[Dict[str, Any]], Any]:
    if args.payload_file:
        raw = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    elif args.payload:
        raw = json.loads(args.payload)
    else:
        raw = DEFAULT_PAYLOAD

    return parse_payload(raw), raw


def run_test(args: argparse.Namespace) -> Dict[str, Any]:
    commands, source_payload = load_payload(args)
    results: List[Dict[str, Any]] = []

    print(f"Connecting to printer {args.ip}:{args.port}")
    print(f"Commands to send: {len(commands)}")

    shared_sock: socket.socket | None = None

    try:
        if not args.per_command_connection:
            shared_sock = socket.create_connection((args.ip, args.port), timeout=args.connect_timeout)
            shared_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("Connection mode: persistent (single socket)")
        else:
            print("Connection mode: per-command socket")

        for index, command in enumerate(commands):
            sock = shared_sock
            created_here = False

            if sock is None:
                sock = socket.create_connection((args.ip, args.port), timeout=args.connect_timeout)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                created_here = True

            send_started = time.monotonic()
            request_bytes = serialize_command(command)
            sock.sendall(request_bytes)

            response_bytes, state = read_response(
                sock=sock,
                first_timeout=args.read_timeout,
                idle_timeout=args.idle_timeout,
                recv_size=args.recv_size,
                max_read_seconds=args.max_read_seconds,
            )
            duration_ms = round((time.monotonic() - send_started) * 1000, 2)

            item: Dict[str, Any] = {
                "index": index,
                "command": command,
                "request_bytes": len(request_bytes),
                "duration_ms": duration_ms,
                "ok": False,
                "reason": None,
                "response_command": None,
                "response_status": None,
                "protocol_error_code": None,
                "raw_response": None,
                "response_json": None,
            }

            if state == "read_timeout":
                item["reason"] = f"Read timeout after {args.read_timeout}s"
            elif state == "empty_response":
                item["reason"] = "Printer closed connection with empty response"
            else:
                text = response_bytes.decode("utf-8", errors="replace")
                normalized = normalize_text(text)
                item["raw_response"] = normalized
                fields = parse_protocol_fields(normalized)
                item.update(fields)
                try:
                    item["response_json"] = json.loads(text)
                except Exception:
                    item["response_json"] = None

                ok, reason = classify_response(item.get("response_command"), item.get("response_status"))
                item["ok"] = ok
                item["reason"] = reason

            results.append(item)

            print(
                f"[{index}] ok={item['ok']} reason={item['reason']} "
                f"cmd={item.get('response_command')} status={item.get('response_status')}"
            )

            if created_here:
                sock.close()

            if args.delay_between > 0 and index < len(commands) - 1:
                time.sleep(args.delay_between)

    finally:
        if shared_sock is not None:
            shared_sock.close()

    summary = {
        "target": {"ip": args.ip, "port": args.port},
        "commands_sent": len(commands),
        "successful": sum(1 for r in results if r.get("ok")),
        "failed": sum(1 for r in results if not r.get("ok")),
        "payload_source": source_payload,
        "results": results,
    }

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct printer JSON command socket tester")
    parser.add_argument("--ip", required=True, help="Printer IP")
    parser.add_argument("--port", type=int, required=True, help="Printer TCP port")
    parser.add_argument("--payload-file", help="Path to JSON file containing commands payload")
    parser.add_argument("--payload", help="Inline JSON payload string")
    parser.add_argument("--connect-timeout", type=float, default=5.0, help="Socket connect timeout in seconds")
    parser.add_argument("--read-timeout", type=float, default=8.0, help="Initial response read timeout in seconds")
    parser.add_argument("--idle-timeout", type=float, default=0.4, help="Idle timeout between response chunks")
    parser.add_argument("--max-read-seconds", type=float, default=12.0, help="Maximum total response read window")
    parser.add_argument("--recv-size", type=int, default=4096, help="recv() buffer size")
    parser.add_argument("--delay-between", type=float, default=0.3, help="Delay between commands in seconds")
    parser.add_argument("--per-command-connection", action="store_true", help="Open a fresh socket for every command")
    parser.add_argument("--output-file", help="Write result JSON to file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = run_test(args)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    out = json.dumps(result, ensure_ascii=False, indent=2)
    print("\n=== Final Result ===")
    print(out)

    if args.output_file:
        Path(args.output_file).write_text(out, encoding="utf-8")
        print(f"\nSaved result to: {args.output_file}")

    return 0 if result["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
