"""Low-level TCP transport with multi-recv read window and reconnect support."""

from __future__ import annotations

import socket
import time
from typing import Optional, Tuple

from app.core.config import Settings
from app.network.monitor import NetworkMonitor
from app.utils.logger import log


class TcpTransport:
    def __init__(
        self,
        printer_id: str,
        host: str,
        port: int,
        settings: Settings,
        network: Optional[NetworkMonitor] = None,
    ):
        self.printer_id = printer_id
        self.host = host
        self.port = port
        self.settings = settings
        self.network = network
        self._sock: Optional[socket.socket] = None

    def update_target(self, host: str, port: int) -> None:
        if self.host != host or self.port != port:
            self.close()
            log(f"Printer {self.printer_id} target updated: {self.host}:{self.port} -> {host}:{port}")
        self.host = host
        self.port = port

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _resolve_host(self) -> str:
        if self.network:
            return self.network.resolve(self.host)
        return self.host

    def connect(self) -> socket.socket:
        if self._sock is not None:
            return self._sock

        target = self._resolve_host()
        if self.network and not self.network.can_reach_printer(self.host, self.port):
            raise ConnectionError(f"Network unreachable for printer {self.printer_id} at {self.host}:{self.port}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.settings.connect_timeout)
        try:
            sock.connect((target, self.port))
        except socket.gaierror as exc:
            raise ConnectionError(f"DNS resolution failed for {self.host}: {exc}") from exc
        except OSError as exc:
            raise ConnectionError(f"TCP connect failed for {self.host}:{self.port}: {exc}") from exc

        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        log(f"TCP connected {self.printer_id} -> {target}:{self.port}")
        return sock

    def send(self, payload: bytes) -> None:
        sock = self.connect()
        sock.sendall(payload)

    def read_response(self) -> bytes:
        if self.settings.fire_and_forget:
            return b""

        sock = self.connect()
        sock.settimeout(self.settings.read_timeout)
        deadline = time.monotonic() + self.settings.max_read_seconds
        chunks = []

        while time.monotonic() < deadline:
            try:
                chunk = sock.recv(self.settings.recv_size)
            except socket.timeout:
                if chunks:
                    break
                raise TimeoutError(
                    f"Printer read timeout after {self.settings.read_timeout}s"
                )

            if not chunk:
                self.close()
                if chunks:
                    break
                raise ConnectionError("Printer closed connection without response")

            chunks.append(chunk)
            if len(b"".join(chunks)) >= self.settings.recv_size:
                break
            time.sleep(self.settings.idle_timeout)
            if not chunks:
                continue
            break

        return b"".join(chunks)

    def send_and_receive(self, payload: bytes) -> Tuple[bytes, Optional[str]]:
        try:
            self.send(payload)
            if self.settings.fire_and_forget:
                return b"", None
            data = self.read_response()
            return data, None
        except TimeoutError as exc:
            self.close()
            return b"", "read_timeout"
        except ConnectionError as exc:
            self.close()
            return b"", "connect_error" if "connect" in str(exc).lower() else "empty_response"
        except OSError as exc:
            self.close()
            return b"", "connect_error"
