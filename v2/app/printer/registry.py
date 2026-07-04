"""Printer registry with allowlist and atomic config persistence."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from app.core.config import PrinterConfig, Settings, load_printers_config, save_printers_config
from app.network.monitor import NetworkMonitor
from app.printer.connection import PrinterConnection
from app.utils.logger import log


class PrinterRegistry:
    def __init__(self, settings: Settings, network: NetworkMonitor):
        self.settings = settings
        self.network = network
        self._printers: Dict[str, PrinterConfig] = {}
        self._connections: Dict[str, PrinterConnection] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        configs = load_printers_config(self.settings.printers_config, self.settings)
        with self._lock:
            self._printers = configs
            for printer_id, cfg in configs.items():
                self._ensure_connection(printer_id, cfg)

    def register(self, printer_id: str, ip: str, port: int, **extra: Any) -> PrinterConfig:
        with self._lock:
            existing = self._printers.get(printer_id)
            cfg = PrinterConfig(
                printer_id=printer_id,
                ip=ip,
                port=int(port),
                items_per_minute=extra.get(
                    "items_per_minute",
                    existing.items_per_minute if existing else self.settings.default_items_per_minute,
                ),
                required_data_fields=extra.get(
                    "required_data_fields",
                    existing.required_data_fields if existing else [],
                ),
                max_queue_size=extra.get(
                    "max_queue_size",
                    existing.max_queue_size if existing else self.settings.max_queue_size,
                ),
                template_name=extra.get("template_name", existing.template_name if existing else None),
                enabled=extra.get("enabled", True if existing is None else existing.enabled),
            )
            self._printers[printer_id] = cfg
            self._ensure_connection(printer_id, cfg)
            if self.settings.persist_printers:
                save_printers_config(self.settings.printers_config, self._printers)
            return cfg

    def get_config(self, printer_id: str) -> Optional[PrinterConfig]:
        with self._lock:
            return self._printers.get(printer_id)

    def get_connection(self, printer_id: str) -> PrinterConnection:
        with self._lock:
            if printer_id not in self._connections:
                raise KeyError(f"Printer not registered: {printer_id}")
            return self._connections[printer_id]

    def is_allowed(self, printer_id: str, ip: str, port: int) -> bool:
        if not self.settings.printer_allowlist_only:
            return True
        cfg = self.get_config(printer_id)
        if cfg is None:
            return False
        return cfg.ip == ip and cfg.port == int(port)

    def all_status(self, queue_depths: Optional[Dict[str, int]] = None) -> Dict[str, Dict[str, Any]]:
        queue_depths = queue_depths or {}
        with self._lock:
            result = {}
            for printer_id, cfg in self._printers.items():
                conn = self._connections.get(printer_id)
                status = conn.status_dict() if conn else {}
                result[printer_id] = {
                    **cfg.to_dict(),
                    **status,
                    "queue_size": queue_depths.get(printer_id, 0),
                    "enabled": cfg.enabled,
                }
            return result

    def _ensure_connection(self, printer_id: str, cfg: PrinterConfig) -> None:
        conn = self._connections.get(printer_id)
        if conn is None:
            self._connections[printer_id] = PrinterConnection(
                printer_id, cfg.ip, cfg.port, self.settings, self.network
            )
            log(f"Registered printer {printer_id} at {cfg.ip}:{cfg.port}")
        else:
            conn.update_target(cfg.ip, cfg.port)
