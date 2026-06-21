@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

echo Removing PrinterMiddleware service...
call "%ROOT_DIR%uninstall_middleware_service.bat"

echo.
echo Stopping and removing cloudflared service...
sc stop cloudflared >nul 2>&1
cloudflared service uninstall >nul 2>&1
sc delete cloudflared >nul 2>&1

echo.
echo Done. Project files were left in place.
pause
exit /b 0
