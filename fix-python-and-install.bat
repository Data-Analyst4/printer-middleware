@echo off
setlocal EnableExtensions

rem Fixes fake Windows Store python and reruns full install.
rem Run as Administrator.

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo ============================================================
echo   Fix Python + Install Printer Middleware
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\install-python.ps1"
if errorlevel 1 (
  echo [ERROR] Python fix failed.
  pause
  exit /b 1
)

if exist "%ROOT_DIR%\.venv" (
  echo Removing old virtual environment...
  rmdir /s /q "%ROOT_DIR%\.venv"
)

echo.
echo Starting full install...
call "%ROOT_DIR%install.bat"
exit /b %ERRORLEVEL%
