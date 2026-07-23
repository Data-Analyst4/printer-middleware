# Domino Printer Middleware — One-Click Install (Site PC)

Same idea as the Rynan `install.bat`, but for the **Domino** app only.  
Does **not** replace or stop the Rynan middleware.

| | Rynan | Domino |
|--|-------|--------|
| Folder | `C:\printer-middleware` | `C:\printer-middleware\domino` (or copy of `domino\`) |
| Installer | `install.bat` | **`domino\install.bat`** |
| Service | `PrinterMiddleware` | **`DominoPrinterMiddleware`** |
| Port | `5001` | **`5003`** |
| Public URL (optional) | `r10-print.k95foods.com` | `domino-print.k95foods.com` |

---

## 1. What `install.bat` does

1. Self-elevate to Administrator  
2. Install Python 3.11 via winget if missing  
3. Create `.venv` + `pip install -r requirements.txt`  
4. Create `config\printers.json` / `site.env` from examples if missing  
5. Download NSSM if needed  
6. Install **DominoPrinterMiddleware** Windows service (boot start + crash restart)  
7. Verify `http://127.0.0.1:5003/health`  

Optional: `install.bat -WithCloudflare` for a separate public hostname.

---

## 2. Get the app onto the PC

### Option A — Full repo ZIP (recommended)

1. Download: https://github.com/Data-Analyst4/printer-middleware/archive/refs/heads/develop.zip  
2. Extract to `C:\printer-middleware`  
3. Open `C:\printer-middleware\domino`

### Option B — Already have the repo

```cmd
cd /d C:\printer-middleware\domino
```

---

## 3. Configure Domino IP

```cmd
cd /d C:\printer-middleware\domino
copy config\printers.json.example config\printers.json
notepad config\printers.json
```

Set real Domino LAN IP and port **7000**:

```json
{
  "DOMINO_AX_1": {
    "ip": "192.168.1.50",
    "port": 7000,
    "protocol": "domino_ax_codenet",
    "default_label_slot": "001",
    "enabled": true
  }
}
```

On the Domino TouchPanel: **Codenet + TCP + port 7000 + Enabled**, then restart printer.

---

## 4. One-click install

**Right-click** `install.bat` → **Run as administrator**

Or:

```cmd
cd /d C:\printer-middleware\domino
install.bat
```

When finished:

- Local health: http://127.0.0.1:5003/health  
- Service: `sc query DominoPrinterMiddleware`

---

## 5. Test from the same PC (or laptop on LAN)

```cmd
curl -X POST http://127.0.0.1:5003/test/ping -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\"}"

curl -X POST http://127.0.0.1:5003/test/port -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"

curl -X POST http://127.0.0.1:5003/test/connection -H "Content-Type: application/json" -d "{\"ip\":\"192.168.1.50\",\"port\":7000}"

curl -X POST http://127.0.0.1:5003/print -H "Content-Type: application/json" -d "{\"printer_id\":\"DOMINO_AX_1\",\"action\":\"print_stored_label\",\"label_slot\":\"001\",\"product_detect\":\"1\"}"
```

From another laptop on the same network, use the site PC LAN IP instead of `127.0.0.1` (e.g. `http://192.168.1.20:5003/...`).

More detail: [PRINTER_SETUP_AND_TEST.md](PRINTER_SETUP_AND_TEST.md)

---

## 6. Uninstall

```cmd
cd /d C:\printer-middleware\domino
uninstall.bat
```

---

## 7. Optional public URL

```cmd
install.bat -WithCloudflare
```

Uses `config\site.env` (`TUNNEL_NAME`, `PUBLIC_HOSTNAME`).  
Use a **different** hostname than Rynan’s `r10-print.k95foods.com`.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Health fails | `logs\service-error.log`; `sc query DominoPrinterMiddleware` |
| Port 5003 in use | Change `PORT=` in `config\site.env`, rerun `install.bat` |
| Ping/port fail to Domino | Same LAN; Domino Codenet TCP 7000 enabled |
| Python not found | Install Python 3.11, check “Add to PATH”; turn off Store python aliases |
| Rynan still works? | Yes — different folder, port, and service name |
