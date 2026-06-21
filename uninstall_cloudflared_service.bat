@echo off
setlocal EnableExtensions

rem Removes the cloudflared Windows service (registered as "Cloudflared").

set "SERVICE_NAME=Cloudflared"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

where cloudflared >nul 2>&1
if errorlevel 1 (
  echo [INFO] cloudflared is not installed. Nothing to remove.
  exit /b 0
)

echo Stopping and removing %SERVICE_NAME% Windows service...

sc.exe query %SERVICE_NAME% >nul 2>&1
if not errorlevel 1 (
  sc.exe stop %SERVICE_NAME% >nul 2>&1
  cloudflared service uninstall >nul 2>&1
  sc.exe delete %SERVICE_NAME% >nul 2>&1
)

echo.
echo %SERVICE_NAME% service removed.
echo Tunnel credentials in %%USERPROFILE%%\.cloudflared were left in place.

exit /b 0
