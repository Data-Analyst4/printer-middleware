@echo off
setlocal EnableExtensions
net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator privileges...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -Wait"
  exit /b %ERRORLEVEL%
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-cloudflared-r10e.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo CloudflaredR10E installed.
  echo Test: https://r10e-printer.k95foods.com/health
) else (
  echo Failed. See C:\printer-middleware-r10e\logs\install-cloudflared-r10e.log
)
pause
exit /b %RC%
