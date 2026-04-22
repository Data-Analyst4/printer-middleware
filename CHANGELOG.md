# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-04-22

### Added
- `/test-print` endpoint family to emulate printer responses with `/print`-compatible payloads
- Scenario-driven printer simulator (`auto`, `rsal_011`, `sysn_007`, `nyes`, `timeout`, `transport_closed`, `mixed`)
- Structured log read endpoints: `/logs/app.json` and `/logs/app.jsonl`
- Printer config management endpoints: create/update/delete printer definitions

### Changed
- Standardized validation error shape for simulator request failures
- Improved compatibility fields in simulated command responses for protocol-level testing

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
3. Create git tag: `git tag -a v1.2.0 -m "Version 1.2.0"`
4. Push tags: `git push origin --tags`
5. Create GitHub release with release notes

### Downloading Specific Versions

#### Via Git Tags
```bash
# Download specific version
git clone --branch v1.2.0 https://github.com/yourusername/printer-middleware.git

# Or checkout specific version
git checkout tags/v1.1.0
```

#### Via GitHub Releases
Download ZIP files from [GitHub Releases](https://github.com/yourusername/printer-middleware/releases)

#### Via pip (if published)
```bash
pip install printer-middleware==1.2.0
```
