@echo off
setlocal
cd /d "%~dp0"

echo Starting virtual printer (20 items/min, template DEMO)...
python scripts\mock_printer.py --host 127.0.0.1 --port 9100 --config config\mock_printer.json
