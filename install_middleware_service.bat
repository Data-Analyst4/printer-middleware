@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Installs the printer middleware as a Windows service using NSSM.
rem This is the preferred boot/restart mechanism for a web API:
rem - starts at Windows boot
rem - runs without user login
rem - restarts automatically after crashes

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"
set "WORK_DIR=%ROOT_DIR:~0,-1%"

set "SERVICE_NAME=PrinterMiddleware"
set "DISPLAY_NAME=Printer Middleware"
set "PYTHON_EXE=%WORK_DIR%\.venv\Scripts\python.exe"
set "APP_SCRIPT=%WORK_DIR%\main.py"
set "APP_LOG=%WORK_DIR%\logs\service-output.log"
set "APP_ERR=%WORK_DIR%\logs\service-error.log"
set "LOCAL_NSSM=%WORK_DIR%\nssm.exe"
set "NSSM_EXE=%LOCAL_NSSM%"

if "%~1"=="" (
  if "%PORT%"=="" set "PORT=5000"
) else (
  set "PORT=%~1"
)

echo %PORT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 (
  echo [ERROR] Invalid port "%PORT%".
  echo         Use a numeric port such as 5000 or 5001.
  exit /b 1
)

if "%HOST%"=="" set "HOST=0.0.0.0"
if "%CORS_ORIGINS%"=="" set "CORS_ORIGINS=*"
if "%PRINTER_READ_TIMEOUT%"=="" set "PRINTER_READ_TIMEOUT=5"
if "%PRINTER_FIRE_AND_FORGET%"=="" set "PRINTER_FIRE_AND_FORGET=false"

echo ============================================================
echo   Printer Middleware Service Installer
echo ============================================================
echo.

if not exist "%PYTHON_EXE%" (
  echo [ERROR] Virtualenv Python not found at "%PYTHON_EXE%"
  echo Create the venv and install dependencies first:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\activate
  echo   pip install -r requirements.txt
  exit /b 1
)

if not exist "%APP_SCRIPT%" (
  echo [ERROR] main.py not found at "%APP_SCRIPT%"
  exit /b 1
)

if not exist "%WORK_DIR%\logs" mkdir "%WORK_DIR%\logs"

if exist "%LOCAL_NSSM%" goto have_nssm

where nssm >nul 2>&1
if not errorlevel 1 (
  set "NSSM_EXE=nssm"
  goto have_nssm
)

echo [INFO] NSSM not found locally or in PATH. Downloading a local copy...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "$zip=Join-Path $env:TEMP 'nssm-2.24.zip';" ^
  "$dir=Join-Path $env:TEMP 'nssm-2.24';" ^
  "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile $zip;" ^
  "if (Test-Path $dir) { Remove-Item $dir -Recurse -Force };" ^
  "Expand-Archive -Path $zip -DestinationPath $dir -Force;" ^
  "Copy-Item (Join-Path $dir 'nssm-2.24\\win64\\nssm.exe') '%LOCAL_NSSM%' -Force"

if not exist "%LOCAL_NSSM%" (
  echo [ERROR] Unable to acquire nssm.exe automatically.
  echo Install NSSM manually or place nssm.exe in this folder.
  exit /b 1
)

set "NSSM_EXE=%LOCAL_NSSM%"

:have_nssm
echo [1/6] Validating port %PORT%...
set "PORT_IN_USE_PID="
for /f %%i in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-NetTCPConnection -State Listen -LocalPort %PORT% -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess; if($c){Write-Output $c}"') do set "PORT_IN_USE_PID=%%i"
if defined PORT_IN_USE_PID (
  echo [WARNING] Port %PORT% is already in use by PID !PORT_IN_USE_PID!.
  echo           If that is not this middleware, choose another port:
  echo           install_middleware_service.bat 5001
  echo.
)

echo [2/6] Removing any previous "%SERVICE_NAME%" service...
"%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm >nul 2>&1
sc delete "%SERVICE_NAME%" >nul 2>&1

echo [3/6] Installing "%SERVICE_NAME%"...
"%NSSM_EXE%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "%APP_SCRIPT%" --host %HOST% --port %PORT%
if errorlevel 1 (
  echo [ERROR] Failed to install the Windows service.
  exit /b 1
)

echo [4/6] Configuring service settings...
"%NSSM_EXE%" set "%SERVICE_NAME%" DisplayName "%DISPLAY_NAME%"
"%NSSM_EXE%" set "%SERVICE_NAME%" Description "Printer middleware API for remote web apps and printer communication"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%WORK_DIR%"
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%APP_LOG%"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%APP_ERR%"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateBytes 10485760
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 5000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 1500
"%NSSM_EXE%" set "%SERVICE_NAME%" AppEnvironmentExtra "HOST=%HOST%" "PORT=%PORT%" "CORS_ORIGINS=%CORS_ORIGINS%" "PRINTER_READ_TIMEOUT=%PRINTER_READ_TIMEOUT%" "PRINTER_FIRE_AND_FORGET=%PRINTER_FIRE_AND_FORGET%"

echo [5/6] Enabling Windows Service recovery...
sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul
sc failureflag "%SERVICE_NAME%" 1 >nul

echo [6/6] Starting service...
sc start "%SERVICE_NAME%" >nul
if errorlevel 1 (
  echo [WARNING] Service start returned a non-zero code.
  echo           Check logs if the service does not reach RUNNING.
)
timeout /t 2 >nul

echo.
echo ============================================================
echo   Service installed successfully
echo ============================================================
echo   Name:         %SERVICE_NAME%
echo   Host:         %HOST%
echo   Port:         %PORT%
echo   CORS_ORIGINS: %CORS_ORIGINS%
echo.
echo   This setup now:
echo   - starts automatically on Windows boot
echo   - runs without needing a user login
echo   - restarts automatically if Python exits or crashes
echo   - writes service logs to:
echo       %APP_LOG%
echo       %APP_ERR%
echo.
echo   Useful commands:
echo     sc query "%SERVICE_NAME%"
echo     sc stop "%SERVICE_NAME%"
echo     sc start "%SERVICE_NAME%"
echo     "%NSSM_EXE%" edit "%SERVICE_NAME%"
echo.
echo   To remove it later:
echo     uninstall_middleware_service.bat
echo ============================================================

exit /b 0
