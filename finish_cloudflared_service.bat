@echo off
setlocal EnableExtensions

rem Finishes cloudflared service setup if install succeeded but recovery/start failed.
rem Common when sc commands were run inside PowerShell (sc = Set-Content alias).

set "SERVICE_NAME=Cloudflared"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

sc.exe query %SERVICE_NAME% >nul 2>&1
if errorlevel 1 (
  echo [ERROR] %SERVICE_NAME% service is not installed.
  echo Run install_cloudflared_service.bat first.
  exit /b 1
)

echo Applying recovery policy and starting %SERVICE_NAME%...
sc.exe failure %SERVICE_NAME% reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul
sc.exe failureflag %SERVICE_NAME% 1 >nul
sc.exe start %SERVICE_NAME%

timeout /t 3 >nul
sc.exe query %SERVICE_NAME%

exit /b 0
