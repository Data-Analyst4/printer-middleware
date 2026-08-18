@echo off
setlocal EnableExtensions

rem Restart PrinterMiddleware Windows service (pick up config changes).

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -ArgumentList '%*' -Wait"
  exit /b %ERRORLEVEL%
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "SERVICE_NAME=PrinterMiddleware"
set "LOCAL_NSSM=%ROOT_DIR%nssm.exe"
set "NSSM_EXE=%LOCAL_NSSM%"

if not exist "%LOCAL_NSSM%" (
  where nssm >nul 2>&1
  if not errorlevel 1 (
    set "NSSM_EXE=nssm"
  ) else (
    set "NSSM_EXE="
  )
)

set "NO_PAUSE=0"
if /I "%~1"=="/nopause" set "NO_PAUSE=1"
if /I "%~1"=="-nopause" set "NO_PAUSE=1"

sc.exe query "%SERVICE_NAME%" >nul 2>&1
if errorlevel 1 (
  echo Service "%SERVICE_NAME%" is not installed.
  echo Run install_middleware_service.bat first.
  if "%NO_PAUSE%"=="0" pause
  exit /b 1
)

echo Restarting "%SERVICE_NAME%"...

if defined NSSM_EXE (
  "%NSSM_EXE%" restart "%SERVICE_NAME%"
) else (
  sc.exe stop "%SERVICE_NAME%"
  timeout /t 3 /nobreak >nul
  sc.exe start "%SERVICE_NAME%"
)

if errorlevel 1 (
  echo.
  echo Restart failed. Check: sc.exe query %SERVICE_NAME%
  if "%NO_PAUSE%"=="0" pause
  exit /b 1
)

timeout /t 2 /nobreak >nul
sc.exe query "%SERVICE_NAME%"
echo.
echo Done. Health check: curl http://127.0.0.1:5000/health
if "%NO_PAUSE%"=="0" pause
exit /b 0
