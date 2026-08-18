param(
    [string]$ServiceName = "PrinterMiddleware",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

function Assert-Healthy {
    param([int]$TimeoutSec = 20)

    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 5
            if ($resp.StatusCode -eq 200) {
                Write-Host "Health check OK" -ForegroundColor Green
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Health check failed within $TimeoutSec seconds."
}

Write-Host "=== Start/Stop Test ===" -ForegroundColor Cyan
sc.exe stop $ServiceName | Out-Host
Start-Sleep -Seconds 4
sc.exe start $ServiceName | Out-Host
Assert-Healthy

Write-Host "=== Crash Recovery Test ===" -ForegroundColor Cyan
$queryEx = sc.exe queryex $ServiceName
$queryEx | Out-Host
$pidLine = $queryEx | Select-String "PID\s*:\s*(\d+)"
if (-not $pidLine) {
    throw "Could not find service PID."
}
$servicePid = [int]$pidLine.Matches[0].Groups[1].Value
if ($servicePid -le 0) {
    throw "Invalid service PID."
}

Write-Host "Killing PID $servicePid to simulate sudden stop..." -ForegroundColor Yellow
Stop-Process -Id $servicePid -Force

Start-Sleep -Seconds 12
sc.exe query $ServiceName | Out-Host
Assert-Healthy -TimeoutSec 40

Write-Host "Resilience tests passed." -ForegroundColor Green
