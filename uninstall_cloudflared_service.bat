@echo off
setlocal EnableExtensions

rem Removes the cloudflared Windows service (registered as "Cloudflared").

set "SERVICE_NAME=Cloudflared"
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "NSSM_EXE=%ROOT_DIR%\nssm.exe"
set "CLOUDFLARED_EXE="

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

if exist "%ProgramFiles(x86)%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles(x86)%\cloudflared\cloudflared.exe"
) else if exist "%ProgramFiles%\cloudflared\cloudflared.exe" (
  set "CLOUDFLARED_EXE=%ProgramFiles%\cloudflared\cloudflared.exe"
)

echo Stopping and removing %SERVICE_NAME% Windows service...

sc.exe stop %SERVICE_NAME% >nul 2>&1
taskkill /IM cloudflared.exe /F >nul 2>&1

if exist "%NSSM_EXE%" (
  "%NSSM_EXE%" stop %SERVICE_NAME% >nul 2>&1
  "%NSSM_EXE%" remove %SERVICE_NAME% confirm >nul 2>&1
)

if defined CLOUDFLARED_EXE (
  "%CLOUDFLARED_EXE%" service uninstall >nul 2>&1
)

sc.exe delete %SERVICE_NAME% >nul 2>&1

echo.
echo %SERVICE_NAME% service removed.
echo Tunnel credentials in %%USERPROFILE%%\.cloudflared were left in place.

exit /b 0
