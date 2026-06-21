@echo off
setlocal EnableExtensions

rem DELL / dev PC: stop cloudflared so production can use the printer tunnel.
rem Run as Administrator on the dev PC only.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

echo Stopping Cloudflared Windows service (if installed)...
sc.exe stop Cloudflared >nul 2>&1
sc.exe stop cloudflared >nul 2>&1

echo Stopping manual cloudflared processes...
taskkill /F /IM cloudflared.exe >nul 2>&1

timeout /t 2 >nul

echo.
echo Remaining cloudflared processes:
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul

echo.
echo Tunnel status (r10-print should have no CONNECTIONS):
if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
  "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" tunnel list
) else (
  where cloudflared >nul 2>&1 && cloudflared tunnel list
)

echo.
echo Done. Now run setup-production-tunnel.bat on the production PC (QCS).
pause
