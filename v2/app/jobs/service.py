"""Print orchestration service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.core.config import Settings
from app.jobs.store import JobStore
from app.printer.protocol import extract_single_command
from app.printer.registry import PrinterRegistry
from app.utils.logger import log
from app.utils.validator import validate_data_enqueue, validate_print_request


class PrintService:
    def __init__(self, settings: Settings, registry: PrinterRegistry, store: JobStore):
        self.settings = settings
        self.registry = registry
        self.store = store

    def handle_sync_print(self, data: Dict[str, Any]) -> Dict[str, Any]:
        valid, error = validate_print_request(data)
        if not valid:
            return {"success": False, "error": error}

        printer_id = str(data["printer_id"])
        ip = str(data["printer"]["ip"])
        port = int(data["printer"]["port"])

        if not self.registry.is_allowed(printer_id, ip, port):
            return {"success": False, "error": "Printer target not in allowlist"}

        self.registry.register(printer_id, ip, port)
        command = extract_single_command(data)
        job_id = str(uuid.uuid4())

        log(f"Sync print {job_id}: printer={printer_id} target={ip}:{port} command={command.get('command')}")

        try:
            connection = self.registry.get_connection(printer_id)
            command_result = connection.send_command(command)
        except Exception as exc:
            command_result = {
                "ok": False,
                "reason": str(exc),
                "error_type": "transport_exception",
            }

        success = bool(command_result.get("ok"))
        result = {
            "success": success,
            "job_id": job_id,
            "status": "completed" if success else "failed",
            "execution_mode": "sync",
            "printer_id": printer_id,
            "printer": {"ip": ip, "port": port},
            "command": command,
            "response": command_result,
            "printer_ok": command_result.get("ok"),
            "printer_reason": command_result.get("reason"),
            "printer_response_command": command_result.get("response_command"),
            "printer_response_status": command_result.get("response_status"),
            "printer_protocol_error_code": command_result.get("protocol_error_code"),
            "printer_protocol_error_description": command_result.get("protocol_error_description"),
            "printer_raw_response": command_result.get("raw_response"),
            "printer_response_payload": command_result.get("response"),
            "error": None if success else command_result.get("reason"),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self.store.save_sync_result(job_id, printer_id, result["status"], result)
        return result

    def enqueue_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        printer_id = str(data.get("printer_id", ""))
        printer_cfg = self.registry.get_config(printer_id)

        if data.get("printer") and isinstance(data["printer"], dict):
            ip = data["printer"].get("ip")
            port = data["printer"].get("port")
            if ip and port:
                self.registry.register(printer_id, str(ip), int(port))
                printer_cfg = self.registry.get_config(printer_id)

        valid, error, normalized = validate_data_enqueue(data, printer_cfg)
        if not valid:
            return {"success": False, "status": "rejected", "error": error}

        printer_id = normalized["printer_id"]
        printer_cfg = self.registry.get_config(printer_id)
        max_queue = printer_cfg.max_queue_size if printer_cfg else self.settings.max_queue_size
        depth = self.store.count_queued(printer_id)
        if depth >= max_queue:
            return {
                "success": False,
                "status": "rejected",
                "error": f"Printer queue full ({depth}/{max_queue})",
            }

        item_id = self.store.enqueue_item(
            printer_id=printer_id,
            command=normalized["command"],
            priority=normalized["priority"],
            erp_ref=normalized.get("erp_ref"),
        )

        interval = 60.0 / max((printer_cfg.items_per_minute if printer_cfg else self.settings.default_items_per_minute), 0.1)
        eta = datetime.now() + timedelta(seconds=depth * interval)

        return {
            "success": True,
            "item_id": item_id,
            "status": "queued",
            "printer_id": printer_id,
            "queue_position": depth + 1,
            "estimated_print_at": eta.isoformat(),
            "execution_mode": "async",
        }

    def get_item(self, item_id: str) -> Dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            return {"success": False, "error": "Item not found"}
        return {"success": True, **item}

    def get_job(self, job_id: str) -> Dict[str, Any]:
        result = self.store.get_sync_result(job_id)
        if not result:
            return {"success": False, "error": "Job not found"}
        return result

    def list_jobs(self) -> Dict[str, Any]:
        sync_jobs = self.store.list_sync_results(limit=100)
        queued_items = self.store.list_items(limit=100)
        return {"success": True, "sync_jobs": sync_jobs, "queued_items": queued_items}

    def metrics(self) -> Dict[str, Any]:
        return {"success": True, **self.store.metrics()}
