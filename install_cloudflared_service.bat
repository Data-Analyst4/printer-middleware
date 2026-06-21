@echo off
setlocal EnableExtensions

rem Installs the named cloudflared tunnel as a Windows service.
rem Requires %%USERPROFILE%%\.cloudflared\config.yml

set "CONFIG_PATH=%USERPROFILE%\.cloudflared\config.yml"
set "SERVICE_NAME=Cloudflared"
set "LOCAL_PORT=5001"
set "CLOUDFLARED_EXE="

if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
) else if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles%\cloudflared\cloudflared.exe"
) else (
  where cloudflared >nul 2>&1
  if not errorlevel 1 set "CLOUDFLARED_EXE=cloudflared"
)

if not defined CLOUDFLARED_EXE (
  echo [ERROR] cloudflared was not found.
  echo Install it first, for example: winget install Cloudflare.cloudflared
  exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

if not exist "%CONFIG_PATH%" (
  echo [ERROR] Config not found at "%CONFIG_PATH%"
  echo Run install.bat first.
  exit /b 1
)

echo Stopping manual cloudflared processes, if any...
taskkill /IM cloudflared.exe /F >nul 2>&1

echo Installing cloudflared Windows service using:
echo   Binary:  %CLOUDFLARED_EXE%
echo   Config:  %CONFIG_PATH%
echo   Service: %SERVICE_NAME%
echo.

sc.exe query %SERVICE_NAME% >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Removing previous %SERVICE_NAME% service...
  sc.exe stop %SERVICE_NAME% >nul 2>&1
  "%CLOUDFLARED_EXE%" service uninstall >nul 2>&1
  sc.exe delete %SERVICE_NAME% >nul 2>&1
)

"%CLOUDFLARED_EXE%" service install
if errorlevel 1 (
  echo [ERROR] cloudflared service install failed.
  exit /b 1
)

echo Enabling Windows Service recovery for %SERVICE_NAME%...
sc.exe failure %SERVICE_NAME% reset= 86400 actions= restart/5000/restart/5000/restart/5000 >nul
sc.exe failureflag %SERVICE_NAME% 1 >nul

echo Starting %SERVICE_NAME% service...
sc.exe start %SERVICE_NAME%
if errorlevel 1 (
  echo [WARNING] Service start returned a non-zero code.
  echo           Run finish_cloudflared_service.bat as Administrator.
)

timeout /t 3 >nul

echo.
echo Service installed. Useful commands (use sc.exe in PowerShell, not sc):
echo   sc.exe query %SERVICE_NAME%
echo   sc.exe stop %SERVICE_NAME%
echo   sc.exe start %SERVICE_NAME%
echo   finish_cloudflared_service.bat
echo   uninstall_cloudflared_service.bat
echo.
echo Config should forward your hostname to:
echo   service: http://127.0.0.1:%LOCAL_PORT%

exit /b 0
