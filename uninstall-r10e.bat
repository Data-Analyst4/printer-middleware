@echo off
setlocal EnableExtensions

rem Removes only R10E services. Does not touch PrinterMiddleware / Domino / main Cloudflared.
rem Leaves C:\printer-middleware-r10e files in place unless you delete the folder yourself.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -Wait"
  exit /b %ERRORLEVEL%
)

set "TARGET=C:\printer-middleware-r10e"
set "APP_SVC=PrinterMiddlewareR10E"
set "CF_SVC=CloudflaredR10E"
set "NSSM=%TARGET%\nssm.exe"
if not exist "%NSSM%" set "NSSM=C:\printer-middleware\nssm.exe"
if not exist "%NSSM%" (
  where nssm >nul 2>&1 && set "NSSM=nssm"
)

echo Removing %APP_SVC% and %CF_SVC%...

if exist "%NSSM%" (
  "%NSSM%" stop "%APP_SVC%" >nul 2>&1
  "%NSSM%" remove "%APP_SVC%" confirm >nul 2>&1
  "%NSSM%" stop "%CF_SVC%" >nul 2>&1
  "%NSSM%" remove "%CF_SVC%" confirm >nul 2>&1
)

sc.exe stop "%APP_SVC%" >nul 2>&1
sc.exe delete "%APP_SVC%" >nul 2>&1
sc.exe stop "%CF_SVC%" >nul 2>&1
sc.exe delete "%CF_SVC%" >nul 2>&1

echo.
echo Services removed.
echo Folder left at: %TARGET%
echo Delete that folder manually if you no longer need it.
echo Cloudflare tunnel DNS record may still exist; remove in Cloudflare Zero Trust if desired.
pause
exit /b 0
