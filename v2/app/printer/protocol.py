"""Printer command protocol — same JSON-over-TCP format as v1."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.core.config import Settings


def normalize_single_command(command_obj: Any) -> Dict[str, Any]:
    if not isinstance(command_obj, dict):
        raise ValueError("Each command must be a JSON object")

    if (
        "command" in command_obj
        and isinstance(command_obj.get("command"), dict)
        and len(command_obj) == 1
    ):
        command_obj = command_obj["command"]

    cmd_name = command_obj.get("command")
    if not isinstance(cmd_name, str) or not cmd_name.strip():
        raise ValueError("Each command object must contain a non-empty 'command' string")

    return command_obj


def extract_single_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "commands" in payload:
        raise ValueError(
            "This API accepts one command per request. Use a single 'command' object, not 'commands'."
        )
    if "command" not in payload:
        raise ValueError("Missing command")
    return normalize_single_command(payload["command"])


def extract_commands(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "command" in payload and "commands" in payload:
        raise ValueError("Cannot have both command and commands")

    if "command" in payload:
        raw_commands = [payload["command"]]
    elif "commands" in payload:
        raw_commands = payload["commands"]
        if not isinstance(raw_commands, list) or not raw_commands:
            raise ValueError("'commands' must be a non-empty array")
    else:
        raise ValueError("Missing command or commands")

    commands: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_commands):
        try:
            commands.append(normalize_single_command(item))
        except ValueError as exc:
            raise ValueError(f"Invalid command at index {index}: {exc}") from exc
    return commands


def payload_suffix(settings: Settings) -> str:
    raw_value = settings.payload_suffix
    aliases = {"": "", "none": "", "lf": "\n", "newline": "\n", "crlf": "\r\n", "null": "\0"}
    alias_value = aliases.get(raw_value.strip().lower())
    if alias_value is not None:
        return alias_value
    try:
        return raw_value.encode("utf-8").decode("unicode_escape")
    except UnicodeDecodeError:
        return raw_value


def serialize_command(command_obj: Dict[str, Any], settings: Settings) -> bytes:
    normalized = normalize_single_command(command_obj)
    payload_text = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return (payload_text + payload_suffix(settings)).encode("utf-8")
