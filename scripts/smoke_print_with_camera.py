#!/usr/bin/env python3
"""
Smoke-test middleware /print with camera_import — no ERP UI required.

Prerequisites:
  1. Middleware running (e.g. python main.py / start.bat)
  2. Mock printer OR real printer IP:port in LblPrinterConfig style
  3. Optional: python scripts/mock_camera_import.py on :5001

Usage:
  python scripts/smoke_print_with_camera.py
  python scripts/smoke_print_with_camera.py --middleware http://127.0.0.1:8000 --printer-ip 127.0.0.1 --printer-port 9100
"""

from __future__ import annotations

import argparse
import json
import urllib.request


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--middleware", default="http://127.0.0.1:8000")
    p.add_argument("--printer-id", default="SMOKE-P1")
    p.add_argument("--printer-ip", default="127.0.0.1")
    p.add_argument("--printer-port", type=int, default=9100)
    p.add_argument("--template", default="DEMO")
    p.add_argument("--camera-url", default="http://127.0.0.1:5001/api/import_batch")
    p.add_argument("--barcode", default="8906164010577")
    args = p.parse_args()

    base = args.middleware.rstrip("/")
    printer = {"ip": args.printer_ip, "port": args.printer_port}

    print("1) STOP")
    print(json.dumps(post_json(f"{base}/print", {
        "printer_id": args.printer_id,
        "printer": printer,
        "command": {"command": "STOP"},
    }), indent=2))

    print("2) STAR")
    print(json.dumps(post_json(f"{base}/print", {
        "printer_id": args.printer_id,
        "printer": printer,
        "command": {
            "command": "STAR",
            "templatename": args.template,
            "startpage": "1",
            "endpage": "1",
            "loop": "true",
        },
    }), indent=2))

    pod = {
        "POD1": "95.00",
        "POD2": "USP0.29",
        "POD4": "01CR46104",
        "POD5": "23/03/2026",
        "POD6": "22/03/2027",
        "POD11": "0.29",
    }
    print("3) DATA + camera_import")
    result = post_json(f"{base}/print", {
        "printer_id": args.printer_id,
        "printer": printer,
        "command": {"command": "DATA", "data": pod},
        "camera_import": {
            "enabled": True,
            "barcode": args.barcode,
            "url": args.camera_url,
        },
    })
    print(json.dumps(result, indent=2))
    print("\nExpected camera text:", "".join(pod[k] for k in sorted(pod, key=lambda x: int(x[3:]))))
    if result.get("camera_import"):
        print("Middleware camera_import meta:", result["camera_import"])
    else:
        print("WARNING: no camera_import in response — check middleware branch / logs")


if __name__ == "__main__":
    main()
