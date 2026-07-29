# Printer Middleware — Linux (Ubuntu) install

One-click install for **Ubuntu/Debian**. Sets up all three apps as systemd services that start on boot and restart on crash.

| App | Folder | Port | systemd service |
|-----|--------|------|-----------------|
| v1 (Rynan) | repo root | **5001** | `printer-middleware` |
| v2 | `v2/` | **5002** | `printer-middleware-v2` |
| Domino | `domino/` | **5003** | `domino-printer-middleware` |

## Install (one command)

```bash
cd /path/to/printer-middleware
chmod +x install-linux.sh uninstall-linux.sh
./install-linux.sh
```

You will be prompted for `sudo`. The script installs Python packages, creates virtualenvs, copies config examples if missing, and starts the services.

### Options

```bash
./install-linux.sh --skip-cloudflare   # skip cloudflared download
./install-linux.sh --v1-only           # only v1
./install-linux.sh --v2-only           # only v2
./install-linux.sh --domino-only       # only Domino
./install-linux.sh --no-start          # install units but do not start yet
```

### After install

1. Edit printer IPs:
   - `config/printers.json`
   - `v2/config/printers.json`
   - `domino/config/printers.json`
2. Check health:
   ```bash
   curl http://127.0.0.1:5001/health
   curl http://127.0.0.1:5002/health
   curl http://127.0.0.1:5003/health
   ```
3. Useful commands:
   ```bash
   sudo systemctl status printer-middleware
   sudo journalctl -u printer-middleware-v2 -f
   sudo systemctl restart domino-printer-middleware
   ```

### Uninstall services

```bash
./uninstall-linux.sh
```

App files and `.venv` folders stay on disk; delete the repo folder if you want a full wipe.

### Optional Cloudflare tunnel

`install-linux.sh` installs `cloudflared` when possible. To expose a public HTTPS URL:

```bash
cloudflared tunnel login
cloudflared tunnel create r10-printer
cloudflared tunnel route dns r10-printer your-hostname.example.com
# edit ~/.cloudflared/config.yml then:
sudo cloudflared service install
```
