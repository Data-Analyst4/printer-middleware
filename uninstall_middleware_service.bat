@echo off
setlocal EnableExtensions

rem Removes the printer middleware Windows service.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
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

echo Removing Windows service "%SERVICE_NAME%"...

if defined NSSM_EXE (
  "%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
  "%NSSM_EXE%" remove "%SERVICE_NAME%" confirm >nul 2>&1
) else (
  sc stop "%SERVICE_NAME%" >nul 2>&1
)

sc delete "%SERVICE_NAME%" >nul 2>&1

echo.
echo Service removed. Project files and logs were left in place.
echo.
echo Useful cleanup:
echo   Delete logs manually if you no longer need them.

exit /b 0
