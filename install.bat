@echo off
setlocal
set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo.
echo ============================================================
echo   Printer Middleware - One-Click Install
echo ============================================================
echo.
echo   This will:
echo     1. Install Python / cloudflared if missing
echo     2. Create venv and install packages
echo     3. Install PrinterMiddleware service (auto-start + restart)
echo     4. Create Cloudflare tunnel for r10-print.k95foods.com
echo     5. Install cloudflared service (auto-start on boot)
echo.
echo   First run may open a browser for Cloudflare login (one-time).
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\setup-all.ps1"
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
  echo [ERROR] Install failed with exit code %RC%.
) else (
  echo [OK] Install finished.
)
echo.
pause
exit /b %RC%
