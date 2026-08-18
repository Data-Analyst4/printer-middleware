@echo off
setlocal EnableExtensions
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -Wait"
  exit /b %ERRORLEVEL%
)
set "SERVICE_NAME=PrinterMiddlewareR10E"
set "NSSM_EXE=%~dp0nssm.exe"
if not exist "%NSSM_EXE%" set "NSSM_EXE=nssm"
echo Restarting "%SERVICE_NAME%"...
"%NSSM_EXE%" restart "%SERVICE_NAME%"
timeout /t 2 /nobreak >nul
sc.exe query "%SERVICE_NAME%"
echo Health: curl http://127.0.0.1:5004/health
pause
