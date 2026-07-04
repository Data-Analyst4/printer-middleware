from app.services.camera_import_forwarder import (
    build_text_from_col_data,
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
