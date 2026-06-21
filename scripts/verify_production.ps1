param(
    [int]$Port = 5001,
    [string]$Hostname = "r10-print.k95foods.com"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$failures = 0

function Check {
    param(
        [string]$Label,
        [scriptblock]$Test
    )

    try {
        & $Test
        Write-Host "[OK]   $Label"
    } catch {
        Write-Host "[FAIL] $Label"
        Write-Host "       $($_.Exception.Message)"
        $script:failures++
    }
}

function Get-CloudflaredService {
    foreach ($name in @("Cloudflared", "cloudflared")) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($svc) {
            return $svc
        }
    }
    throw "Cloudflared Windows service not found (expected name: Cloudflared)"
}

function Get-CloudflaredServiceCim {
    foreach ($name in @("Cloudflared", "cloudflared")) {
        $svc = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
        if ($svc) {
            return $svc
        }
    }
    throw "Cloudflared Windows service not found (expected name: Cloudflared)"
}

Write-Host ""
Write-Host "Production verification"
Write-Host "======================="
Write-Host ""

Check "PrinterMiddleware service is RUNNING" {
    $svc = Get-Service -Name PrinterMiddleware -ErrorAction Stop
    if ($svc.Status -ne "Running") {
        throw "Status is $($svc.Status)"
    }
}

Check "PrinterMiddleware service start type is Automatic" {
    $svc = Get-CimInstance Win32_Service -Filter "Name='PrinterMiddleware'" -ErrorAction Stop
    if ($svc.StartMode -ne "Auto") {
        throw "StartMode is $($svc.StartMode)"
    }
}

Check "Cloudflared service is RUNNING" {
    $svc = Get-CloudflaredService
    if ($svc.Status -ne "Running") {
        throw "Status is $($svc.Status)"
    }
}

Check "Cloudflared service start type is Automatic" {
    $svc = Get-CloudflaredServiceCim
    if ($svc.StartMode -ne "Auto") {
        throw "StartMode is $($svc.StartMode)"
    }
}

Check "Middleware listens on port $Port" {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) {
        throw "No listener on port $Port"
    }
}

Check "Local health endpoint responds" {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 10
    if ($health.status -ne "healthy") {
        throw "Unexpected health response: $($health | ConvertTo-Json -Compress)"
    }
}

Check "cloudflared config exists" {
    $configPath = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
    if (-not (Test-Path $configPath)) {
        throw "Missing $configPath"
    }
}

Check "Public hostname responds ($Hostname)" {
    $uri = "https://$Hostname/health"
    $health = Invoke-RestMethod -Uri $uri -TimeoutSec 20
    if ($health.status -ne "healthy") {
        throw "Unexpected health response: $($health | ConvertTo-Json -Compress)"
    }
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "All checks passed."
    Write-Host "  Local:  http://127.0.0.1:$Port/health"
    Write-Host "  Public: https://$Hostname/health"
    exit 0
}

Write-Host "$failures check(s) failed. Review service logs:"
Write-Host "  logs\service-output.log"
Write-Host "  logs\service-error.log"
Write-Host ""
Write-Host "If Cloudflared installed but did not start, run:"
Write-Host "  finish_cloudflared_service.bat"
exit 1
