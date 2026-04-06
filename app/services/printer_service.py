"""Utility for one-off TCP printer calls used by tests/examples."""

import json
import socket


def send_printer_command(ip, port, command_dict):
    payload = json.dumps(command_dict).encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5.0)
        sock.connect((ip, port))
        sock.sendall(payload)

        try:
            resp = sock.recv(4096)
        except socket.timeout:
            print("Printer read timeout")
            return None

        if not resp:
            return None

        text = resp.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = text
        print(f"Printer response: {parsed}")
        return parsed
