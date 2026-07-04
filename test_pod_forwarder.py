from app.services.pod_forwarder import build_pod_string, has_pod_fields, should_forward_pod


def test_build_pod_string_concatenates_pod_values_in_order():
    data = {
        "POD3": "C",
        "POD1": "A",
        "POD2": "B",
    }

    assert build_pod_string(data) == "ABC"


def test_build_pod_string_ignores_non_pod_fields():
    data = {
        "POD1": "1122",
        "POD2": "2233",
        "other": "ignored",
    }

    assert build_pod_string(data) == "11222233"


def test_should_forward_pod_only_for_data_with_pod_fields():
    assert should_forward_pod({"command": "STAR", "templatename": "DEMO"}) is False
    assert should_forward_pod({"command": "DATA", "data": {"field": "x"}}) is False
    assert should_forward_pod({"command": "DATA", "data": {"POD1": "1"}}) is True


def test_has_pod_fields():
    assert has_pod_fields({"POD1": "1"}) is True
    assert has_pod_fields({"batch": "1"}) is False
    assert has_pod_fields(None) is False
