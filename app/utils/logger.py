import json
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "app.log")
JSON_LOG_FILE = os.path.join(LOG_DIR, "app.jsonl")

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