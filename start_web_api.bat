@echo off
setlocal

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

if /I "%~1"=="install-service" goto :install_service
if /I "%~1"=="uninstall-service" goto :uninstall_service
if /I "%~1"=="service-status" goto :service_status

if /I "%~1"=="help" goto :usage
if /I "%~1"=="/?" goto :usage

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

:install_service
shift
call "%ROOT_DIR%install_middleware_service.bat" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:uninstall_service
shift
call "%ROOT_DIR%uninstall_middleware_service.bat" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:service_status
sc query "PrinterMiddleware"
exit /b %ERRORLEVEL%

:usage
echo Usage:
echo   start_web_api.bat
echo   start_web_api.bat public
echo   start_web_api.bat install-service [port]
echo   start_web_api.bat uninstall-service
echo   start_web_api.bat service-status
echo.
echo Commands:
echo   install-service   Install as a Windows service that starts on boot
echo                     and restarts automatically if the app closes.
echo   uninstall-service Remove the Windows service.
echo   service-status    Show current Windows service status.
echo   public            Start the API now and launch the Cloudflare tunnel.
exit /b 0
