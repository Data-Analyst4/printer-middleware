@echo off
setlocal EnableExtensions

rem Removes both production Windows services (middleware + cloudflared tunnel).

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo Removing production services...
echo.

call "%ROOT_DIR%uninstall_middleware_service.bat"
call "%ROOT_DIR%uninstall_cloudflared_service.bat"

echo.
echo Production services removed. Project files, logs, and Cloudflare credentials were kept.

exit /b 0
