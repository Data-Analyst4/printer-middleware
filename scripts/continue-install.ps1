# Completes Cloudflare tunnel + Cloudflared service when middleware is already installed.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SetupScript = Join-Path $RootDir "scripts\setup-all.ps1"

if (-not (Test-Path $SetupScript)) {
    throw "Missing $SetupScript"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Continue Install - Tunnel + Cloudflared Service" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Project: $RootDir"
Write-Host ""

& $SetupScript -TunnelAndCloudflaredOnly
exit $LASTEXITCODE
