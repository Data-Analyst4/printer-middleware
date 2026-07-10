from app.services.camera_import_forwarder import (
    build_text_from_col_data,
    forward_camera_import_immediate,
    get_camera_import_flow,
    parse_rqlp_result,
    resolve_camera_target,
    post_camera_import,
)


def test_build_text_from_col_data_orders_cols():
    assert build_text_from_col_data({"col2": "B", "col1": "A", "col3": "C"}) == "ABC"


def test_parse_rqlp_result_success():
    result = parse_rqlp_result({
        "ok": True,
        "response_command": "RSFP",
        "response": {
            "command": "RSFP",
            "value": "2/2",
            "data": {"col1": "95.00", "col2": "BATCH"},
        },
    })
    assert result["success"] is True
    assert result["printed_count"] == 2
    assert result["col_data"]["col1"] == "95.00"


def test_parse_rqlp_result_zero_printed_fails():
    result = parse_rqlp_result({
        "ok": True,
        "response": {"command": "RSFP", "value": "0/0", "data": {}},
    })
    assert result["success"] is False


def test_parse_rqlp_result_transport_fail():
    result = parse_rqlp_result({"ok": False, "reason": "timeout"})
    assert result["success"] is False


def test_resolve_camera_target_allows_empty_barcode():
    url, barcode = resolve_camera_target({
        "camera_import": {
            "enabled": True,
            "barcode": "",
            "url": "http://192.168.0.68:5001/api/import_batch",
        }
    })
    assert url == "http://192.168.0.68:5001/api/import_batch"
    assert barcode == ""


def test_resolve_camera_target_disabled():
    url, barcode = resolve_camera_target({"camera_import": {"enabled": False, "barcode": "1"}})
    assert url is None


def test_post_camera_import_handles_connection_error():
    result = post_camera_import(
        "http://127.0.0.1:1/api/import_batch",
        "8906164010577",
        "testdata",
    )
    assert result["ok"] is False
    assert result["reason"]


def test_get_camera_import_flow_default_immediate():
    assert get_camera_import_flow() in ("immediate", "rqlp")


def test_forward_immediate_empty_barcode_alerts_erp(monkeypatch):
    posted = {}

    def fake_post(url, barcode, text):
        posted["url"] = url
        posted["barcode"] = barcode
        posted["text"] = text
        return {"ok": True, "url": url, "barcode": barcode, "text_length": len(text), "reason": "OK"}

    monkeypatch.setattr(
        "app.services.camera_import_forwarder.post_camera_import",
        fake_post,
    )

    meta = forward_camera_import_immediate(
        "job-1",
        {
            "camera_import": {
                "enabled": True,
                "barcode": "",
                "url": "http://camera.test/api/import_batch",
            }
        },
        {"POD1": "A", "POD2": "B"},
        printer_id="P1",
    )
    assert meta["flow"] == "immediate"
    assert meta["attempted"] is True
    assert meta["missing_barcode"] is True
    assert meta["erp_alert_recommended"] is True
    assert "empty_barcode" in meta["alert_reasons"]
    assert meta["camera_ok"] is True
    assert posted["text"] == "AB"
    assert posted["barcode"] == ""


def test_forward_immediate_http_failure_alerts_erp(monkeypatch):
    def fake_post(url, barcode, text):
        return {
            "ok": False,
            "url": url,
            "barcode": barcode,
            "text_length": len(text),
            "reason": "HTTP 500: error",
            "status_code": 500,
        }

    monkeypatch.setattr(
        "app.services.camera_import_forwarder.post_camera_import",
        fake_post,
    )

    meta = forward_camera_import_immediate(
        "job-2",
        {
            "camera_import": {
                "enabled": True,
                "barcode": "8906164010577",
                "url": "http://camera.test/api/import_batch",
            }
        },
        {"POD1": "X"},
        printer_id="P1",
    )
    assert meta["camera_ok"] is False
    assert meta["erp_alert_recommended"] is True
    assert "camera_http_failure" in meta["alert_reasons"]
    assert "empty_barcode" not in meta["alert_reasons"]


def test_forward_immediate_success_no_alert(monkeypatch):
    monkeypatch.setattr(
        "app.services.camera_import_forwarder.post_camera_import",
        lambda url, barcode, text: {
            "ok": True,
            "url": url,
            "barcode": barcode,
            "text_length": len(text),
            "reason": "OK",
        },
    )
    meta = forward_camera_import_immediate(
        "job-3",
        {
            "camera_import": {
                "enabled": True,
                "barcode": "8906164010577",
                "url": "http://camera.test/api/import_batch",
            }
        },
        {"POD1": "OK"},
    )
    assert meta["camera_ok"] is True
    assert meta["erp_alert_recommended"] is False
    assert meta["alert_reasons"] == []
    assert meta["status"] == "sent"
