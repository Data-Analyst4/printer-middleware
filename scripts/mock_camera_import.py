#!/usr/bin/env python3
"""
Local stand-in for the camera OCR import_batch API.

Use when no real camera is running — prints every POST body so you can verify
ERP → middleware → camera payload shape.

  python scripts/mock_camera_import.py
  # listens on http://127.0.0.1:5001/api/import_batch

Point App Setting CAMERA_IMPORT_BATCH_URL (or middleware env) at:
  http://127.0.0.1:5001/api/import_batch
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HOST = "0.0.0.0"
PORT = 5001
PATH = "/api/import_batch"
COUNT = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now(timezone.utc).isoformat()}] {fmt % args}")

    def do_POST(self):
        global COUNT
        if self.path.rstrip("/") != PATH.rstrip("/"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not found"}')
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {"_raw": raw.decode("utf-8", errors="replace")}

        COUNT += 1
        barcode = body.get("barcode", "")
        text = body.get("text", "")
        print("=" * 60)
        print(f"#{COUNT} import_batch received")
        print(f"  barcode: {barcode!r}{'  << EMPTY' if not barcode else ''}")
        print(f"  text:    {text!r}")
        print(f"  full:    {json.dumps(body, ensure_ascii=False)}")
        print("=" * 60)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "received": COUNT}).encode("utf-8"))

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"service": "mock-camera-import", "path": PATH, "count": COUNT}).encode("utf-8")
        )


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Mock camera listening on http://{HOST}:{PORT}{PATH}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopped. Total POSTs received: {COUNT}")


if __name__ == "__main__":
    main()
