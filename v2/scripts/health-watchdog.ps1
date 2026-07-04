# Health watchdog — restart middleware/tunnel on failure (run via Task Scheduler every 5 min)
param(
    [int]$Port = 5002,
    [string]$ServiceName = "PrinterMiddlewareV2",
    [string]$TunnelService = "CloudflaredV2"
)

$ErrorActionPreference = "SilentlyContinue"
$healthUri = "http://127.0.0.1:$Port/health"
$logFile = Join-Path (Split-Path $PSScriptRoot -Parent) "logs\watchdog.log"

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format o) $Message"
    Add-Content -Path $logFile -Value $line
}

try {
    $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 10
    if ($health.status -eq "healthy") {
        exit 0
    }
    Write-Log "Unhealthy response: $($health | ConvertTo-Json -Compress)"
} catch {
    Write-Log "Health check failed: $_"
}

Write-Log "Restarting $ServiceName"
Restart-Service $ServiceName -Force
Start-Sleep -Seconds 8

try {
    Invoke-RestMethod -Uri $healthUri -TimeoutSec 10 | Out-Null
    Write-Log "Middleware recovered after restart"
    exit 0
} catch {
    Write-Log "Middleware still down after restart"
}

Write-Log "Restarting tunnel service $TunnelService"
Restart-Service $TunnelService -Force
