@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo [ERROR] Virtualenv Python not found at "%PYTHON_EXE%"
  echo Create the venv first, then rerun this script.
  exit /b 1
)

if "%PORT%"=="" set "PORT=5000"
if "%HOST%"=="" set "HOST=0.0.0.0"
if "%CORS_ORIGINS%"=="" set "CORS_ORIGINS=*"
if "%PRINTER_READ_TIMEOUT%"=="" set "PRINTER_READ_TIMEOUT=5"
if "%PRINTER_FIRE_AND_FORGET%"=="" set "PRINTER_FIRE_AND_FORGET=false"

echo Starting printer middleware for web app access...
echo.
echo   Host: %HOST%
echo   Port: %PORT%
echo   CORS_ORIGINS: %CORS_ORIGINS%
echo   Local URL: http://127.0.0.1:%PORT%
echo   LAN URL:   http://192.168.29.124:%PORT%
echo.

if /I "%~1"=="public" (
  echo Public mode requested. Starting Cloudflare tunnel in a separate window...
  start "printer-middleware-tunnel" powershell -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\run_tunnel.ps1"
  echo.
  echo If tunnel preflight passes, your web app can use the public hostname from your Cloudflare config.
  echo.
)

"%PYTHON_EXE%" main.py --host %HOST% --port %PORT%
exit /b %ERRORLEVEL%
