@echo off
setlocal EnableExtensions

rem Installs the named cloudflared tunnel as a Windows service.
rem Run this script from an elevated Command Prompt / PowerShell
rem after you have created a named tunnel and configured %USERPROFILE%\.cloudflared\config.yml

set "CONFIG_PATH=%USERPROFILE%\.cloudflared\config.yml"

where cloudflared >nul 2>&1
if errorlevel 1 (
  echo [ERROR] cloudflared was not found in PATH.
  echo Install it first, for example: choco install cloudflared
  exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] This script must be run as Administrator.
  exit /b 1
)

if not exist "%CONFIG_PATH%" (
  echo [ERROR] Config not found at "%CONFIG_PATH%"
  echo Copy config\cloudflared\config.yml.example to that path and replace placeholders first.
  exit /b 1
)

echo Installing cloudflared Windows service using:
echo   %CONFIG_PATH%
echo.

cloudflared service install
if errorlevel 1 (
  echo [ERROR] cloudflared service install failed.
  exit /b 1
)

echo Starting cloudflared service...
sc start cloudflared

echo.
echo Service installed. Useful commands:
echo   sc query cloudflared
echo   sc stop cloudflared
echo   sc start cloudflared
echo.
echo Make sure your config file points to:
echo   service: http://127.0.0.1:5000

exit /b 0
