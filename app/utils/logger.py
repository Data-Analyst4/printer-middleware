import json
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")
JSON_LOG_FILE = os.path.join(LOG_DIR, "app.jsonl")
ERP_REQUEST_LOG = os.path.join(LOG_DIR, "erp_requests.jsonl")


def log_erp_request(payload):
    """Write the exact POST /print JSON from ERP (bulk app only)."""
    os.makedirs(LOG_DIR, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "path": "/print",
        "body": payload,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with open(ERP_REQUEST_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    kind = "unknown"
    if isinstance(payload, dict):
        if "pod_data" in payload:
            kind = "bulk_pod_data_count"
        elif "items" in payload:
            kind = "bulk_items"
        elif isinstance(payload.get("command"), dict):
            kind = str(payload["command"].get("command") or "command").upper()
        elif "command" in payload:
            kind = "command"
    log(f"ERP /print body kind={kind} bytes={len(line)}")

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def log(message, level="INFO", job_id=None, printer_id=None, extra_data=None):
    """Enhanced logging with structured JSON logs"""
    timestamp = datetime.now().isoformat()

    # Console log
    log_line = f"{timestamp} [{level}] {message}"
    if job_id:
        log_line += f" [Job: {job_id}]"
    if printer_id:
        log_line += f" [Printer: {printer_id}]"
    print(log_line, flush=True)

    # File log
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")

    # Structured JSON log
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message,
        "job_id": job_id,
        "printer_id": printer_id
    }
    if extra_data:
        log_entry.update(extra_data)

    with open(JSON_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")