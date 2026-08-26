"""
Printer Middleware - Enterprise-grade printer management system
"""

__version__ = "1.4.1"
__version_info__ = tuple(map(int, __version__.split('.')))

# Version history
VERSION_HISTORY = {
    "1.4.1": {
        "date": "2026-08-26",
        "title": "Bulk resume on timeout/NYES",
        "changes": [
            "PRINT_BULK_RESUME keeps a bulk job running after timeout, NYES, or TCP drop",
            "Recovery reads RQLP printed count first, leftover = plan - printed, then STAR",
            "Retry the same DATA 2-3 times on soft TCP errors before RQLP recovery",
            "STOP, RSAL 011, and FULL still hard-stop the job",
            "While bulk is running, ERP STAR/DATA/RQLP are rejected; poll GET /job/{id}; STOP allowed",
            "GET /job reports rqlp_printed, leftover, recoveries",
        ],
    },
    "1.4.0": {
        "date": "2026-08-20",
        "title": "Bulk Mode A (pod_data + count)",
        "changes": [
            "POST /print with pod_data+count queues same POD x N and returns immediately",
            "Background drain sends DATA in chunks of 30 and waits for printer RYES",
            "GET /job/{job_id} reports sent_to_printer and batch status",
            "STOP cancels any in-progress bulk drain then stops the printer",
            "R10E root app: same /print URL also accepts pod_data+count (Mode A bulk)",
            "Single command STAR/STOP/DATA/MON/RQLP and camera_import demo path unchanged",
            "v1.3.0 kept in releases/v1.3.0-r10e for rollback",
        ],
    },
    "1.3.0": {
        "date": "2026-08-20",
        "title": "Fast DATA send",
        "changes": [
            "DATA commands are written to the printer without waiting for a 5s ACK",
            "STAR/STOP/MON/RQLP still wait for printer response",
            "Camera import POST runs in a background thread so a dead camera cannot delay print",
            "v1.2.0 code kept in releases/v1.2.0 for rollback",
            "Set PRINTER_DATA_FIRE_AND_FORGET=false or CAMERA_IMPORT_ASYNC=false to restore old waits",
        ],
    },
    "1.2.0": {
        "date": "2026-07-11",
        "title": "Immediate camera import",
        "changes": [
            "DATA requests POST {barcode, text} to camera URL immediately before printer send",
            "Camera text built from request POD fields (no RQLP wait)",
            "Print success remains independent of camera HTTP result",
            "Response includes erp_alert_recommended and alert_reasons for ERP WhatsApp "
            "(empty_barcode, camera_http_failure)",
            "Camera URL from CAMERA_IMPORT_BATCH_URL env or per-request camera_import.url",
            "Legacy RQLP-after-print flow kept; enable with CAMERA_IMPORT_FLOW=rqlp"
        ]
    },
    "1.1.0": {
        "date": "2026-04-08",
        "changes": [
            "Added direct printer command send/response flow for web app use",
            "Added printer protocol parsing and payload serialization helpers",
            "Added Cloudflare tunnel and Windows service deployment scripts",
            "Improved printer connection diagnostics and response reporting"
        ]
    },
    "1.0.0": {
        "date": "2024-12-19",
        "changes": [
            "Initial enterprise-grade release",
            "Async API with job queuing",
            "Persistent SQLite storage",
            "Worker thread processing",
            "Retry engine with exponential backoff",
            "WebSocket real-time monitoring",
            "Production server support (Waitress)",
            "Windows service compatibility"
        ]
    }
}


def get_version():
    """Get current version string"""
    return __version__


def get_version_info():
    """Get detailed version information"""
    return {
        "version": __version__,
        "version_info": __version_info__,
        "history": VERSION_HISTORY
    }
