@echo off
setlocal EnableExtensions

rem Production PC full install - run as Administrator.
rem Extract GitHub ZIP to C:\printer-middleware first.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-production-pc.ps1" %*
exit /b %ERRORLEVEL%
