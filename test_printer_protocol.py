import os

from app.services.printer_protocol import extract_commands, serialize_command


def test_extract_commands_accepts_single_command_object():
    payload = {
        "printer_id": "P1",
        "printer": {"ip": "127.0.0.1", "port": 5000},
        "command": {"command": "STAR", "templatename": "DEMO"},
    }

    commands = extract_commands(payload)

    assert commands == [{"command": "STAR", "templatename": "DEMO"}]


def test_extract_commands_accepts_nested_command_wrapper():
    payload = {
        "commands": [
            {"command": {"command": "DATA", "data": {"POD1": "123"}}},
        ]
    }

    commands = extract_commands(payload)

    assert commands == [{"command": "DATA", "data": {"POD1": "123"}}]


def test_serialize_command_uses_compact_json_bytes():
    previous = os.environ.pop("PRINTER_PAYLOAD_SUFFIX", None)

    try:
        payload = serialize_command(
            {"command": "STAR", "templatename": "DEMO", "startpage": "1"}
        )
    finally:
        if previous is not None:
            os.environ["PRINTER_PAYLOAD_SUFFIX"] = previous

    assert payload == b'{"command":"STAR","templatename":"DEMO","startpage":"1"}'


def test_serialize_command_applies_newline_suffix_alias():
    previous = os.environ.get("PRINTER_PAYLOAD_SUFFIX")
    os.environ["PRINTER_PAYLOAD_SUFFIX"] = "newline"

    try:
        payload = serialize_command({"command": "DATA", "data": {"POD1": "123"}})
    finally:
        if previous is None:
            os.environ.pop("PRINTER_PAYLOAD_SUFFIX", None)
        else:
            os.environ["PRINTER_PAYLOAD_SUFFIX"] = previous

    assert payload.endswith(b"\n")
