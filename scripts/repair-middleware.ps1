# Diagnose and repair PrinterMiddleware service health on port 5001.
param(
    [int]$Port = 5001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$outputLog = Join-Path $RootDir "logs\service-output.log"
$errorLog = Join-Path $RootDir "logs\service-error.log"
$healthUri = "http://127.0.0.1:$Port/health"

Write-Host ""
Write-Host "==> Folder permissions (Local System needs logs + db)" -ForegroundColor Cyan
$logsDir = Join-Path $RootDir "logs"
$dbDir = Join-Path $RootDir "app\db"
$configDir = Join-Path $RootDir "config"
foreach ($dir in @($logsDir, $dbDir, $configDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
icacls $logsDir /grant "SYSTEM:(OI)(CI)F" /T 2>$null | Out-Null
icacls $dbDir /grant "SYSTEM:(OI)(CI)F" /T 2>$null | Out-Null
icacls $configDir /grant "SYSTEM:(OI)(CI)M" /T 2>$null | Out-Null

Write-Host ""
Write-Host "==> Ensure Waitress is installed (Windows service WSGI)" -ForegroundColor Cyan
if (Test-Path $venvPython) {
    & $venvPython -m pip install "waitress==3.0.0" 2>&1 | ForEach-Object { Write-Host $_ }
}

Write-Host ""
Write-Host "==> Service status" -ForegroundColor Cyan
sc.exe query PrinterMiddleware

Write-Host ""
Write-Host "==> Port $Port listener" -ForegroundColor Cyan
Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess |
    Format-Table -AutoSize

Write-Host ""
Write-Host "==> Recent service logs" -ForegroundColor Cyan
foreach ($logPath in @($outputLog, $errorLog)) {
    if (Test-Path $logPath) {
        Write-Host "--- $logPath ---" -ForegroundColor Yellow
        Get-Content $logPath -Tail 30
        Write-Host ""
    } else {
        Write-Host "Missing: $logPath"
    }
}

Write-Host ""
Write-Host "==> Manual import test" -ForegroundColor Cyan
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtualenv missing at $venvPython"
} else {
    $importResult = & $venvPython -c "import main; print('import ok')" 2>&1
    Write-Host ($importResult -join "`n")
}

Write-Host ""
Write-Host "==> Restarting service" -ForegroundColor Cyan
sc.exe stop PrinterMiddleware | Out-Null
Start-Sleep -Seconds 3
sc.exe start PrinterMiddleware | Out-Null
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "==> Health check" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 10
    Write-Host "OK: $healthUri -> $($health.status)" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "FAILED: $healthUri" -ForegroundColor Red
    Write-Host $_.Exception.Message
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Fix any import error shown above"
    Write-Host "  2. Run as Admin: install_middleware_service.bat $Port"
    Write-Host "  3. If healthy, run: continue-install.bat"
    exit 1
}
