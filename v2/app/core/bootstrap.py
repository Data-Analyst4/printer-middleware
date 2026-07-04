"""Application bootstrap and shared runtime context."""

from __future__ import annotations

import atexit
import threading
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from app.core.config import Settings
from app.jobs.service import PrintService
from app.jobs.store import JobStore
from app.network.monitor import NetworkMonitor
from app.printer.registry import PrinterRegistry
from app.utils.logger import log
from app.workers.consumer import ConsumerManager


@dataclass
class AppContext:
    settings: Settings
    network: NetworkMonitor
    registry: PrinterRegistry
    store: JobStore
    print_service: PrintService
    consumers: ConsumerManager


_context: Optional[AppContext] = None
_lock = threading.Lock()


def get_context() -> AppContext:
    if _context is None:
        raise RuntimeError("Application not initialized")
    return _context


def init_app(env_file: Optional[str] = None) -> AppContext:
    global _context
    with _lock:
        if _context is not None:
            return _context

        load_dotenv(env_file)
        settings = Settings.from_env()
        network = NetworkMonitor(settings)
        registry = PrinterRegistry(settings, network)
        store = JobStore(settings)
        print_service = PrintService(settings, registry, store)
        consumers = ConsumerManager(registry, store, settings)

        registry.load()
        network.start()
        consumers.start_all()
        store.purge_old()

        _context = AppContext(
            settings=settings,
            network=network,
            registry=registry,
            store=store,
            print_service=print_service,
            consumers=consumers,
        )

        atexit.register(shutdown_app)
        log("Printer Middleware v2 initialized")
        return _context


def shutdown_app() -> None:
    global _context
    with _lock:
        if _context is None:
            return
        _context.consumers.stop_all()
        _context.network.stop()
        _context = None
