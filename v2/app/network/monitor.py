"""Network reachability and DNS helpers for factory LAN / ISP scenarios."""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from app.core.config import Settings
from app.utils.logger import log


@dataclass
class NetworkStatus:
    internet_ok: bool = True
    last_check_at: Optional[str] = None
    last_error: Optional[str] = None
    dns_cache: Dict[str, Tuple[str, float]] = field(default_factory=dict)


class NetworkMonitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.status = NetworkStatus()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="network-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.check_internet()
            self._stop.wait(self.settings.network_check_interval)

    def check_internet(self) -> bool:
        probes = [("1.1.1.1", 53), ("8.8.8.8", 53)]
        ok = False
        last_error = None
        for host, port in probes:
            try:
                sock = socket.create_connection((host, port), timeout=3)
                sock.close()
                ok = True
                break
            except OSError as exc:
                last_error = str(exc)

        with self._lock:
            self.status.internet_ok = ok
            self.status.last_error = None if ok else last_error
            self.status.last_check_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if not ok:
            log(f"Internet probe failed: {last_error}", level="WARNING")
        return ok

    def resolve(self, host: str) -> str:
        if host.replace(".", "").isdigit():
            return host

        now = time.monotonic()
        with self._lock:
            cached = self.status.dns_cache.get(host)
            if cached and now - cached[1] < self.settings.dns_cache_seconds:
                return cached[0]

        try:
            resolved = socket.gethostbyname(host)
        except socket.gaierror:
            resolved = host

        with self._lock:
            self.status.dns_cache[host] = (resolved, now)
        return resolved

    def can_reach_printer(self, host: str, port: int) -> bool:
        target = self.resolve(host)
        try:
            sock = socket.create_connection((target, port), timeout=min(3.0, self.settings.connect_timeout))
            sock.close()
            return True
        except OSError:
            return False

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "internet_ok": self.status.internet_ok,
                "last_check_at": self.status.last_check_at,
                "last_error": self.status.last_error,
            }
