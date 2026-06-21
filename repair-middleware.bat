@echo off
setlocal EnableExtensions

rem Diagnose and restart PrinterMiddleware when /health fails.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%scripts\repair-middleware.ps1" %*
exit /b %ERRORLEVEL%
