"""Protocol compatibility tests."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.core.config import Settings
from app.printer.protocol import extract_single_command, serialize_command
from app.printer.response_parser import classify_result, parse_response_bytes


def test_extract_single_command():
    payload = {"command": {"command": "STAR", "templatename": "DEMO"}}
    cmd = extract_single_command(payload)
    assert cmd["command"] == "STAR"


def test_serialize_command():
    settings = Settings.from_env()
    payload = serialize_command({"command": "DATA", "data": {"POD1": "1"}}, settings)
    assert b"DATA" in payload


def test_parse_text_response():
    parsed = parse_response_bytes(b"STAR;YES")
    assert parsed["response_command"] == "STAR"
    result = {"response_command": "STAR", "response_status": "YES"}
    classified = classify_result(result)
    assert classified["ok"] is True


def test_parse_sysn_failure():
    parsed = parse_response_bytes(b"RSP;SYSN;001")
    result = {**parsed}
    classified = classify_result(result)
    assert classified["ok"] is False
