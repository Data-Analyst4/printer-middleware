@echo off
setlocal EnableExtensions

rem Refreshes C:\printer-middleware from GitHub without Git installed.
rem Keeps config\printers.json and config\site.env if they already exist.

set "TARGET_DIR=C:\printer-middleware"
set "ROOT_DIR=%~dp0"
set "REPO_ZIP_URL=https://github.com/Data-Analyst4/printer-middleware/archive/refs/heads/develop.zip"

echo ============================================================
echo   Update Printer Middleware (no Git required)
echo ============================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$target='%TARGET_DIR%';" ^
  "$zip=Join-Path $env:TEMP 'printer-middleware-update.zip';" ^
  "$extract=Join-Path $env:TEMP 'printer-middleware-update-extract';" ^
  "$printers=Join-Path $target 'config\printers.json';" ^
  "$site=Join-Path $target 'config\site.env';" ^
  "$printersBackup=Join-Path $env:TEMP 'printers.json.bak';" ^
  "$siteBackup=Join-Path $env:TEMP 'site.env.bak';" ^
  "if (Test-Path $printers) { Copy-Item $printers $printersBackup -Force };" ^
  "if (Test-Path $site) { Copy-Item $site $siteBackup -Force };" ^
  "Invoke-WebRequest -Uri '%REPO_ZIP_URL%' -OutFile $zip -UseBasicParsing;" ^
  "Remove-Item $extract -Recurse -Force -ErrorAction SilentlyContinue;" ^
  "Expand-Archive $zip $extract -Force;" ^
  "$newFolder=(Get-ChildItem $extract -Directory | Select-Object -First 1).FullName;" ^
  "if (Test-Path $target) { Remove-Item $target -Recurse -Force };" ^
  "Move-Item $newFolder $target;" ^
  "if (Test-Path $printersBackup) { Copy-Item $printersBackup $printers -Force } else { Copy-Item (Join-Path $target 'config\printers.json.example') $printers -Force };" ^
  "if (Test-Path $siteBackup) { Copy-Item $siteBackup $site -Force };" ^
  "Write-Host 'Update complete.'"

if errorlevel 1 (
  echo [ERROR] Update failed.
  exit /b 1
)

echo.
echo Updated %TARGET_DIR%
echo Now run as Administrator:  install.bat
echo.
pause
