"""Central configuration for v2."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 5002
    cors_origins: str = "*"
    db_path: str = str(ROOT_DIR / "data" / "jobs.db")
    printers_config: str = str(ROOT_DIR / "config" / "printers.json")
    persist_printers: bool = True
    printer_allowlist_only: bool = False
    api_key: Optional[str] = None

    connect_timeout: float = 5.0
    read_timeout: float = 5.0
    idle_timeout: float = 0.4
    max_read_seconds: float = 8.0
    recv_size: int = 4096
    send_retries: int = 3
    fire_and_forget: bool = False
    require_response: bool = True
    payload_suffix: str = ""

    queue_enabled: bool = True
    default_items_per_minute: float = 20.0
    max_queue_size: int = 2000
    worker_poll_seconds: float = 0.5

    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: float = 30.0

    network_check_interval: float = 60.0
    dns_cache_seconds: float = 300.0

    job_history_limit: int = 5000
    result_ttl_hours: int = 168

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.getenv("HOST", "0.0.0.0"),
            port=_env_int("PORT", 5002),
            cors_origins=os.getenv("CORS_ORIGINS", "*"),
            db_path=os.getenv("DB_PATH", str(ROOT_DIR / "data" / "jobs.db")),
            printers_config=os.getenv("PRINTERS_CONFIG", str(ROOT_DIR / "config" / "printers.json")),
            persist_printers=_env_bool("PERSIST_PRINTERS", True),
            printer_allowlist_only=_env_bool("PRINTER_ALLOWLIST_ONLY", False),
            api_key=os.getenv("API_KEY") or None,
            connect_timeout=_env_float("PRINTER_CONNECT_TIMEOUT", 5.0),
            read_timeout=_env_float("PRINTER_READ_TIMEOUT", 5.0),
            idle_timeout=_env_float("PRINTER_IDLE_TIMEOUT", 0.4),
            max_read_seconds=_env_float("PRINTER_MAX_READ_SECONDS", 8.0),
            recv_size=_env_int("PRINTER_RECV_SIZE", 4096),
            send_retries=max(1, _env_int("PRINTER_SEND_RETRIES", 3)),
            fire_and_forget=_env_bool("PRINTER_FIRE_AND_FORGET", False),
            require_response=_env_bool("PRINTER_REQUIRE_RESPONSE", True),
            payload_suffix=os.getenv("PRINTER_PAYLOAD_SUFFIX", ""),
            queue_enabled=_env_bool("QUEUE_ENABLED", True),
            default_items_per_minute=_env_float("DEFAULT_ITEMS_PER_MINUTE", 20.0),
            max_queue_size=_env_int("MAX_QUEUE_SIZE", 2000),
            worker_poll_seconds=_env_float("WORKER_POLL_SECONDS", 0.5),
            circuit_failure_threshold=_env_int("CIRCUIT_FAILURE_THRESHOLD", 5),
            circuit_recovery_seconds=_env_float("CIRCUIT_RECOVERY_SECONDS", 30.0),
            network_check_interval=_env_float("NETWORK_CHECK_INTERVAL", 60.0),
            dns_cache_seconds=_env_float("DNS_CACHE_SECONDS", 300.0),
            job_history_limit=_env_int("JOB_HISTORY_LIMIT", 5000),
            result_ttl_hours=_env_int("RESULT_TTL_HOURS", 168),
        )


@dataclass
class PrinterConfig:
    printer_id: str
    ip: str
    port: int
    items_per_minute: float = 20.0
    required_data_fields: List[str] = field(default_factory=list)
    max_queue_size: int = 500
    template_name: Optional[str] = None
    enabled: bool = True

    @classmethod
    def from_dict(cls, printer_id: str, data: Dict[str, Any], defaults: Settings) -> "PrinterConfig":
        fields = data.get("required_data_fields") or data.get("required_fields") or []
        if isinstance(fields, str):
            fields = [part.strip() for part in fields.split(",") if part.strip()]
        return cls(
            printer_id=printer_id,
            ip=str(data["ip"]),
            port=int(data["port"]),
            items_per_minute=float(data.get("items_per_minute", defaults.default_items_per_minute)),
            required_data_fields=list(fields),
            max_queue_size=int(data.get("max_queue_size", defaults.max_queue_size)),
            template_name=data.get("template_name"),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "port": self.port,
            "items_per_minute": self.items_per_minute,
            "required_data_fields": self.required_data_fields,
            "max_queue_size": self.max_queue_size,
            "template_name": self.template_name,
            "enabled": self.enabled,
        }


def load_printers_config(path: str, settings: Settings) -> Dict[str, PrinterConfig]:
    config_path = Path(path)
    if not config_path.exists():
        return {}

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    printers: Dict[str, PrinterConfig] = {}
    for printer_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            printers[printer_id] = PrinterConfig.from_dict(printer_id, entry, settings)
        except (KeyError, TypeError, ValueError):
            continue
    return printers


def save_printers_config(path: str, printers: Dict[str, PrinterConfig]) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {pid: cfg.to_dict() for pid, cfg in printers.items()}
    temp_path = config_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(config_path)
