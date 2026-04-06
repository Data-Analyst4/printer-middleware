"""TCP JSON connection manager for printers.

The printers speak raw TCP and expect JSON payloads; we send the bytes and
return the response (parsed as JSON when possible, otherwise text). A per-call
socket is used to avoid stale connections.
"""

import json
import os
import socket
import threading
from typing import Any, Dict, Optional

from app.utils.logger import log

CONNECT_TIMEOUT = float(os.getenv("PRINTER_CONNECT_TIMEOUT", "5"))
READ_TIMEOUT = float(os.getenv("PRINTER_READ_TIMEOUT", "2"))
FIRE_AND_FORGET = os.getenv("PRINTER_FIRE_AND_FORGET", "false").lower() == "true"


class ConnectionManager:
    def __init__(self, printer_id: str, ip: str, port: int):
        self.printer_id = printer_id
        self.ip = ip
        self.port = port
        self.connected = False  # reflects last successful call
        self.lock = threading.Lock()

    def _open_socket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((self.ip, self.port))
        self.connected = True
        return sock

    def send_command(self, command_dict: Dict[str, Any]) -> Optional[Any]:
        """Send one command and return printer response (JSON or text).

        Raises socket errors on failure; caller decides retry policy.
        """
        with self.lock:
            try:
                with self._open_socket() as sock:
                    payload = json.dumps(command_dict).encode("utf-8")
                    sock.sendall(payload)

                    if FIRE_AND_FORGET:
                        return None

                    sock.settimeout(READ_TIMEOUT)
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        log(f"Read timeout from printer {self.printer_id}")
                        return None

                    if not data:
                        return None

                    text = data.decode("utf-8", errors="replace")
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
            except Exception as e:
                self.connected = False
                log(f"Send error for {self.printer_id}: {e}")
                raise

    def close(self):
        # No persistent socket to close in the current design
        self.connected = False

    def update_target(self, ip: str, port: int):
        with self.lock:
            self.ip = ip
            self.port = port
            self.connected = False
