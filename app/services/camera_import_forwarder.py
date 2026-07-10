"""
Camera import_batch forwarder.

Default flow (v1.2.0+ "Immediate camera import"):
  On DATA, POST {barcode, text} to the camera URL immediately (before printer send).
  Text is built from request POD fields. Print success is independent of camera.

Legacy flow (kept, unused by default):
  After DATA ACK, RQLP confirm last print, then POST camera.
  Enable with CAMERA_IMPORT_FLOW=rqlp.

Payload: { "barcode": "<EAN>", "text": "<POD1><POD2>..." }

ERP should check camera_import.erp_alert_recommended and send WhatsApp when
alert_reasons includes empty_barcode and/or camera_http_failure.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from app.services.pod_forwarder import build_pod_string
from app.utils.logger import log

DEFAULT_CAMERA_URL = os.getenv(
    "CAMERA_IMPORT_BATCH_URL",
    "http://192.168.0.68:5001/api/import_batch",
)
CAMERA_IMPORT_ENABLED = os.getenv("CAMERA_IMPORT_ENABLED", "true").lower() == "true"
CAMERA_IMPORT_TIMEOUT = float(os.getenv("CAMERA_IMPORT_TIMEOUT", "3"))
# immediate = POST before printer send (default). rqlp = legacy after-print confirm.
CAMERA_IMPORT_FLOW = os.getenv("CAMERA_IMPORT_FLOW", "immediate").strip().lower()
RQLP_MAX_ATTEMPTS = max(1, int(os.getenv("CAMERA_RQLP_MAX_ATTEMPTS", "3")))
RQLP_RETRY_DELAY_S = float(os.getenv("CAMERA_RQLP_RETRY_DELAY_S", "0.15"))


def get_camera_import_flow() -> str:
    """Return active camera flow: 'immediate' (default) or 'rqlp' (legacy)."""
    if CAMERA_IMPORT_FLOW == "rqlp":
        return "rqlp"
    return "immediate"


def _col_sort_key(key: str) -> int:
    upper = key.upper()
    if upper.startswith("COL"):
        suffix = upper[3:]
        if suffix.isdigit():
            return int(suffix)
    return 10**9


def build_text_from_col_data(col_data: Dict[str, Any]) -> str:
    """Concatenate col1, col2, … in numeric order (no delimiter)."""
    if not isinstance(col_data, dict):
        return ""
    keys = [k for k in col_data if str(k).upper().startswith("COL")]
    if not keys:
        return ""
    keys.sort(key=_col_sort_key)
    return "".join(str(col_data[k] if col_data[k] is not None else "") for k in keys)


def parse_rqlp_result(command_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse middleware/printer RQLP (RSFP) response.

    Returns:
      success, printed_count, total_count, col_data, value_str, reason
    """
    out: Dict[str, Any] = {
        "success": False,
        "printed_count": 0,
        "total_count": 0,
        "col_data": {},
        "value_str": None,
        "reason": None,
        "raw": command_result,
    }

    if not command_result or not command_result.get("ok"):
        out["reason"] = (command_result or {}).get("reason") or "RQLP command failed"
        return out

    response_cmd = (command_result.get("response_command") or "").upper()
    # Accept RSFP (normal) or any ok response that carries value/data
    body = command_result.get("response")
    value_str = None
    col_data: Dict[str, Any] = {}

    if isinstance(body, dict):
        value_str = body.get("value")
        data = body.get("data")
        if isinstance(data, dict):
            col_data = data
        cmd = str(body.get("command") or response_cmd or "").upper()
        if cmd and cmd not in {"RSFP", "RQLP", "YES"} and not value_str:
            out["reason"] = f"Unexpected RQLP response command: {cmd}"
            return out
    elif isinstance(body, str):
        # Text fallback: RSFP;1/1 or similar
        parts = [p.strip() for p in body.replace("<STX>", "").replace("<ETX>", "").split(";") if p.strip()]
        if parts and parts[0].upper() == "RSFP" and len(parts) > 1:
            value_str = parts[1]

    if not value_str and command_result.get("response_fields"):
        fields = command_result["response_fields"]
        if fields and "/" in str(fields[0]):
            value_str = str(fields[0])

    if not value_str or "/" not in str(value_str):
        out["reason"] = "RQLP response missing printed count value (expected X/Y)"
        return out

    value_str = str(value_str).strip()
    out["value_str"] = value_str
    try:
        printed_s, total_s = value_str.split("/", 1)
        printed_count = int(printed_s.strip())
        total_count = int(total_s.strip())
    except (ValueError, TypeError):
        out["reason"] = f"Invalid RQLP count format: {value_str}"
        return out

    out["printed_count"] = printed_count
    out["total_count"] = total_count
    out["col_data"] = col_data

    if printed_count < 1:
        out["reason"] = f"Printer reports no labels printed yet ({value_str})"
        return out

    out["success"] = True
    out["reason"] = "RQLP confirmed last print"
    return out


