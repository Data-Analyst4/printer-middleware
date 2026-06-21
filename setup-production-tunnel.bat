@echo off
setlocal EnableExtensions

rem Production PC only: new tunnel r10-printer -> r10-printer.k95foods.com -> port 5001
rem Run once as Administrator on the site PC (not on dev PC).

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ============================================================
echo   Production Tunnel - r10-printer.k95foods.com
echo ============================================================
echo.
echo   Prerequisites on THIS PC:
echo     - Printer middleware healthy at http://127.0.0.1:5001/health
echo     - cloudflared installed (winget install Cloudflare.cloudflared)
echo     - config/printers.json edited with real printer IPs
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\setup-production-tunnel.ps1" -TunnelName r10-printer -Hostname r10-printer.k95foods.com -Port 5001
exit /b %ERRORLEVEL%
