# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2026-08-26 — Bulk resume on timeout/NYES

### Added
- `PRINT_BULK_RESUME` (default on): after a timeout, NYES, or TCP drop, keep the same bulk job running
- Recovery path: **RQLP first** (STAR can reset printed count), leftover = plan − printed, then STAR, then send leftover
- Soft TCP retries the same DATA 2–3 times before RQLP recovery
- `GET /job/{id}` fields: `rqlp_printed`, `leftover`, `recoveries`
- While a bulk job is `queued`/`running`, ERP `STAR`/`DATA`/`RQLP` are rejected; poll `GET /job/{id}`; `STOP` still allowed

### Unchanged
- STOP, RSAL 011 (invalid version), and FULL still hard-stop the job (no leftover loop)
- Chunk size 30, no `camera_import` on bulk
- Set `PRINT_BULK_RESUME=false` to restore fail-fast drain

## [1.4.0] - 2026-08-20 — Bulk Mode A (pod_data + count)

### Added
- `POST /print` with `pod_data` + `count` queues the same POD × N and returns immediately (`execution_mode: batch`)
- Background drain sends DATA in chunks of 30 and waits for printer ACK
- `GET /job/{job_id}` reports `sent_to_printer` and batch status
- STOP cancels any in-progress bulk drain then stops the printer

## [1.3.0] - 2026-08-20 — Fast DATA send

### Changed
- DATA commands are written to the printer without waiting for a 5s ACK (`PRINTER_DATA_FIRE_AND_FORGET`)
- Camera import POST runs in a background thread so a dead camera cannot delay print

## [1.2.0] - 2026-07-11 — Immediate camera import

### Added
- **Immediate camera import** (default): on each `DATA` `/print` request with `camera_import.enabled`, middleware POSTs `{barcode, text}` to the camera URL **before** sending the command to the printer
- Camera text built from request POD fields (`POD1`, `POD2`, …)
- Response field `camera_import.erp_alert_recommended` plus `alert_reasons` (`empty_barcode`, `camera_http_failure`) so **ERP** can send WhatsApp alerts
- Env `CAMERA_IMPORT_FLOW=immediate|rqlp` (default `immediate`); legacy RQLP-after-print path retained for rollback

### Changed
- Default camera path no longer waits for printer ACK or RQLP
- Print `success` remains based on printer result only; camera failure does not fail the print job
- Camera URL: `CAMERA_IMPORT_BATCH_URL` env, overridable per request via `camera_import.url` (ERP UI)

### Unchanged (kept for later)
- Full RQLP confirm → camera flow still in code; set `CAMERA_IMPORT_FLOW=rqlp` to use it

## [1.1.0] - 2026-04-08

### Added
- Direct synchronous printer command flow for web app integrations
- Printer protocol helpers for command normalization and payload serialization
- Cloudflare tunnel scripts for HTTPS exposure of the local middleware
- Windows service install scripts for the middleware and cloudflared
- Protocol-focused test coverage for command extraction and payload formatting

### Changed
- Improved printer response parsing and structured error reporting
- Improved connection handling to capture transport and printer-level failures
- Updated release metadata for the 1.1.0 web integration milestone

## [1.0.0] - 2024-12-19

### Added
- **Enterprise-grade Architecture**: Complete rewrite for production readiness
- **Async API Layer**: Non-blocking job enqueuing with immediate response
- **Persistent Storage**: SQLite database for job persistence and printer management
- **Worker Processing System**: Multi-threaded workers per printer with connection pooling
- **Retry Engine**: Exponential backoff retry mechanism (5s → 30s → 2min → 10min)
- **Real-time Monitoring**: WebSocket support for live job and printer status updates
- **Production Server**: Waitress WSGI server for production deployment
- **Windows Service**: NSSM compatibility for auto-startup as Windows service
- **Comprehensive API**: RESTful endpoints for job management, printer monitoring, and metrics
- **Dashboard**: Web-based monitoring interface with real-time updates

### Changed
- Migrated from in-memory storage to persistent SQLite database
- Replaced synchronous processing with async job queuing
- Enhanced error handling with retry mechanisms
- Improved connection management with auto-reconnect

### Technical Details
- **Database**: SQLite with thread-safe operations and indexing
- **Concurrency**: Threading for worker pools and connection management
- **Communication**: TCP socket connections with command serialization
- **Monitoring**: WebSocket protocol for real-time dashboard updates
- **Deployment**: Production-ready with Windows service support

### Breaking Changes
- API endpoints now return job IDs immediately instead of waiting for completion
- Configuration moved to database-backed system
- Synchronous processing replaced with async queuing

---

## Version History

### Version Numbering
This project uses [Semantic Versioning](https://semver.org/):
- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

### Release Process
1. Update version in `app/version.py` and `pyproject.toml`
2. Update CHANGELOG.md with new version details
3. Create git tag: `git tag -a v1.1.0 -m "Version 1.1.0"`
4. Push tags: `git push origin --tags`
5. Create GitHub release with release notes