def resolve_camera_target(request_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (url, barcode) when camera_import is enabled on the request."""
    if not CAMERA_IMPORT_ENABLED:
        return None, None

    inline = request_data.get("camera_import")
    if not isinstance(inline, dict) or not inline.get("enabled"):
        return None, None

    barcode = str(inline.get("barcode") or "").strip()
    url = str(inline.get("url") or DEFAULT_CAMERA_URL).strip()
    if not url:
        return None, None

    if not barcode:
        log(
            "Camera import barcode empty — ERP should alert (empty_barcode)",
            level="WARNING",
            extra_data={"camera_import_missing_barcode": True},
        )

    return url, barcode


def resolve_camera_import(
    request_data: Dict[str, Any],
    pod_data: Optional[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolve url/barcode/text from request POD (no RQLP).
    Used by the default immediate camera flow.
    """
    url, barcode = resolve_camera_target(request_data)
    if url is None:
        return None, None, None
    if not isinstance(pod_data, dict):
        return None, None, None
    text = build_pod_string(pod_data)
    if not text:
        return None, None, None
    return url, barcode, text


def forward_camera_import_immediate(
    job_id: str,
    request_data: Dict[str, Any],
    pod_data: Optional[Dict[str, Any]],
    *,
    printer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sync: build text from POD and POST camera before printer send.

    Does not raise; always returns meta for the /print response so ERP can
    WhatsApp on empty_barcode or camera_http_failure.
    """
    url, barcode = resolve_camera_target(request_data)
    meta: Dict[str, Any] = {
        "attempted": False,
        "flow": "immediate",
        "camera_ok": False,
        "url": url,
        "barcode": barcode if barcode is not None else "",
        "missing_barcode": False,
        "erp_alert_recommended": False,
        "alert_reasons": [],
        "status": "skipped",
        "reason": None,
        "text_source": "sent_pod",
        "text_length": 0,
    }

    if url is None:
        meta["reason"] = "camera_import not enabled"
        return meta

    missing_barcode = not bool(barcode)
    meta["missing_barcode"] = missing_barcode
    meta["attempted"] = True

    if missing_barcode:
        meta["alert_reasons"].append("empty_barcode")
        meta["erp_alert_recommended"] = True

    text = build_pod_string(pod_data if isinstance(pod_data, dict) else {})
    meta["text_length"] = len(text)

    if not text:
        meta["status"] = "no_text"
        meta["reason"] = "no POD text available for camera"
        log(
            meta["reason"],
            level="ERROR",
            job_id=job_id,
            printer_id=printer_id,
            extra_data={"camera_import": meta},
        )
        return meta

    camera_result = post_camera_import(url, barcode or "", text)
    meta["camera"] = camera_result
    meta["camera_ok"] = bool(camera_result.get("ok"))
    meta["status"] = "sent" if camera_result.get("ok") else "camera_failed"
    meta["reason"] = camera_result.get("reason")

    if not camera_result.get("ok"):
        meta["alert_reasons"].append("camera_http_failure")
        meta["erp_alert_recommended"] = True

    level = "INFO" if camera_result.get("ok") else "ERROR"
    log(
        (
            f"Immediate camera import "
            f"{'succeeded' if camera_result.get('ok') else 'failed'} "
            f"barcode={barcode or '(empty)'} text_len={len(text)} url={url}"
            f"{' alerts=' + ','.join(meta['alert_reasons']) if meta['alert_reasons'] else ''}"
        ),
        level=level,
        job_id=job_id,
        printer_id=printer_id,
        extra_data={"camera_import": meta},
    )
    return meta


def post_camera_import(url: str, barcode: str, text: str) -> Dict[str, Any]:
    payload = json.dumps({"barcode": barcode, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    result: Dict[str, Any] = {
        "ok": False,
        "url": url,
        "barcode": barcode,
        "text_length": len(text),
        "status_code": None,
        "reason": None,
    }

    try:
        with urllib.request.urlopen(req, timeout=CAMERA_IMPORT_TIMEOUT) as resp:
            result["status_code"] = resp.getcode()
            result["ok"] = 200 <= resp.getcode() < 300
            result["reason"] = "OK" if result["ok"] else f"HTTP {resp.getcode()}"
    except urllib.error.HTTPError as exc:
        result["status_code"] = exc.code
        result["reason"] = f"HTTP {exc.code}: {exc.reason}"
    except Exception as exc:
        result["reason"] = str(exc)

    return result


def query_last_printed(printer_id: str) -> Dict[str, Any]:
    """Send RQLP to the printer and parse RSFP last-print status."""
    from app.services.printer_manager import PRINTERS

    printer = PRINTERS.get(printer_id)
    if not printer:
        return {
            "success": False,
            "reason": f"Printer {printer_id} not registered",
            "printed_count": 0,
            "total_count": 0,
            "col_data": {},
        }

    connection = printer["connection"]
    last_error = "RQLP failed"
    last_raw = None

    for attempt in range(1, RQLP_MAX_ATTEMPTS + 1):
        try:
            command_result = connection.send_command({"command": "RQLP"})
        except Exception as exc:
            last_error = f"RQLP transport error: {exc}"
            log(last_error, level="ERROR", printer_id=printer_id)
            if attempt < RQLP_MAX_ATTEMPTS:
                time.sleep(RQLP_RETRY_DELAY_S * attempt)
            continue

        last_raw = command_result
        parsed = parse_rqlp_result(command_result)
        if parsed["success"]:
            return parsed

        last_error = parsed.get("reason") or "RQLP not confirmed"
        if attempt < RQLP_MAX_ATTEMPTS:
            time.sleep(RQLP_RETRY_DELAY_S * attempt)

    return {
        "success": False,
        "reason": last_error,
        "printed_count": 0,
        "total_count": 0,
        "col_data": {},
        "raw": last_raw,
    }


def build_camera_text_after_rqlp(
    rqlp: Dict[str, Any],
    sent_pod_data: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """
    Build camera text from RQLP col data; fall back to sent POD if cols empty
    but RQLP already confirmed print success.
    Returns (text, source) where source is 'rqlp_cols' | 'sent_pod' | ''.
    """
    col_text = build_text_from_col_data(rqlp.get("col_data") or {})
    if col_text:
        return col_text, "rqlp_cols"

    pod_text = build_pod_string(sent_pod_data or {})
    if pod_text:
        return pod_text, "sent_pod"

    return "", ""


def verify_last_print_and_forward_camera(
    job_id: str,
    printer_id: str,
    request_data: Dict[str, Any],
    sent_pod_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Legacy (CAMERA_IMPORT_FLOW=rqlp): RQLP confirm last print, then POST camera.
    Default production path is forward_camera_import_immediate.
    """
    url, barcode = resolve_camera_target(request_data)
    meta: Dict[str, Any] = {
        "attempted": False,
        "rqlp_ok": False,
        "camera_ok": False,
        "url": url,
        "barcode": barcode if barcode is not None else "",
        "missing_barcode": barcode == "" if barcode is not None else None,
        "status": "skipped",
        "reason": None,
    }

    if url is None:
        meta["reason"] = "camera_import not enabled"
        return meta

    meta["attempted"] = True
    meta["status"] = "awaiting_rqlp"

    rqlp = query_last_printed(printer_id)
    meta["rqlp"] = {
        "success": rqlp.get("success"),
        "value": rqlp.get("value_str"),
        "printed_count": rqlp.get("printed_count"),
        "total_count": rqlp.get("total_count"),
        "reason": rqlp.get("reason"),
    }

    if not rqlp.get("success"):
        meta["status"] = "rqlp_failed"
        meta["reason"] = rqlp.get("reason") or "RQLP did not confirm last print"
        log(
            f"Camera import skipped — RQLP not confirmed: {meta['reason']}",
            level="ERROR",
            job_id=job_id,
            printer_id=printer_id,
            extra_data={"camera_import": meta},
        )
        return meta

    meta["rqlp_ok"] = True
    text, text_source = build_camera_text_after_rqlp(rqlp, sent_pod_data)
    meta["text_source"] = text_source
    meta["text_length"] = len(text)

    if not text:
        meta["status"] = "no_text"
        meta["reason"] = "RQLP ok but no POD/col text available"
        log(
            meta["reason"],
            level="ERROR",
            job_id=job_id,
            printer_id=printer_id,
            extra_data={"camera_import": meta},
        )
        return meta

    if text_source == "sent_pod":
        log(
            "RQLP confirmed print but col data empty — using sent POD values for camera text",
            level="WARNING",
            job_id=job_id,
            printer_id=printer_id,
        )

    camera_result = post_camera_import(url, barcode or "", text)
    meta["camera_ok"] = bool(camera_result.get("ok"))
    meta["camera"] = camera_result
    meta["status"] = "sent" if camera_result.get("ok") else "camera_failed"
    meta["reason"] = camera_result.get("reason")

    level = "INFO" if camera_result.get("ok") else "ERROR"
    log(
        (
            f"Camera import {'succeeded' if camera_result.get('ok') else 'failed'} "
            f"after RQLP {rqlp.get('value_str')} barcode={barcode or '(empty)'} "
            f"text_src={text_source} text_len={len(text)} url={url}"
        ),
        level=level,
        job_id=job_id,
        printer_id=printer_id,
        extra_data={"camera_import": meta},
    )
    return meta


def forward_camera_import_after_rqlp_async(
    job_id: str,
    printer_id: str,
    request_data: Dict[str, Any],
    sent_pod_data: Optional[Dict[str, Any]],
) -> None:
    """Background: RQLP confirm → camera POST. Print path already returned."""

    def _run() -> None:
        try:
            verify_last_print_and_forward_camera(
                job_id,
                printer_id,
                request_data,
                sent_pod_data,
            )
        except Exception as exc:
            log(
                f"Camera import after RQLP crashed: {exc}",
                level="ERROR",
                job_id=job_id,
                printer_id=printer_id,
            )

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"camera-rqlp-{job_id[:8]}",
    ).start()


# Back-compat alias used by older call sites
def forward_camera_import_async(
    job_id: str,
    url: str,
    barcode: str,
    text: str,
    *,
    printer_id: Optional[str] = None,
) -> None:
    def _run() -> None:
        result = post_camera_import(url, barcode, text)
        level = "INFO" if result["ok"] else "ERROR"
        log(
            (
                f"Camera import {'succeeded' if result['ok'] else 'failed'} "
                f"barcode={barcode} text_len={len(text)} url={url}"
            ),
            level=level,
            job_id=job_id,
            printer_id=printer_id,
            extra_data={"camera_import": result},
        )

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"camera-import-{job_id[:8]}",
    ).start()
