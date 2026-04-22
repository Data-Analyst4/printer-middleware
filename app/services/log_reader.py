import json
import os
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional, Tuple


JSON_LOG_PATH = os.path.join("logs", "app.jsonl")
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MAX_OFFSET = 10000


def _parse_positive_int(
    raw_value: Optional[str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    if raw_value is None:
        return default, None

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None, {
            "success": False,
            "error": f"Invalid '{name}': must be an integer",
            "error_type": "validation_error",
            "details": {"parameter": name},
        }

    if value < minimum or value > maximum:
        return None, {
            "success": False,
            "error": f"Invalid '{name}': must be between {minimum} and {maximum}",
            "error_type": "validation_error",
            "details": {"parameter": name, "minimum": minimum, "maximum": maximum},
        }

    return value, None


def _parse_datetime(raw_value: Optional[str], name: str) -> Tuple[Optional[datetime], Optional[Dict[str, Any]]]:
    if not raw_value:
        return None, None

    value = raw_value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, {
            "success": False,
            "error": f"Invalid '{name}': must be ISO-8601 datetime",
            "error_type": "validation_error",
            "details": {"parameter": name},
        }

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed, None


def _entry_timestamp(entry: Dict[str, Any]) -> Optional[datetime]:
    timestamp = entry.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None

    value = timestamp.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed


def _matches_filters(
    entry: Dict[str, Any],
    level: Optional[str],
    job_id: Optional[str],
    printer_id: Optional[str],
    query_text: Optional[str],
    since: Optional[datetime],
    until: Optional[datetime],
) -> bool:
    if level and str(entry.get("level", "")).upper() != level:
        return False

    if job_id and str(entry.get("job_id", "")) != job_id:
        return False

    if printer_id and str(entry.get("printer_id", "")) != printer_id:
        return False

    if query_text:
        message = str(entry.get("message", "")).lower()
        if query_text not in message:
            return False

    if since is not None or until is not None:
        entry_time = _entry_timestamp(entry)
        if entry_time is None:
            return False
        if since is not None and entry_time < since:
            return False
        if until is not None and entry_time > until:
            return False

    return True


def read_app_json_logs(params: Dict[str, Any]) -> Dict[str, Any]:
    limit, limit_error = _parse_positive_int(
        params.get("limit"),
        name="limit",
        default=DEFAULT_LIMIT,
        minimum=1,
        maximum=MAX_LIMIT,
    )
    if limit_error:
        return limit_error

    offset, offset_error = _parse_positive_int(
        params.get("offset"),
        name="offset",
        default=0,
        minimum=0,
        maximum=MAX_OFFSET,
    )
    if offset_error:
        return offset_error

    level = params.get("level")
    if level is not None:
        level = str(level).strip().upper()
        if not level:
            level = None

    job_id = params.get("job_id")
    if job_id is not None:
        job_id = str(job_id).strip() or None

    printer_id = params.get("printer_id")
    if printer_id is not None:
        printer_id = str(printer_id).strip() or None

    query_text = params.get("q")
    if query_text is not None:
        query_text = str(query_text).strip().lower() or None

    since, since_error = _parse_datetime(params.get("since"), name="since")
    if since_error:
        return since_error

    until, until_error = _parse_datetime(params.get("until"), name="until")
    if until_error:
        return until_error

    if since is not None and until is not None and since > until:
        return {
            "success": False,
            "error": "Invalid range: 'since' must be less than or equal to 'until'",
            "error_type": "validation_error",
            "details": {"parameter": "since,until"},
        }

    if not os.path.exists(JSON_LOG_PATH):
        return {
            "success": False,
            "error": "Log file not found",
            "error_type": "not_found",
            "details": {"path": JSON_LOG_PATH},
        }

    window_size = limit + offset
    matched_window: Deque[Dict[str, Any]] = deque(maxlen=window_size)
    matched_total = 0
    invalid_json_lines = 0
    scanned_lines = 0

    with open(JSON_LOG_PATH, "r", encoding="utf-8", errors="replace") as file_obj:
        for raw_line in file_obj:
            scanned_lines += 1
            line = raw_line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                invalid_json_lines += 1
                continue

            if not isinstance(entry, dict):
                invalid_json_lines += 1
                continue

            if not _matches_filters(entry, level, job_id, printer_id, query_text, since, until):
                continue

            matched_total += 1
            matched_window.append(entry)

    newest_first = list(matched_window)
    newest_first.reverse()
    logs_page = newest_first[offset : offset + limit]

    return {
        "success": True,
        "source": JSON_LOG_PATH,
        "count": len(logs_page),
        "total_matched": matched_total,
        "scanned_lines": scanned_lines,
        "invalid_json_lines": invalid_json_lines,
        "has_more": matched_total > (offset + limit),
        "filters": {
            "level": level,
            "job_id": job_id,
            "printer_id": printer_id,
            "q": query_text,
            "since": params.get("since"),
            "until": params.get("until"),
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "order": "desc",
        },
        "logs": logs_page,
    }
