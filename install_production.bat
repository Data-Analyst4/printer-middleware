@echo off
setlocal EnableExtensions

rem One-shot production installer:
rem - PrinterMiddleware Windows service on port 5001 (boot start + crash restart)
rem - Cloudflare tunnel r10-print -> r10-print.k95foods.com (boot start via cloudflared service)

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "PORT=5001"
set "TUNNEL_NAME=r10-print"
set "PUBLIC_HOST=r10-print.k95foods.com"

echo ============================================================
echo   Printer Middleware Production Installer
echo ============================================================
echo   App:      printer-middleware (NOT the HR attendance app)
echo   Port:     %PORT%
echo   Tunnel:   %TUNNEL_NAME%
echo   Hostname: %PUBLIC_HOST%
echo.
echo   If HR attendance middleware (v8-mw on port 8080) is also on
echo   this PC, its hostname will be kept in the same cloudflared
echo   service config automatically.
echo ============================================================
echo.

if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  echo [ERROR] Virtualenv not found. Run first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\activate
  echo   pip install -r requirements.txt
  exit /b 1
)

where cloudflared >nul 2>&1
if errorlevel 1 (
  echo [ERROR] cloudflared is not installed.
  echo Install it first, for example: choco install cloudflared
  exit /b 1
)

echo [1/4] Installing PrinterMiddleware service on port %PORT%...
call "%ROOT_DIR%install_middleware_service.bat" %PORT%
if errorlevel 1 (
  echo [ERROR] Middleware service install failed.
  exit /b 1
)

echo.
echo [2/4] Configuring Cloudflare tunnel '%TUNNEL_NAME%'...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\setup_r10_tunnel.ps1" -Port %PORT% -TunnelName %TUNNEL_NAME% -Hostname %PUBLIC_HOST%
if errorlevel 1 (
  echo [ERROR] Cloudflare tunnel setup failed.
  exit /b 1
)

echo.
echo [3/4] Installing cloudflared Windows service...
call "%ROOT_DIR%install_cloudflared_service.bat"
if errorlevel 1 (
  echo [ERROR] cloudflared service install failed.
  exit /b 1
)

echo.
echo [4/4] Running verification...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\verify_production.ps1" -Port %PORT% -Hostname %PUBLIC_HOST%
set "VERIFY_CODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%VERIFY_CODE%"=="0" (
  echo   Production install complete
) else (
  echo   Install finished with verification warnings
)
echo ============================================================
echo   Middleware service: PrinterMiddleware
echo   Tunnel service:     Cloudflared
echo   Local API:          http://127.0.0.1:%PORT%
echo   Public API:         https://%PUBLIC_HOST%
echo.
echo   After reboot, both services start automatically.
echo   If Python or cloudflared crashes, Windows restarts them.
echo.
echo   Useful commands (in PowerShell use sc.exe, not sc):
echo     sc.exe query PrinterMiddleware
echo     sc.exe query Cloudflared
echo     finish_cloudflared_service.bat
echo     powershell -ExecutionPolicy Bypass -File scripts\verify_production.ps1
echo     uninstall_production.bat
echo ============================================================

exit /b %VERIFY_CODE%
