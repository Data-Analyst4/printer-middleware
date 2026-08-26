import unittest

from app.services.batch_queue import (
    _is_hard_fail,
    _is_nyes,
    _is_soft_tcp,
    is_bulk_payload,
    validate_batch_request,
)
from app.services.camera_import_forwarder import parse_rqlp_result


class BatchValidationTests(unittest.TestCase):
    def test_single_command_is_not_bulk(self):
        self.assertFalse(
            is_bulk_payload({"command": {"command": "DATA", "data": {"POD1": "1"}}})
        )

    def test_pod_data_count_ok(self):
        ok, err = validate_batch_request({
            "printer_id": "P1",
            "printer": {"ip": "192.168.1.120", "port": 2030},
            "pod_data": {"POD1": "95.00"},
            "count": 30,
        })
        self.assertTrue(ok, err)

    def test_reject_command_plus_pod_data(self):
        ok, err = validate_batch_request({
            "printer_id": "P1",
            "printer": {"ip": "192.168.1.120", "port": 2030},
            "command": {"command": "DATA"},
            "pod_data": {"POD1": "1"},
            "count": 2,
        })
        self.assertFalse(ok)
        self.assertIn("Cannot send command", err)

    def test_reject_items_with_pod_data(self):
        ok, err = validate_batch_request({
            "printer_id": "P1",
            "printer": {"ip": "192.168.1.120", "port": 2030},
            "pod_data": {"POD1": "1"},
            "items": [{"POD1": "1"}],
            "count": 1,
        })
        self.assertFalse(ok)

    def test_reject_count_too_large(self):
        ok, err = validate_batch_request({
            "printer_id": "P1",
            "printer": {"ip": "192.168.1.120", "port": 2030},
            "pod_data": {"POD1": "1"},
            "count": 100001,
        })
        self.assertFalse(ok)
        self.assertIn("exceeds maximum", err)

    def test_hard_fail_rsal_011(self):
        self.assertTrue(_is_hard_fail({
            "ok": False,
            "response_command": "RSAL",
            "protocol_error_code": "011",
            "reason": "Printer alarm RSAL code 011",
        }))

    def test_nyes_is_not_hard_fail(self):
        nyes = {"ok": False, "response_command": "NYES", "reason": "Printer returned NYES"}
        self.assertTrue(_is_nyes(nyes))
        self.assertFalse(_is_hard_fail(nyes))

    def test_soft_tcp_timeout(self):
        self.assertTrue(_is_soft_tcp({
            "ok": False,
            "error_type": "read_timeout",
            "reason": "Printer read timeout after 5.0s",
        }))
        self.assertTrue(_is_soft_tcp({
            "ok": False,
            "reason": "[WinError 10054] An existing connection was forcibly closed",
        }))

    def test_rqlp_allow_zero(self):
        result = {
            "ok": True,
            "response_command": "RSFP",
            "response": {"command": "RSFP", "value": "0/3010"},
        }
        denied = parse_rqlp_result(result)
        self.assertFalse(denied["success"])
        allowed = parse_rqlp_result(result, allow_zero=True)
        self.assertTrue(allowed["success"])
        self.assertEqual(allowed["printed_count"], 0)


if __name__ == "__main__":
    unittest.main()
