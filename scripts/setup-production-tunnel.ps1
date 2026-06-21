# Production PC only: new Cloudflare tunnel + DNS + cloudflared Windows service.
# Default: tunnel r10-printer -> https://r10-printer.k95foods.com -> http://127.0.0.1:5001
# Does NOT include HR middleware (v8-mw). Printer middleware only.

param(
    [string]$TunnelName = "r10-printer",
    [string]$Hostname = "r10-printer.k95foods.com",
    [int]$Port = 5001,
    [switch]$SkipCloudflareLogin
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HelpersPath = Join-Path $RootDir "scripts\install-helpers.ps1"
$SiteEnvPath = Join-Path $RootDir "config\site.env"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-TunnelName", $TunnelName,
        "-Hostname", $Hostname,
        "-Port", $Port
    )
    if ($SkipCloudflareLogin) { $args += "-SkipCloudflareLogin" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList ($args -join " ") -WorkingDirectory $RootDir
    exit 0
}

if (-not (Test-Path $HelpersPath)) {
    Fail "Missing $HelpersPath"
}
. $HelpersPath

$cloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"
$configPath = Join-Path $cloudflaredDir "config.yml"
$printConfigPath = Join-Path $cloudflaredDir "config-$TunnelName.yml"

$cloudflaredExe = Resolve-CloudflaredPath
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Production tunnel setup (printer only)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Tunnel:   $TunnelName"
Write-Host "  Public:   https://$Hostname"
Write-Host "  Local:    http://127.0.0.1:$Port"
Write-Host "  cloudflared: $cloudflaredExe"
Write-Host "  User profile: $env:USERPROFILE"

function Invoke-LocalCloudflared {
    param([string[]]$ArgumentList)
    return Invoke-External -FilePath $cloudflaredExe -ArgumentList $ArgumentList
}

function Get-TunnelIdByName {
    param([string]$Name)
    $result = Invoke-LocalCloudflared @("tunnel", "list")
    foreach ($line in ($result.Output -split "`r?`n")) {
        if ($line -match "^([0-9a-f-]{36})\s+(\S+)") {
            if ($Matches[2] -eq $Name) {
                return $Matches[1]
            }
        }
    }
    return $null
}

function Write-TunnelConfigFile {
    param(
        [string]$Path,
        [string]$TunnelId,
        [string]$CredentialsFile,
        [string]$PublicHostname,
        [int]$LocalPort
    )
    $lines = @(
        "tunnel: $TunnelId",
        "credentials-file: $CredentialsFile",
        "ingress:",
        "  - hostname: $PublicHostname",
        "    service: http://127.0.0.1:$LocalPort",
        "  - service: http_status:404"
    )
    Set-Content -Path $Path -Value ($lines -join "`n") -Encoding UTF8
}

Write-Step "Checking local printer middleware"
$healthUri = "http://127.0.0.1:$Port/health"
try {
    $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 10
    if ($health.status -ne "healthy") {
        Fail "Middleware at $healthUri returned status '$($health.status)'. Start the app first."
    }
    Write-Host "  OK: $healthUri"
} catch {
    Fail "Middleware is not reachable at $healthUri. Run: .\.venv\Scripts\python.exe main.py --host 0.0.0.0 --port $Port (or install_middleware_service.bat $Port)"
}

Write-Step "Saving site config"
$siteDir = Split-Path -Parent $SiteEnvPath
if (-not (Test-Path $siteDir)) {
    New-Item -ItemType Directory -Path $siteDir -Force | Out-Null
}
@"
SITE_NAME=R10
TUNNEL_NAME=$TunnelName
PUBLIC_HOSTNAME=$Hostname
PORT=$Port
HOST=0.0.0.0
CORS_ORIGINS=*
"@ | Set-Content -Path $SiteEnvPath -Encoding UTF8
Write-Host "  Wrote $SiteEnvPath"

Write-Step "Preparing $cloudflaredDir"
if (-not (Test-Path $cloudflaredDir)) {
    New-Item -ItemType Directory -Path $cloudflaredDir -Force | Out-Null
}

$certPath = Join-Path $cloudflaredDir "cert.pem"
if (-not (Test-Path $certPath) -and -not $SkipCloudflareLogin) {
    Write-Host "  Cloudflare login required (one time). Complete the browser prompt."
    $loginResult = Invoke-LocalCloudflared @("tunnel", "login")
    if ($loginResult.ExitCode -ne 0) {
        Fail "cloudflared tunnel login failed: $($loginResult.Output)"
    }
    if (-not (Test-Path $certPath)) {
        Fail "Login did not create cert.pem at $certPath"
    }
}

