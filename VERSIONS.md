# Versions in this repo

R10E **root is now 1.4.1** (bulk Mode A + resume on timeout/NYES).

| What | Where | Version | Port | URL |
|------|--------|---------|------|-----|
| **R10E live app** | repo root | **1.4.1** | 5004 | https://r10e-printer.k95foods.com |
| Frozen 1.3.0 (before bulk) | `releases/v1.3.0-r10e/` | 1.3.0 | — | rollback |
| Copy of bulk tree | `bulk/` | 1.4.0 | 5005 | optional / test-printer |
| Older freeze | `releases/v1.2.0/` | 1.2.0 | — | rollback |

## Rollback to 1.3.0

Copy from `releases\v1.3.0-r10e\` over repo root `app\` + `main.py`, restart `PrinterMiddlewareR10E`.
