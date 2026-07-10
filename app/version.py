"""
Printer Middleware - Enterprise-grade printer management system
"""

__version__ = "1.2.0"
__version_info__ = tuple(map(int, __version__.split('.')))

# Version history
VERSION_HISTORY = {
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
