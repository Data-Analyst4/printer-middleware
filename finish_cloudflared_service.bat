@echo off
setlocal EnableExtensions

rem Finishes / repairs cloudflared service if install succeeded but start failed.
rem Re-applies boot start + crash recovery, then starts the service.

set "SERVICE_NAME=Cloudflared"
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "NSSM_EXE=%ROOT_DIR%\nssm.exe"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

sc.exe query %SERVICE_NAME% >nul 2>&1
if errorlevel 1 (
  echo [ERROR] %SERVICE_NAME% service is not installed.
  echo Run install_cloudflared_service.bat first.
  exit /b 1
)

echo Syncing cloudflared config for Local System...
set "SYSTEM_CF_DIR=C:\Windows\System32\config\systemprofile\.cloudflared"
if not exist "%SYSTEM_CF_DIR%" mkdir "%SYSTEM_CF_DIR%"
if exist "%USERPROFILE%\.cloudflared\" (
  xcopy /E /Y /I /Q "%USERPROFILE%\.cloudflared\*" "%SYSTEM_CF_DIR%\" >nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$d='%SYSTEM_CF_DIR%'; $c=Join-Path $d 'config.yml'; if (Test-Path $c) { $t=Get-Content $c -Raw; $u=[regex]::Replace($t,'(?im)(credentials-file:\s*).+\\([^\\\r\n]+\.json)\s*',('${1}'+$d+'\${2}')); Set-Content -Path $c -Value $u -Encoding UTF8 }"
  icacls "%SYSTEM_CF_DIR%" /grant "SYSTEM:(OI)(CI)F" /T >nul 2>&1
)

if exist "%NSSM_EXE%" (
  "%NSSM_EXE%" set %SERVICE_NAME% Start SERVICE_AUTO_START >nul 2>&1
  "%NSSM_EXE%" set %SERVICE_NAME% AppExit Default Restart >nul 2>&1
  "%NSSM_EXE%" set %SERVICE_NAME% AppRestartDelay 5000 >nul 2>&1
)

echo Applying delayed-auto start + recovery policy and starting %SERVICE_NAME%...
sc.exe config %SERVICE_NAME% start= delayed-auto >nul
sc.exe failure %SERVICE_NAME% reset= 86400 actions= restart/5000/restart/10000/restart/30000 >nul
sc.exe failureflag %SERVICE_NAME% 1 >nul
sc.exe start %SERVICE_NAME%

timeout /t 4 /nobreak >nul
sc.exe query %SERVICE_NAME%
sc.exe qc %SERVICE_NAME%
sc.exe qfailure %SERVICE_NAME%

exit /b 0
