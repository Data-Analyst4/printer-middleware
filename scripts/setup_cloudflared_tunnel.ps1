param(
    [Parameter(Mandatory = $true)]
    [string]$TunnelToken,
    [string]$ServiceName = "CloudflaredTunnel"
)

$ErrorActionPreference = "Stop"

Write-Host "Checking cloudflared..." -ForegroundColor Cyan
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared is not installed. Install it first: winget install --id Cloudflare.cloudflared -e"
}

# Remove old service if present.
sc.exe stop $ServiceName | Out-Null
Start-Sleep -Seconds 2
sc.exe delete $ServiceName | Out-Null
Start-Sleep -Seconds 2

$cloudflaredPath = (Get-Command cloudflared).Source
$binPath = '"' + $cloudflaredPath + '" tunnel --no-autoupdate run --token ' + $TunnelToken

Write-Host "Creating tunnel service '$ServiceName'..." -ForegroundColor Cyan
sc.exe create $ServiceName binPath= $binPath start= auto DisplayName= "Cloudflared Tunnel" | Out-Host
sc.exe description $ServiceName "Cloudflare Tunnel for printer middleware" | Out-Host
sc.exe config $ServiceName start= delayed-auto | Out-Host

# Restart tunnel service on failure.
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Host
sc.exe failureflag $ServiceName 1 | Out-Host

sc.exe start $ServiceName | Out-Host
Start-Sleep -Seconds 5
sc.exe query $ServiceName | Out-Host

Write-Host "Tunnel service setup complete." -ForegroundColor Green
