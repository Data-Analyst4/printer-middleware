@echo off
setlocal EnableExtensions

rem Downloads printer-middleware from GitHub without Git installed.
rem Then optionally runs install.bat (Administrator required for full install).

set "TARGET_DIR=C:\printer-middleware"
set "REPO_ZIP_URL=https://github.com/Data-Analyst4/printer-middleware/archive/refs/heads/develop.zip"
set "ROOT_DIR=%~dp0"

echo ============================================================
echo   Download Printer Middleware (no Git required)
echo ============================================================
echo   Source: GitHub develop branch
echo   Target: %TARGET_DIR%
echo ============================================================
echo.

where powershell >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PowerShell is required.
  exit /b 1
)

set "RUN_INSTALL=0"
if /I "%~1"=="install" set "RUN_INSTALL=1"

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\download-app.ps1" -TargetDir "%TARGET_DIR%" -ZipUrl "%REPO_ZIP_URL%"
if errorlevel 1 (
  echo.
  echo [ERROR] Download failed.
  exit /b 1
)

echo.
echo [OK] App downloaded to %TARGET_DIR%
echo.
echo Next steps:
echo   1. Edit printer IPs:  notepad %TARGET_DIR%\config\printers.json
echo   2. Right-click install.bat -^> Run as administrator
echo      Or from Admin CMD:  cd /d %TARGET_DIR% ^&^& install.bat
echo.

if "%RUN_INSTALL%"=="1" (
  echo Starting install.bat as Administrator...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%TARGET_DIR%\install.bat' -Verb RunAs -WorkingDirectory '%TARGET_DIR%'"
)

exit /b 0
