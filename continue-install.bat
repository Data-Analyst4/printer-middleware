@echo off
setlocal EnableExtensions

rem Finishes Cloudflare tunnel + Cloudflared service after middleware is already installed.
rem Use when install.bat stopped at health check but PrinterMiddleware is running.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ============================================================
echo   Continue Install - Tunnel + Cloudflared Service
echo ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\continue-install.ps1"
exit /b %ERRORLEVEL%
