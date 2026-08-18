@echo off
REM Install AnyDesk as a Windows service so it starts on boot and at the lock screen.
REM Right-click -> Run as administrator, or double-click (script self-elevates).

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_anydesk_autostart.ps1" %*
exit /b %ERRORLEVEL%
