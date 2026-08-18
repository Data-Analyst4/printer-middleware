@echo off
setlocal EnableExtensions

rem Install second middleware instance for R10E (P1) on port 5004.
rem Target folder: C:\printer-middleware-r10e
rem Public URL:    https://r10e-printer.k95foods.com
rem Does not modify existing PrinterMiddleware / Domino installs.

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -Wait"
  exit /b %ERRORLEVEL%
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ============================================================
echo   R10E Printer Middleware Installer
echo ============================================================
echo   Target:  C:\printer-middleware-r10e
echo   Port:    5004
echo   Domain:  r10e-printer.k95foods.com
echo   Printer: P1 @ 192.168.1.120:2030
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\install-r10e-full.ps1" ^
  -TargetDir "C:\printer-middleware-r10e" ^
  -SourceDir "%ROOT_DIR%" ^
  -Hostname "r10e-printer.k95foods.com" ^
  -TunnelName "r10e-printer" ^
  -Port 5004

set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Install failed with exit code %RC%.
  echo See C:\printer-middleware-r10e\logs\install-r10e-full.log if present.
  pause
  exit /b %RC%
)

echo.
echo Done. Edit C:\printer-middleware-r10e\config\site.env then restart-middleware.bat
pause
exit /b 0
