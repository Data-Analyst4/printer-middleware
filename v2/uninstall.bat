@echo off
setlocal
cd /d "%~dp0"

set SERVICE=PrinterMiddlewareV2
set CF=CloudflaredV2

if exist "..\nssm.exe" (
  set NSSM=..\nssm.exe
) else if exist "nssm.exe" (
  set NSSM=nssm.exe
) else (
  echo nssm.exe not found
  exit /b 1
)

"%NSSM%" stop %SERVICE% 2>nul
"%NSSM%" remove %SERVICE% confirm 2>nul
"%NSSM%" stop %CF% 2>nul
"%NSSM%" remove %CF% confirm 2>nul

echo Services removed: %SERVICE%, %CF%
pause
