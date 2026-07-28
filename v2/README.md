# Printer Middleware v2

Enterprise printer bridge for Web ERP integration. **v2 is a separate app** — v1 in the repo root is untouched.

## What's better in v2

- **Same printer protocol** — JSON commands over TCP (`STAR`, `DATA`, etc.)
- **v1-compatible** `POST /print` (sync)
- **New** `POST /print/data` — validate, queue, rate-limit, persist
- **SQLite storage** — survives restarts
- **Circuit breaker + retries** — TCP/ISP failure resilience
- **Network monitor** — DNS cache, internet probe
- **Dashboard** matches API
- **One-click Windows install** — Python, venv, NSSM service, Cloudflare tunnel

Default port: **5002** (does not conflict with v1).

---

## Quick start (development)

```powershell
cd v2
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy config\printers.json.example config\printers.json
python main.py --debug
```

Open http://127.0.0.1:5002

### With virtual printer

Terminal 1 (repo root):

```powershell
python scripts\mock_printer.py --port 9100 --config config\mock_printer.json
```

Terminal 2:

```powershell
cd v2
python main.py --debug
```

---

## ERP API

### Sync print (same as v1)

```http
POST /print
Content-Type: application/json

{
  "printer_id": "SIM1",
  "printer": { "ip": "127.0.0.1", "port": 9100 },
  "command": {
    "command": "STAR",
    "templatename": "DEMO",
    "startpage": "1",
    "endpage": "1",
    "loop": "false"
  }
}
```

### Async DATA queue

```http
POST /print/data

{
  "printer_id": "SIM1",
  "erp_ref": "ORDER-1001",
  "data": { "POD1": "12345", "POD2": "67890" },
  "priority": "normal"
}
```

Response:

```json
{
  "success": true,
  "item_id": "...",
  "status": "queued",
  "queue_position": 3,
  "estimated_print_at": "..."
}
```

---

## Production install (Windows 10/11)

1. Copy `config\site.env.example` → `config\site.env` and edit hostname/port
2. Right-click **`install.bat`** → **Run as administrator**

Installs:

- Python (via winget if missing)
- Virtual environment + pip packages
- Windows service `PrinterMiddlewareV2` (auto-start, auto-restart)
- Cloudflare tunnel service `CloudflaredV2` (optional)

Verify:

```powershell
Invoke-RestMethod http://127.0.0.1:5002/health
```

Uninstall: run `uninstall.bat` as admin.

### Health watchdog (optional)

Schedule `scripts\health-watchdog.ps1` every 5 minutes in Task Scheduler to restart middleware/tunnel after ISP or power failures.

---

## Configuration

`config/printers.json`:

```json
{
  "P1": {
    "ip": "192.168.29.110",
    "port": 2030,
    "items_per_minute": 20,
    "required_data_fields": ["POD1", "POD2"],
    "max_queue_size": 500
  }
}
```

Environment (`config/app.env` or NSSM service env):

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5002 | HTTP port |
| `PRINTER_SEND_RETRIES` | 3 | TCP retry attempts |
| `PRINTER_READ_TIMEOUT` | 5 | Socket read timeout |
| `DEFAULT_ITEMS_PER_MINUTE` | 20 | Queue consumer rate |
| `API_KEY` | (none) | Optional `X-API-Key` for ERP/machine clients |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | (none) | Enable username/password login for the dashboard |
| `SECRET_KEY` | derived | Flask session secret (set in production) |
| `PRINTER_ALLOWLIST_ONLY` | false | Reject unknown printer targets |

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full design and v1 issue list.

---

## Tests

```powershell
cd v2
.\.venv\Scripts\activate
python -m pytest tests/ -v
```
