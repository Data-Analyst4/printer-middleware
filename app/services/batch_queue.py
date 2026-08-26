"""Mode A bulk queue: same POD repeated N times, drain in chunks of 30.

With PRINT_BULK_RESUME (default on), a timeout/NYES/TCP drop does not drop the
rest of the job. Middleware reads RQLP printed count, leftover = plan - printed,
STAR, then continues sending leftover. STOP / RSAL 011 / FULL still hard-stop.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.utils.logger import log

MAX_COUNT = int(os.getenv("PRINT_BULK_MAX_COUNT", "100000"))
CHUNK_SIZE = max(1, int(os.getenv("PRINT_CHUNK_SIZE", "30")))
CHUNK_PAUSE_S = float(os.getenv("PRINT_CHUNK_PAUSE_MS", "400")) / 1000.0
SLOW_ACK_MS = float(os.getenv("PRINT_CHUNK_SLOW_ACK_MS", "80"))
RESUME_ENABLED = os.getenv("PRINT_BULK_RESUME", "true").lower() == "true"
DATA_RETRIES = max(1, int(os.getenv("PRINT_BULK_DATA_RETRIES", "3")))
RECOVER_MAX = max(0, int(os.getenv("PRINT_BULK_RECOVER_MAX", "20")))
STAR_RETRIES = max(1, int(os.getenv("PRINT_BULK_STAR_RETRIES", "3")))

BATCH_LOCK = threading.Lock()
# printer_id -> job_id of queued/running bulk
ACTIVE_BATCH: Dict[str, str] = {}
CANCEL_EVENTS: Dict[str, threading.Event] = {}

HARD_ALARM_CODES = {"011"}
HARD_STATUSES = {"FULL", "SYSN"}


def is_bulk_payload(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return "pod_data" in data or "items" in data


def validate_batch_request(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(data, dict):
        return False, "Invalid JSON payload"

    if "command" in data:
        return False, (
            "Cannot send command together with pod_data or items. "
            "Use command for STAR/STOP/single DATA, or pod_data+count for bulk."
        )

    if data.get("camera_import"):
        return False, "camera_import is not allowed on bulk requests (demo/single DATA only)"

    if "pod_data" in data and "items" in data:
        return False, "Cannot send items together with pod_data. Use pod_data+count for bulk."

    if "items" in data:
        return False, "items[] (Mode B) is not supported in this build. Use pod_data + count."

    if "pod_data" not in data:
        return False, "Bulk request requires pod_data"

    pod_data = data.get("pod_data")
    if not isinstance(pod_data, dict) or not pod_data:
        return False, "pod_data must be a non-empty object (same as today's command.data)"

    if "count" not in data:
        return False, "Bulk request requires integer count >= 1"

    try:
        count = int(data["count"])
    except (TypeError, ValueError):
        return False, "Bulk request requires integer count >= 1"

    if count < 1:
        return False, "Bulk request requires integer count >= 1"

    if count > MAX_COUNT:
        return False, f"count {count} exceeds maximum {MAX_COUNT}"

    if "printer_id" not in data:
        return False, "Missing printer_id"

    printer = data.get("printer")
    if not isinstance(printer, dict):
        return False, "Missing printer info"

    ip = printer.get("ip")
    port = printer.get("port")
    if not ip or not isinstance(ip, str):
        return False, "Invalid IP"
    if port is None or not str(port).isdigit():
        return False, "Invalid Port"

    return True, None


def _now() -> str:
    return datetime.now().isoformat()


def _batch_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    return dict(job)


def active_job_id(printer_id: str) -> Optional[str]:
    with BATCH_LOCK:
        return ACTIVE_BATCH.get(printer_id)


def cancel_printer_batch(printer_id: str) -> Dict[str, Any]:
    """Stop drain for this printer. Remaining unsent labels are dropped."""
    from app.services.printer_manager import REQUEST_RESULTS, RESULTS_LOCK

    with BATCH_LOCK:
        job_id = ACTIVE_BATCH.get(printer_id)
        event = CANCEL_EVENTS.get(printer_id)

    if not job_id:
        return {
            "batch_cancelled": False,
            "cancelled_job_id": None,
            "cancelled_remaining": 0,
        }

    if event:
        event.set()

    remaining = 0
    with RESULTS_LOCK:
        job = REQUEST_RESULTS.get(job_id)
        if job and job.get("execution_mode") == "batch":
            sent = int(job.get("sent_to_printer") or 0)
            total = int(job.get("count") or 0)
            remaining = max(0, total - sent)
            if job.get("status") in {"queued", "running"}:
                job["status"] = "stopped"
                job["message"] = "Bulk drain cancelled by STOP"
                job["updated_at"] = _now()
                job["cancelled_remaining"] = remaining

    with BATCH_LOCK:
        if ACTIVE_BATCH.get(printer_id) == job_id:
            ACTIVE_BATCH.pop(printer_id, None)

    log(
        f"Bulk cancelled printer={printer_id} job_id={job_id} "
        f"cancelled_remaining={remaining}"
    )
    return {
        "batch_cancelled": True,
        "cancelled_job_id": job_id,
        "cancelled_remaining": remaining,
    }


def handle_batch_print(data: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.printer_manager import (
        REQUEST_RESULTS,
        RESULTS_LOCK,
        register_printer,
        save_printers,
        _store_result,
    )

    valid, error = validate_batch_request(data)
    if not valid:
        return {"success": False, "status": "rejected", "error": error}

    printer_id = str(data["printer_id"])
    ip = str(data["printer"]["ip"])
    port = int(data["printer"]["port"])
    pod_data = dict(data["pod_data"])
    count = int(data["count"])

    with BATCH_LOCK:
        existing = ACTIVE_BATCH.get(printer_id)
        if existing:
            return {
                "success": False,
                "status": "rejected",
                "error": (
                    f"Printer {printer_id} already has a bulk job running "
                    f"(job_id={existing}). Send STOP first."
                ),
                "job_id": existing,
            }

    register_printer(printer_id, ip, port)
    save_printers()

    job_id = str(uuid.uuid4())
    job = {
        "success": True,
        "job_id": job_id,
        "queue_id": job_id,
        "status": "queued",
        "execution_mode": "batch",
        "printer_id": printer_id,
        "printer": {"ip": ip, "port": port},
        "queued": count,
        "count": count,
        "sent_to_printer": 0,
        "rqlp_printed": None,
        "leftover": count,
        "recoveries": 0,
        "failed": 0,
        "chunk_size": CHUNK_SIZE,
        "resume_enabled": RESUME_ENABLED,
        "message": "Bulk job queued. Middleware will send DATA to the printer in chunks of 30.",
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
    }

    cancel_event = threading.Event()
    with BATCH_LOCK:
        ACTIVE_BATCH[printer_id] = job_id
        CANCEL_EVENTS[printer_id] = cancel_event

    _store_result(job)
    log(f"Bulk queued {job_id}: printer={printer_id} count={count} chunk={CHUNK_SIZE}")

    worker = threading.Thread(
        target=_drain_batch,
        name=f"bulk-{printer_id}-{job_id[:8]}",
        daemon=True,
        args=(job_id, printer_id, pod_data, count, cancel_event),
    )
    worker.start()
    return _batch_snapshot(job)


def _update_job(job_id: str, **fields: Any) -> None:
    from app.services.printer_manager import REQUEST_RESULTS, RESULTS_LOCK

    with RESULTS_LOCK:
        job = REQUEST_RESULTS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = _now()


def _clear_active(printer_id: str, job_id: str) -> None:
    with BATCH_LOCK:
        if ACTIVE_BATCH.get(printer_id) == job_id:
            ACTIVE_BATCH.pop(printer_id, None)
        event = CANCEL_EVENTS.get(printer_id)
        if event and event.is_set() and ACTIVE_BATCH.get(printer_id) != job_id:
            CANCEL_EVENTS.pop(printer_id, None)


def _is_hard_fail(result: Dict[str, Any]) -> bool:
    code = str(result.get("protocol_error_code") or "")
    if code in HARD_ALARM_CODES:
        return True
    cmd = (result.get("response_command") or "").upper()
    if cmd == "RSAL":
        return True
    status = (result.get("response_status") or "").upper()
    if status in HARD_STATUSES:
        return True
    reason = str(result.get("reason") or "")
    upper = reason.upper()
    if "INVALID VERSION" in upper:
        return True
    if "RSAL" in upper:
        return True
    if "STATUS FULL" in upper or upper.endswith(" FULL"):
        return True
    return False


def _is_nyes(result: Dict[str, Any]) -> bool:
    if (result.get("response_command") or "").upper() == "NYES":
        return True
    if (result.get("response_status") or "").upper() == "NYES":
        return True
    return "NYES" in str(result.get("reason") or "").upper()


def _is_soft_tcp(result: Dict[str, Any]) -> bool:
    et = str(result.get("error_type") or "")
    if et in {"read_timeout", "empty_response", "transport_exception", "printer_busy"}:
        return True
    reason = str(result.get("reason") or "")
    blob = reason.lower()
    if "timed out" in blob or "timeout" in blob:
        return True
    if any(code in reason for code in ("10054", "10053", "10060")):
        return True
    if "forcibly closed" in blob or "connection reset" in blob or "broken pipe" in blob:
        return True
    return False


def _force_reconnect(printer_id: str) -> None:
    from app.services.printer_manager import PRINTERS

    printer = PRINTERS.get(printer_id)
    if not printer:
        return
    connection = printer.get("connection")
    if connection is not None and hasattr(connection, "force_reconnect"):
        connection.force_reconnect()


def _send_star(printer_id: str, send_fn) -> Dict[str, Any]:
    last: Dict[str, Any] = {"ok": False, "reason": "STAR not attempted"}
    for attempt in range(1, STAR_RETRIES + 1):
        try:
            last = send_fn(printer_id, {"command": "STAR"}, wait_for_ack=True)
        except Exception as exc:
            last = {
                "ok": False,
                "reason": str(exc),
                "error_type": "transport_exception",
            }
        if last.get("ok"):
            return last
        if _is_hard_fail(last):
            return last
        _force_reconnect(printer_id)
        time.sleep(0.3)
        log(f"Bulk STAR retry {attempt}/{STAR_RETRIES} printer={printer_id}: {last.get('reason')}")
    return last


def _query_rqlp_printed(printer_id: str, send_fn) -> Tuple[Optional[int], Optional[str]]:
    from app.services.camera_import_forwarder import parse_rqlp_result

    last_reason = "RQLP not attempted"
    for attempt in range(1, 3):
        try:
            result = send_fn(printer_id, {"command": "RQLP"}, wait_for_ack=True)
        except Exception as exc:
            last_reason = str(exc)
            _force_reconnect(printer_id)
            continue
        parsed = parse_rqlp_result(result, allow_zero=True)
        if parsed.get("success"):
            return int(parsed.get("printed_count") or 0), None
        last_reason = parsed.get("reason") or result.get("reason") or "RQLP failed"
        if _is_hard_fail(result):
            return None, last_reason
        _force_reconnect(printer_id)
        time.sleep(0.2)
        log(f"Bulk RQLP retry {attempt} printer={printer_id}: {last_reason}")
    return None, last_reason


def _send_data_with_retries(printer_id: str, command: Dict[str, Any], send_fn) -> Dict[str, Any]:
    last: Dict[str, Any] = {"ok": False, "reason": "DATA not attempted"}
    for attempt in range(1, DATA_RETRIES + 1):
        try:
            last = send_fn(printer_id, command, wait_for_ack=True)
        except Exception as exc:
            last = {
                "ok": False,
                "reason": str(exc),
                "error_type": "transport_exception",
            }
        if last.get("ok"):
            return last
        if _is_hard_fail(last) or _is_nyes(last):
            return last
        if _is_soft_tcp(last) and attempt < DATA_RETRIES:
            _force_reconnect(printer_id)
            time.sleep(0.2)
            continue
        return last
    return last


def _recover(
    job_id: str,
    printer_id: str,
    count: int,
    recoveries: int,
    send_fn,
) -> Tuple[str, int, Optional[int], str]:
    """RQLP first (never STAR first — STAR can reset printed count), then STAR.

    Returns (action, leftover, rqlp_printed, message)
    action: continue | done | fail
    """
    _force_reconnect(printer_id)
    printed, err = _query_rqlp_printed(printer_id, send_fn)
    if printed is None:
        return "fail", 0, None, err or "RQLP failed during recovery"

    leftover = max(0, count - printed)
    _update_job(
        job_id,
        status="running",
        rqlp_printed=printed,
        leftover=leftover,
        recoveries=recoveries,
        message=(
            f"Recovery {recoveries}: printer printed {printed}/{count}, "
            f"leftover={leftover}"
        ),
    )
    if leftover == 0:
        return "done", 0, printed, f"RQLP shows plan already printed ({printed}/{count})"

    star = _send_star(printer_id, send_fn)
    if not star.get("ok"):
        reason = star.get("reason") or "STAR failed during recovery"
        return "fail", leftover, printed, reason
    return "continue", leftover, printed, f"recovered leftover={leftover} after RQLP {printed}"


def _drain_batch(
    job_id: str,
    printer_id: str,
    pod_data: Dict[str, Any],
    count: int,
    cancel_event: threading.Event,
) -> None:
    from app.services.printer_manager import _send_command

    _update_job(job_id, status="running", message="Sending to printer")
    command = {"command": "DATA", "data": pod_data}
    sent = 0
    remaining = count
    recoveries = 0
    rqlp_printed: Optional[int] = None
    last_ack_ms = 0.0
    labels_since_pause = 0

    try:
        _force_reconnect(printer_id)

        while remaining > 0:
            if cancel_event.is_set():
                leftover = remaining
                _update_job(
                    job_id,
                    status="stopped",
                    message="Bulk drain cancelled by STOP",
                    cancelled_remaining=leftover,
                    leftover=leftover,
                    sent_to_printer=sent,
                    rqlp_printed=rqlp_printed,
                    recoveries=recoveries,
                )
                log(f"Bulk {job_id} stopped at {sent}/{count} leftover={leftover}")
                return

            started = time.perf_counter()
            result = _send_data_with_retries(printer_id, command, _send_command)
            last_ack_ms = (time.perf_counter() - started) * 1000.0

            if result.get("ok"):
                sent += 1
                remaining -= 1
                labels_since_pause += 1
                _update_job(
                    job_id,
                    sent_to_printer=sent,
                    leftover=remaining,
                    status="running",
                    recoveries=recoveries,
                    rqlp_printed=rqlp_printed,
                )
                if labels_since_pause >= CHUNK_SIZE and remaining > 0:
                    if last_ack_ms > SLOW_ACK_MS:
                        time.sleep(CHUNK_PAUSE_S)
                    labels_since_pause = 0
                continue

            reason = result.get("reason") or "Printer rejected DATA"
            if (not RESUME_ENABLED) or _is_hard_fail(result):
                _update_job(
                    job_id,
                    status="failed",
                    failed=1,
                    sent_to_printer=sent,
                    leftover=remaining,
                    recoveries=recoveries,
                    rqlp_printed=rqlp_printed,
                    error=reason,
                    message="Drain stopped. Remaining labels were not sent.",
                    last_printer_reason=reason,
                    last_printer_raw=result.get("raw_response"),
                )
                log(f"Bulk {job_id} failed at {sent}/{count}: {reason}", level="ERROR")
                return

            if recoveries >= RECOVER_MAX:
                _update_job(
                    job_id,
                    status="failed",
                    failed=1,
                    sent_to_printer=sent,
                    leftover=remaining,
                    recoveries=recoveries,
                    rqlp_printed=rqlp_printed,
                    error=f"Recovery limit {RECOVER_MAX} reached: {reason}",
                    message="Drain stopped after too many recoveries.",
                    last_printer_reason=reason,
                    last_printer_raw=result.get("raw_response"),
                )
                log(
                    f"Bulk {job_id} failed recoveries={recoveries} at {sent}/{count}: {reason}",
                    level="ERROR",
                )
                return

            recoveries += 1
            _update_job(
                job_id,
                status="running",
                recoveries=recoveries,
                sent_to_printer=sent,
                leftover=remaining,
                last_printer_reason=reason,
                last_printer_raw=result.get("raw_response"),
                message=f"Recovering after {reason}",
            )
            log(
                f"Bulk {job_id} recovery {recoveries}/{RECOVER_MAX} at {sent}/{count}: {reason}"
            )
            action, leftover, printed, rec_msg = _recover(
                job_id, printer_id, count, recoveries, _send_command
            )
            rqlp_printed = printed
            if action == "fail":
                _update_job(
                    job_id,
                    status="failed",
                    failed=1,
                    sent_to_printer=sent,
                    leftover=leftover,
                    recoveries=recoveries,
                    rqlp_printed=printed,
                    error=rec_msg,
                    message="Drain stopped during recovery. Remaining labels were not sent.",
                    last_printer_reason=rec_msg,
                )
                log(f"Bulk {job_id} recovery failed: {rec_msg}", level="ERROR")
                return
            if action == "done":
                _update_job(
                    job_id,
                    status="completed",
                    sent_to_printer=sent,
                    leftover=0,
                    failed=0,
                    error=None,
                    recoveries=recoveries,
                    rqlp_printed=printed,
                    message=rec_msg,
                )
                log(f"Bulk {job_id} completed via RQLP printed={printed}/{count}")
                return
            remaining = leftover
            labels_since_pause = 0
            log(f"Bulk {job_id} {rec_msg}")

        _update_job(
            job_id,
            status="completed",
            sent_to_printer=sent,
            leftover=0,
            failed=0,
            error=None,
            recoveries=recoveries,
            rqlp_printed=rqlp_printed,
            message="All DATA commands acknowledged by printer",
        )
        log(f"Bulk {job_id} completed sent={sent}/{count} recoveries={recoveries}")
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            sent_to_printer=sent,
            leftover=remaining,
            failed=1,
            recoveries=recoveries,
            rqlp_printed=rqlp_printed,
            error=str(exc),
            message="Drain stopped. Remaining labels were not sent.",
        )
        log(f"Bulk {job_id} crashed: {exc}", level="ERROR")
    finally:
        _clear_active(printer_id, job_id)
