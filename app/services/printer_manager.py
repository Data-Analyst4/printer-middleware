import json
import os
import time
from queue import PriorityQueue
import threading
import itertools
from app.services.queue_worker import printer_worker
from app.services.connection_manager import ConnectionManager
from app.services.job_manager import JobManager
from app.models.job import JobStatus
from app.utils.validator import validate_request
from app.utils.logger import log

PRINTERS = {}  # printer_id -> {"ip":, "port":, "queue":, "connection":, "worker_thread":}
JOB_MANAGER = JobManager()
CONFIG_PATH = "config/printers.json"
_counter = itertools.count()

def load_printers():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            print("Error loading printers.json:", e)
            return {}
    return {}

def save_printers():
    data = {}
    for pid, p in PRINTERS.items():
        data[pid] = {"ip": p["ip"], "port": p["port"]}
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

def register_printer(printer_id, ip, port):
    if printer_id in PRINTERS:
        # Update existing printer target and keep the same queue/worker
        existing = PRINTERS[printer_id]
        existing["ip"] = ip
        existing["port"] = port
        existing["connection"].update_target(ip, port)
        return

    # Create priority queue: (priority_number, counter, job)
    # Lower priority number = higher priority
    queue = PriorityQueue()

    # Create connection manager
    connection = ConnectionManager(printer_id, ip, port)

    PRINTERS[printer_id] = {
        "ip": ip,
        "port": port,
        "queue": queue,
        "connection": connection,
        "worker_thread": None
    }

    # Start worker thread
    worker_thread = threading.Thread(target=printer_worker, args=(PRINTERS[printer_id], JOB_MANAGER), daemon=True)
    worker_thread.start()
    PRINTERS[printer_id]["worker_thread"] = worker_thread

def handle_print_request(data):
    valid, error = validate_request(data)
    if not valid:
        return {"success": False, "error": error}

    printer_id = data["printer_id"]
    ip = data["printer"]["ip"]
    port = data["printer"]["port"]

    # Get the command(s) directly from the request
    if "command" in data:
        commands = [data["command"]]
    else:
        commands = data["commands"]

    # Get priority (default to normal)
    priority = data.get("priority", "normal")

    register_printer(printer_id, ip, port)
    save_printers()

    # Create job and enqueue for background processing
    job = JOB_MANAGER.create_job(printer_id, commands, priority)
    priority_num = 1 if priority.lower() == "high" else 2
    PRINTERS[printer_id]["queue"].put((priority_num, next(_counter), job))
    log(f"Queued job {job.job_id} for printer {printer_id} with priority {priority}")

    return {
        "success": True,
        "job_id": job.job_id,
        "status": job.status.value,
        "message": "Job queued; poll /job/<job_id> for status"
    }

def get_all_printers():
    return {
        pid: {
            "ip": p["ip"],
            "port": p["port"],
            "queue_size": p["queue"].qsize(),
            "connection_status": "connected" if p["connection"].connected else "disconnected"
        }
        for pid, p in PRINTERS.items()
    }

def get_job_result(job_id):
    job = JOB_MANAGER.get_job(job_id)
    if not job:
        return {"success": False, "error": "Job not found"}
    return {"success": True, **job.to_dict()}

def get_all_jobs():
    return {"success": True, "jobs": JOB_MANAGER.get_all_jobs()}

def get_metrics():
    return {"success": True, **JOB_MANAGER.get_metrics()}

# Load existing printers on startup
for pid, cfg in load_printers().items():
    register_printer(pid, cfg["ip"], cfg["port"])