Write-Step "Creating or verifying tunnel '$TunnelName' on THIS PC"
$tunnelId = Get-TunnelIdByName -Name $TunnelName
$credentialsFile = $null

if ($tunnelId) {
    $credentialsFile = Join-Path $cloudflaredDir "$tunnelId.json"
    if (Test-Path $credentialsFile) {
        Write-Host "  OK: Existing tunnel '$TunnelName' ($tunnelId) with local credentials."
    } else {
        Fail @"
Tunnel '$TunnelName' exists in Cloudflare but credentials are missing on this PC:
  $credentialsFile

Delete tunnel '$TunnelName' in Cloudflare Zero Trust -> Networks -> Tunnels, then rerun this script.
Or pick a new tunnel name that does not exist yet.
"@
    }
} else {
    Write-Host "  Creating new tunnel '$TunnelName' (credentials file will be written here)..."
    $createResult = Invoke-LocalCloudflared @("tunnel", "create", $TunnelName)
    if ($createResult.Output) {
        Write-Host "  $($createResult.Output)"
    }
    if ($createResult.ExitCode -ne 0) {
        Fail "cloudflared tunnel create '$TunnelName' failed: $($createResult.Output)"
    }
    $tunnelId = Get-TunnelIdByName -Name $TunnelName
    if (-not $tunnelId) {
        Fail "Tunnel '$TunnelName' was created but its id could not be resolved."
    }
    $credentialsFile = Join-Path $cloudflaredDir "$tunnelId.json"
}

if (-not $credentialsFile) {
    $credentialsFile = Join-Path $cloudflaredDir "$tunnelId.json"
}
if (-not (Test-Path $credentialsFile)) {
    Fail "Credentials file missing at $credentialsFile"
}
Write-Host "  OK: $credentialsFile"

Write-Step "Routing DNS: $Hostname"
$dnsResult = Invoke-LocalCloudflared @("tunnel", "route", "dns", $TunnelName, $Hostname)
if ($dnsResult.Output) {
    Write-Host "  $($dnsResult.Output)"
}
if ($dnsResult.ExitCode -ne 0 -and $dnsResult.Output -notmatch "already exists|Record already exists|CNAME") {
    Fail "DNS route failed: $($dnsResult.Output)"
}

Write-Step "Writing cloudflared config (printer only, no HR)"
if (Test-Path $configPath) {
    $backup = "$configPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item $configPath $backup -Force
    Write-Host "  Backed up previous config to $backup"
}

Write-TunnelConfigFile -Path $printConfigPath -TunnelId $tunnelId -CredentialsFile $credentialsFile -PublicHostname $Hostname -LocalPort $Port
Write-TunnelConfigFile -Path $configPath -TunnelId $tunnelId -CredentialsFile $credentialsFile -PublicHostname $Hostname -LocalPort $Port
Write-Host "  $configPath"
Write-Host "  $Hostname -> http://127.0.0.1:$Port"

Write-Step "Granting Local System access to tunnel files"
icacls $cloudflaredDir /grant "SYSTEM:(OI)(CI)F" /T 2>$null | Out-Null

Write-Step "Installing cloudflared Windows service"
Stop-ManualCloudflaredProcesses

$installer = Join-Path $RootDir "install_cloudflared_service.bat"
if (-not (Test-Path $installer)) {
    Fail "Missing $installer"
}
& cmd.exe /c "`"$installer`""
if ($LASTEXITCODE -ne 0) {
    Write-Warning "install_cloudflared_service.bat exit code $LASTEXITCODE. Trying finish_cloudflared_service.bat..."
    $finish = Join-Path $RootDir "finish_cloudflared_service.bat"
    if (Test-Path $finish) {
        & cmd.exe /c "`"$finish`""
    }
}

Start-Sleep -Seconds 8

Write-Step "Tunnel connector status"
$listResult = Invoke-LocalCloudflared @("tunnel", "list")
if ($listResult.Output) {
    Write-Host $listResult.Output
}

Write-Step "Verification"
$verifyScript = Join-Path $RootDir "scripts\verify_production.ps1"
if (Test-Path $verifyScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Port $Port -Hostname $Hostname
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Production tunnel setup complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Local:   http://127.0.0.1:$Port/health"
Write-Host "  Public:  https://$Hostname/health"
Write-Host ""
Write-Host "  Install middleware as a service (if not yet):"
Write-Host "    install_middleware_service.bat $Port"
Write-Host ""

exit 0
