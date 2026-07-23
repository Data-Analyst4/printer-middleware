# Domino Printer Middleware

Separate middleware for **Domino Ax-Series** printers (Codenet 2).  
This is **not** the Rynan middleware — keep both apps and URLs independent.

| | Rynan middleware (existing) | Domino middleware (this app) |
|--|--|--|
| Folder | repo root / `v2/` | `domino/` |
| Default port | `5001` / `5002` | **`5003`** |
| Suggested public URL | `https://r10-print.k95foods.com` | **`https://domino-print.k95foods.com`** |
| Printer protocol | JSON `STAR` / `DATA` over TCP ~2030 | Codenet bytes over TCP **7000** |
| ERP printer config URL | Rynan URL | **Domino URL (different)** |

## Quick start (one-click on a site PC)

**Right-click** [`install.bat`](install.bat) → **Run as administrator**

That installs Python (if needed), `.venv`, and Windows service **`DominoPrinterMiddleware`** on port **5003**.

Full steps: [INSTALL_GUIDE.md](INSTALL_GUIDE.md)

### Manual start (dev)

```powershell
cd domino
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy config\printers.json.example config\printers.json
# edit config\printers.json with real Domino IP
python main.py
```

Health check: `http://127.0.0.1:5003/health`

## Configure Domino printer (TouchPanel)

Full checklist + ping/port/print tests: **[PRINTER_SETUP_AND_TEST.md](PRINTER_SETUP_AND_TEST.md)**

1. `Home > Setup > Printer network > Advanced`
2. Protocol Setting → **Codenet**
3. Protocol Mode → **TCP**
4. Protocol Enabled → **On**
5. TCP Port → **7000**
6. Response timing → **On Processed**
7. Restart printer
8. Store labels in printer (slots like `001`, `002`)

Quick connection test:

```powershell
curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"
```

## Example print request

```json
POST /print
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_stored_label",
  "label_slot": "001",
  "product_detect": "1"
}
```

Or map ERP product codes via `label_map` in `config/printers.json`:

```json
{
  "printer_id": "DOMINO_AX_1",
  "action": "print_product",
  "product_code": "SKU001"
}
```

## ERP changes

See **[ERP_INTEGRATION.md](ERP_INTEGRATION.md)** for exact changes needed in the ERP printer configuration and API calls.

## Local mock printer

```powershell
python scripts\mock_domino_printer.py --port 7000
```

Point `printers.json` IP to `127.0.0.1` while testing.
