# ERP bulk v1 contract (R10E)

Base URL:
- LAN: http://127.0.0.1:5004
- Public: https://r10e-printer.k95foods.com

POST /print with pod_data + count (no command, no camera_import).
Success: HTTP 200, execution_mode=batch, status=queued, job_id.
Progress: GET /job/{job_id} → sent_to_printer, rqlp_printed, leftover, recoveries, status queued|running|completed|stopped|failed

While status is queued/running: poll GET /job/{id} only. Do not send RQLP, DATA, or STAR (middleware rejects them). STOP is allowed.

v1.4.1: timeout / NYES / TCP drop keeps the same job running. Middleware RQLP first, leftover = plan − printed, STAR, then leftover DATA. STOP / RSAL 011 / FULL still hard-stop.

Resume after STOP is a new bulk with count = plan − physical RQLP printed.
