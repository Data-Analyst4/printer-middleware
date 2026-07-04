"""Per-printer rate-limited queue consumers."""

from __future__ import annotations

import json
import threading
import time
from typing import Dict, Optional

from app.core.config import Settings
from app.jobs.store import JobStore
from app.printer.registry import PrinterRegistry
from app.utils.logger import log


class PrinterConsumer:
    def __init__(self, printer_id: str, registry: PrinterRegistry, store: JobStore, settings: Settings):
        self.printer_id = printer_id
        self.registry = registry
        self.store = store
        self.settings = settings
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._next_slot = 0.0

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name=f"consumer-{self.printer_id}",
        )
        self._thread.start()
        log(f"Started queue consumer for {self.printer_id}")

    def stop(self) -> None:
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _wait_for_slot(self, items_per_minute: float) -> None:
        interval = 60.0 / max(items_per_minute, 0.1)
        now = time.monotonic()
        slot = max(self._next_slot, now)
        self._next_slot = slot + interval
        wait_seconds = slot - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def _loop(self) -> None:
        while self.running:
            try:
                item = self.store.fetch_next(self.printer_id)
                if not item:
                    time.sleep(self.settings.worker_poll_seconds)
                    continue

                cfg = self.registry.get_config(self.printer_id)
                rate = cfg.items_per_minute if cfg else self.settings.default_items_per_minute
                self._wait_for_slot(rate)

                command = json.loads(item["command"]) if isinstance(item["command"], str) else item["command"]
                connection = self.registry.get_connection(self.printer_id)

                try:
                    response = connection.send_command(command)
                    ok = bool(response.get("ok"))
                except Exception as exc:
                    response = {"ok": False, "reason": str(exc), "error_type": "transport_exception"}
                    ok = False

                retry_count = int(item.get("retry_count") or 0)
                max_retries = int(item.get("max_retries") or 5)

                if ok:
                    self.store.complete_item(item["item_id"], response, True)
                    log(f"Queued item {item['item_id']} printed on {self.printer_id}")
                elif retry_count + 1 < max_retries:
                    self.store.requeue_failed(item["item_id"], str(response.get("reason")), retry_count + 1)
                    log(f"Queued item {item['item_id']} failed, requeued ({retry_count + 1}/{max_retries})")
                else:
                    self.store.complete_item(item["item_id"], response, False)
                    log(f"Queued item {item['item_id']} failed permanently on {self.printer_id}", level="ERROR")

            except Exception as exc:
                log(f"Consumer error for {self.printer_id}: {exc}", level="ERROR")
                time.sleep(2)


class ConsumerManager:
    def __init__(self, registry: PrinterRegistry, store: JobStore, settings: Settings):
        self.registry = registry
        self.store = store
        self.settings = settings
        self._consumers: Dict[str, PrinterConsumer] = {}
        self._lock = threading.Lock()

    def start_all(self) -> None:
        if not self.settings.queue_enabled:
            return
        with self._lock:
            for printer_id in self.registry.all_status().keys():
                self._ensure_consumer(printer_id)

    def ensure_consumer(self, printer_id: str) -> None:
        with self._lock:
            self._ensure_consumer(printer_id)

    def _ensure_consumer(self, printer_id: str) -> None:
        if printer_id not in self._consumers:
            consumer = PrinterConsumer(printer_id, self.registry, self.store, self.settings)
            self._consumers[printer_id] = consumer
            consumer.start()

    def stop_all(self) -> None:
        with self._lock:
            for consumer in self._consumers.values():
                consumer.stop()
            self._consumers.clear()
