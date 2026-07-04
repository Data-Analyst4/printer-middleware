import json
import os
import tempfile

from app.services import pod_device_manager as manager


def test_upsert_and_get_pod_device(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "pod_devices.json")
        monkeypatch.setattr(manager, "CONFIG_PATH", config_path)
        monkeypatch.setattr(manager, "PERSIST_POD_DEVICES", True)
        manager.POD_DEVICES.clear()

        result = manager.upsert_pod_device(
            "CAMERA_LINE_A",
            {"name": "Line A Camera", "ip": "192.168.1.50", "port": 9101, "enabled": True},
        )

        assert result["success"] is True
        device = manager.get_pod_device("CAMERA_LINE_A")
        assert device is not None
        assert device["ip"] == "192.168.1.50"
        assert device["port"] == 9101

        with open(config_path, "r", encoding="utf-8") as file:
            saved = json.load(file)

        assert saved["CAMERA_LINE_A"]["ip"] == "192.168.1.50"


def test_resolve_pod_target_prefers_inline_request(monkeypatch):
    monkeypatch.setattr(
        manager,
        "get_pod_device",
        lambda device_id: {"ip": "10.0.0.1", "port": 9000, "enabled": True},
    )

    target, device_id, source = manager.resolve_pod_target(
        {
            "pod_device_id": "CAMERA_LINE_A",
            "pod_device": {"ip": "192.168.1.60", "port": 9102},
        }
    )

    assert target == {"ip": "192.168.1.60", "port": 9102}
    assert device_id == "CAMERA_LINE_A"
    assert source == "request"


def test_resolve_pod_target_uses_registry_when_inline_missing(monkeypatch):
    monkeypatch.setattr(
        manager,
        "get_pod_device",
        lambda device_id: {"ip": "10.0.0.5", "port": 9105, "enabled": True},
    )

    target, device_id, source = manager.resolve_pod_target({"pod_device_id": "CAMERA_LINE_B"})

    assert target == {"ip": "10.0.0.5", "port": 9105}
    assert device_id == "CAMERA_LINE_B"
    assert source == "registry"
