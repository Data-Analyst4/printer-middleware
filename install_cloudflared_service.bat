@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Installs the named Cloudflare tunnel as a Windows service via NSSM.
rem Starts at boot, runs without login, restarts on crash.
rem Requires %%USERPROFILE%%\.cloudflared\config.yml

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

rem %~dp0 trailing backslash breaks nssm AppDirectory quotes — strip it.
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

set "CONFIG_PATH=%USERPROFILE%\.cloudflared\config.yml"
set "SERVICE_NAME=Cloudflared"
set "DISPLAY_NAME=Cloudflared Tunnel"
set "LOCAL_PORT=5000"
set "CLOUDFLARED_EXE="
set "NSSM_EXE=%ROOT_DIR%\nssm.exe"

if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
) else if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles%\cloudflared\cloudflared.exe"
) else (
  where cloudflared >nul 2>&1
  if not errorlevel 1 for /f "delims=" %%I in ('where cloudflared') do set "CLOUDFLARED_EXE=%%I"
)

if not defined CLOUDFLARED_EXE (
  echo [ERROR] cloudflared was not found.
  echo Install it first, for example: winget install Cloudflare.cloudflared
  exit /b 1
)

if not exist "%NSSM_EXE%" (
  echo [ERROR] nssm.exe not found at "%NSSM_EXE%"
  exit /b 1
)

if not exist "%CONFIG_PATH%" (
  echo [ERROR] Config not found at "%CONFIG_PATH%"
  echo Run install.bat / tunnel setup first.
  exit /b 1
)

rem Sync config into SYSTEM profile and rewrite credentials-file paths
rem so Local System can start the tunnel (avoids crash loop / 1033/530).
set "SYSTEM_CF_DIR=C:\Windows\System32\config\systemprofile\.cloudflared"
if not exist "%SYSTEM_CF_DIR%" mkdir "%SYSTEM_CF_DIR%"
xcopy /E /Y /I /Q "%USERPROFILE%\.cloudflared\*" "%SYSTEM_CF_DIR%\" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d='%SYSTEM_CF_DIR%'; $c=Join-Path $d 'config.yml'; if (Test-Path $c) { $t=Get-Content $c -Raw; $u=[regex]::Replace($t,'(?im)(credentials-file:\s*).+\\([^\\\r\n]+\.json)\s*',('${1}'+$d+'\${2}')); Set-Content -Path $c -Value $u -Encoding UTF8 }"
icacls "%SYSTEM_CF_DIR%" /grant "SYSTEM:(OI)(CI)F" /T >nul 2>&1

echo Stopping manual cloudflared processes, if any...
taskkill /IM cloudflared.exe /F >nul 2>&1

echo Removing previous %SERVICE_NAME% service (if any)...
sc.exe stop %SERVICE_NAME% >nul 2>&1
"%CLOUDFLARED_EXE%" service uninstall >nul 2>&1
"%NSSM_EXE%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM_EXE%" remove %SERVICE_NAME% confirm >nul 2>&1
sc.exe delete %SERVICE_NAME% >nul 2>&1
timeout /t 2 /nobreak >nul

echo Installing %SERVICE_NAME% Windows service using NSSM:
echo   Binary:  %CLOUDFLARED_EXE%
echo   Config:  %CONFIG_PATH%
echo   Service: %SERVICE_NAME%
echo.

if not exist "%ROOT_DIR%\logs" mkdir "%ROOT_DIR%\logs"

"%NSSM_EXE%" install %SERVICE_NAME% "%CLOUDFLARED_EXE%"
if errorlevel 1 (
  echo [ERROR] NSSM install failed.
  exit /b 1
)

"%NSSM_EXE%" set %SERVICE_NAME% AppParameters "tunnel --no-autoupdate --config \"%CONFIG_PATH%\" run"
"%NSSM_EXE%" set %SERVICE_NAME% DisplayName "%DISPLAY_NAME%"
"%NSSM_EXE%" set %SERVICE_NAME% Description "Cloudflare Tunnel for printer middleware (boot start + crash restart)"
"%NSSM_EXE%" set %SERVICE_NAME% AppDirectory "%ROOT_DIR%"
"%NSSM_EXE%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_EXE%" set %SERVICE_NAME% AppStdout "%ROOT_DIR%\logs\cloudflared-output.log"
"%NSSM_EXE%" set %SERVICE_NAME% AppStderr "%ROOT_DIR%\logs\cloudflared-error.log"
"%NSSM_EXE%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_EXE%" set %SERVICE_NAME% AppRotateBytes 1048576
"%NSSM_EXE%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_EXE%" set %SERVICE_NAME% AppRestartDelay 5000
"%NSSM_EXE%" set %SERVICE_NAME% AppThrottle 1500

rem Delayed auto-start: wait for network after reboot.
sc.exe config %SERVICE_NAME% start= delayed-auto >nul

echo Enabling Windows Service recovery for %SERVICE_NAME%...
sc.exe failure %SERVICE_NAME% reset= 86400 actions= restart/5000/restart/10000/restart/30000 >nul
sc.exe failureflag %SERVICE_NAME% 1 >nul

echo Starting %SERVICE_NAME% service...
sc.exe start %SERVICE_NAME%
if errorlevel 1 (
  echo [WARNING] Service start returned a non-zero code.
  echo           Run finish_cloudflared_service.bat as Administrator.
)

timeout /t 4 /nobreak >nul
sc.exe query %SERVICE_NAME%

echo.
echo Done. On boot / crash:
echo   - Windows starts %SERVICE_NAME% automatically (delayed-auto)
echo   - NSSM + sc recovery restart the tunnel if it exits
echo.
echo Useful commands (use sc.exe in PowerShell, not sc):
echo   sc.exe query %SERVICE_NAME%
echo   sc.exe stop %SERVICE_NAME%
echo   sc.exe start %SERVICE_NAME%
echo   finish_cloudflared_service.bat
echo   uninstall_cloudflared_service.bat
echo.
echo Config should forward your hostname to:
echo   service: http://127.0.0.1:%LOCAL_PORT%

exit /b 0
