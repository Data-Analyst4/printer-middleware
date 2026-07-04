# Printer Middleware v2 — Architecture

v2 lives in `v2/` and does **not** modify v1. It keeps the same core integration model:

```text
Web ERP  --HTTP JSON-->  Middleware  --TCP JSON-->  Printer
```

## v1 problems fixed in v2

| Area | v1 mistake | v2 fix |
|------|------------|--------|
| Persistence | Jobs in memory only; SQLite unused | SQLite `print_items` + `sync_results` wired to all APIs |
| Workers | Broken worker IDs, deadlocks, never started | One `PrinterConsumer` per printer, started at boot |
| Dashboard | Field names mismatched API | Dashboard reads v2 metric fields |
| TCP read | Single `recv(4096)` truncates responses | Multi-recv read window with idle timeout |
| Retries | Minimal / env-only | Exponential backoff + configurable attempts |
| Failures | No circuit breaker | Per-printer circuit breaker after N failures |
| Network | No ISP/LAN awareness | DNS cache, internet probe, pre-connect reachability check |
| Config | Non-atomic printer save | Atomic write via temp file + replace |
| Validation | Weak IP/port checks | `ipaddress` module + port 1–65535 |
| Queue | Documented but missing | `POST /print/data` async queue with rate limiting |
| Install | Multiple conflicting hostnames/scripts | Single `install.bat`, service `PrinterMiddlewareV2`, port 5002 |
| Security | Open by default | Optional `API_KEY` header |
| Logging | Unprotected concurrent writes | Thread-locked append logs |

## Module layout

```text
v2/
├── main.py                 # Waitress / Flask entry
├── app/
│   ├── api/routes.py       # HTTP endpoints
│   ├── core/               # config, bootstrap
│   ├── printer/            # protocol, TCP, connection, registry
│   ├── jobs/               # SQLite store + print service
│   ├── workers/            # rate-limited consumers
│   ├── network/            # DNS + internet monitor
│   └── resilience/         # retry + circuit breaker
├── config/                 # printers, site.env, app.env
├── dashboard/              # monitoring UI
└── scripts/                # install, watchdog
```

## Request flows

### Sync print (ERP compatible with v1)

```text
POST /print → validate → TCP send → parse response → SQLite sync_results → return
```

### Async data queue (continuous ERP production)

```text
POST /print/data → validate DATA fields → SQLite queued → 202 Accepted
PrinterConsumer → rate limit → TCP send → update item status
```

## Failure handling

1. **TCP connect fail** → retry with backoff → circuit opens after threshold
2. **Read timeout** → close socket, retry on fresh connection
3. **DNS change** → cached resolution refreshed every `DNS_CACHE_SECONDS`
4. **Internet down** → logged in `/health` network block; printer LAN may still work
5. **Queue item fail** → requeue up to `max_retries`, then mark failed
6. **Service crash** → NSSM auto-restart (`AppExit Default Restart`)
7. **Tunnel down** → `scripts/health-watchdog.ps1` restarts middleware + Cloudflared

## Windows deployment

- Default port **5002** (v1 can stay on 5000/5001)
- Service name **PrinterMiddlewareV2**
- Tunnel service **CloudflaredV2**
- Uses parent repo `nssm.exe` if not copied into v2

## Configuration

| File | Purpose |
|------|---------|
| `config/printers.json` | Printer IP, port, items/min, required fields |
| `config/site.env` | Install: port, tunnel hostname |
| `config/app.env` | Runtime: timeouts, retries, API key |

## ERP integration

| Endpoint | Use |
|----------|-----|
| `POST /print` | STAR setup, one-off sync commands |
| `POST /print/data` | High-volume DATA with queue |
| `GET /print/item/{id}` | Poll async item status |
| `GET /printers` | Queue depth + circuit state |
| `GET /metrics` | Dashboard counters |
