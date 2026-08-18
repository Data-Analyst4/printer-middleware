# Domino middleware + Cloudflare tunnel installer (Windows PowerShell 5.1 safe)
# Installs to this folder (expected: C:\printer-middleware\domino)
# Public URL: https://domino-printer.k95foods.com -> http://127.0.0.1:5003

param(
    [string]$Hostname = "domino-printer.k95foods.com",
    [string]$TunnelName = "domino-printer",
    [int]$Port = 5003,
    [string]$HostAddr = "0.0.0.0",
    [switch]$SkipCloudflare
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RootDir = $RootDir.TrimEnd("\")
$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
$Nssm = Join-Path $RootDir "nssm.exe"
$LogsDir = Join-Path $RootDir "logs"
$SiteEnvPath = Join-Path $RootDir "config\site.env"
$PrintersPath = Join-Path $RootDir "config\printers.json"
$ServiceName = "DominoPrinterMiddleware"
$CfServiceName = "DominoCloudflared"
$LogFile = Join-Path $LogsDir "install-domino-full.log"

function Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) { return }
    Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-Hostname", $Hostname,
        "-TunnelName", $TunnelName,
        "-Port", "$Port",
        "-HostAddr", $HostAddr
    )
    if ($SkipCloudflare) { $argList += "-SkipCloudflare" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait
    exit 0
}

function Find-Cloudflared {
    $candidates = @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Invoke-Cf {
    param([string]$Exe, [string[]]$Args)
    $out = & $Exe @Args 2>&1 | Out-String
    return @{
        ExitCode = $LASTEXITCODE
        Output   = $out
    }
}

function Get-TunnelId {
    param([string]$Exe, [string]$Name)
    $result = Invoke-Cf -Exe $Exe -Args @("tunnel", "list")
    foreach ($line in ($result.Output -split "`r?`n")) {
        if ($line -match "^([0-9a-fA-F-]{36})\s+(\S+)") {
            if ($Matches[2] -eq $Name) { return $Matches[1] }
        }
    }
    return $null
}

# --- main ---
Ensure-Admin
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RootDir "config") | Out-Null
"" | Set-Content -Path $LogFile -Encoding ASCII

Log "============================================================"
Log "Domino install root: $RootDir"
Log "Public hostname: $Hostname"
Log "Local port: $Port"

if (-not (Test-Path (Join-Path $RootDir "main.py"))) {
    throw "main.py not found under $RootDir"
}
if (-not (Test-Path $VenvPython)) {
    throw "Missing venv python at $VenvPython. Run pip install first."
}
if (-not (Test-Path $Nssm)) {
    $parentNssm = Join-Path (Split-Path $RootDir -Parent) "nssm.exe"
    if (Test-Path $parentNssm) {
        Copy-Item $parentNssm $Nssm -Force
    } else {
        throw "nssm.exe not found"
    }
}

# site.env
$siteBody = @"
HOST=$HostAddr
PORT=$Port
TUNNEL_NAME=$TunnelName
PUBLIC_HOSTNAME=$Hostname
PRINTER_CONNECT_TIMEOUT=5
PRINTER_READ_TIMEOUT=5
PRINTER_SEND_RETRIES=3
"@
Set-Content -Path $SiteEnvPath -Value $siteBody -Encoding ASCII
Log "Wrote $SiteEnvPath"

if (-not (Test-Path $PrintersPath)) {
    Copy-Item (Join-Path $RootDir "config\printers.json.example") $PrintersPath -Force
    Log "Created printers.json from example - edit Domino IP before go-live"
}

icacls $RootDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null

# Middleware service
Log "Installing Windows service $ServiceName"
& $Nssm stop $ServiceName 2>$null | Out-Null
& $Nssm remove $ServiceName confirm 2>$null | Out-Null
sc.exe delete $ServiceName 2>$null | Out-Null

& $Nssm install $ServiceName $VenvPython | Out-Null
& $Nssm set $ServiceName AppParameters "main.py --host $HostAddr --port $Port" | Out-Null
& $Nssm set $ServiceName AppDirectory $RootDir | Out-Null
& $Nssm set $ServiceName DisplayName "Domino Printer Middleware" | Out-Null
& $Nssm set $ServiceName Description "HTTP to Domino Ax Codenet TCP bridge" | Out-Null
& $Nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null
& $Nssm set $ServiceName AppThrottle 1500 | Out-Null
& $Nssm set $ServiceName AppExit Default Restart | Out-Null
& $Nssm set $ServiceName AppRestartDelay 5000 | Out-Null
& $Nssm set $ServiceName AppStdout (Join-Path $LogsDir "service-output.log") | Out-Null
& $Nssm set $ServiceName AppStderr (Join-Path $LogsDir "service-error.log") | Out-Null
& $Nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $Nssm set $ServiceName AppRotateOnline 1 | Out-Null
& $Nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $Nssm set $ServiceName AppNoConsole 1 | Out-Null
$envExtra = "PYTHONUNBUFFERED=1`r`nHOST=$HostAddr`r`nPORT=$Port"
& $Nssm set $ServiceName AppEnvironmentExtra $envExtra | Out-Null
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null

& $Nssm start $ServiceName | Out-Null
Start-Sleep -Seconds 5

$healthOk = $false
$healthUri = "http://127.0.0.1:$Port/health"
for ($i = 1; $i -le 12; $i++) {
    try {
        $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 5
        if ($health.status -eq "healthy") {
            Log ("Health OK: " + ($health | ConvertTo-Json -Compress))
            $healthOk = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 3
    }
}
if (-not $healthOk) {
    throw "Health check failed at $healthUri. See $LogsDir\service-error.log"
}

if ($SkipCloudflare) {
    Log "Cloudflare skipped"
    Log "EXIT=0"
    exit 0
}

# Cloudflare
$cf = Find-Cloudflared
if (-not $cf) {
    Log "Installing cloudflared via winget..."
    winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements --disable-interactivity
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $cf = Find-Cloudflared
}
if (-not $cf) { throw "cloudflared not found after install" }
Log "cloudflared: $cf"

$cloudDir = Join-Path $env:USERPROFILE ".cloudflared"
New-Item -ItemType Directory -Force -Path $cloudDir | Out-Null
$certPath = Join-Path $cloudDir "cert.pem"

if (-not (Test-Path $certPath)) {
    Log "Opening Cloudflare login in browser (one-time). Complete login, then return here."
    $login = Invoke-Cf -Exe $cf -Args @("tunnel", "login")
    Log $login.Output
    if (-not (Test-Path $certPath)) {
        throw "cloudflared tunnel login did not create cert.pem at $certPath"
    }
}

$tunnelId = Get-TunnelId -Exe $cf -Name $TunnelName
if (-not $tunnelId) {
    Log "Creating tunnel $TunnelName ..."
    $create = Invoke-Cf -Exe $cf -Args @("tunnel", "create", $TunnelName)
    Log $create.Output
    if ($create.ExitCode -ne 0) { throw "tunnel create failed" }
    $tunnelId = Get-TunnelId -Exe $cf -Name $TunnelName
}
if (-not $tunnelId) { throw "Could not resolve tunnel id for $TunnelName" }
Log "Tunnel id: $tunnelId"

$credFile = Join-Path $cloudDir ($tunnelId + ".json")
if (-not (Test-Path $credFile)) {
    throw "Credentials missing: $credFile"
}

Log "Routing DNS $Hostname"
$dns = Invoke-Cf -Exe $cf -Args @("tunnel", "route", "dns", $TunnelName, $Hostname)
Log $dns.Output
if ($dns.ExitCode -ne 0 -and $dns.Output -notmatch "already exists|Record already exists|CNAME") {
    throw "DNS route failed"
}

$configPath = Join-Path $cloudDir "config-domino-printer.yml"
$configLines = @(
    "tunnel: $tunnelId",
    "credentials-file: $credFile",
    "ingress:",
    "  - hostname: $Hostname",
    "    service: http://127.0.0.1:$Port",
    "  - service: http_status:404"
)
Set-Content -Path $configPath -Value ($configLines -join "`r`n") -Encoding ASCII
Log "Wrote $configPath"

# SYSTEM profile copy (service often runs as Local System)
$systemCfDir = "C:\Windows\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Force -Path $systemCfDir | Out-Null
Copy-Item (Join-Path $cloudDir "*") $systemCfDir -Force -ErrorAction SilentlyContinue
icacls $cloudDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
icacls $systemCfDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null

Get-Process cloudflared -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*cloudflared*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Log "Installing $CfServiceName service"
& $Nssm stop $CfServiceName 2>$null | Out-Null
& $Nssm remove $CfServiceName confirm 2>$null | Out-Null
sc.exe delete $CfServiceName 2>$null | Out-Null

$cfArgs = "tunnel --no-autoupdate --config `"$configPath`" run"
& $Nssm install $CfServiceName $cf | Out-Null
& $Nssm set $CfServiceName AppParameters $cfArgs | Out-Null
& $Nssm set $CfServiceName AppDirectory $RootDir | Out-Null
& $Nssm set $CfServiceName DisplayName "Domino Cloudflared Tunnel" | Out-Null
& $Nssm set $CfServiceName Description "Cloudflare tunnel for $Hostname" | Out-Null
& $Nssm set $CfServiceName Start SERVICE_AUTO_START | Out-Null
& $Nssm set $CfServiceName AppExit Default Restart | Out-Null
& $Nssm set $CfServiceName AppRestartDelay 5000 | Out-Null
& $Nssm set $CfServiceName AppStdout (Join-Path $LogsDir "cloudflared-output.log") | Out-Null
& $Nssm set $CfServiceName AppStderr (Join-Path $LogsDir "cloudflared-error.log") | Out-Null
& $Nssm set $CfServiceName AppRotateFiles 1 | Out-Null
& $Nssm set $CfServiceName AppNoConsole 1 | Out-Null
sc.exe failure $CfServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
sc.exe failureflag $CfServiceName 1 | Out-Null

& $Nssm start $CfServiceName | Out-Null
Start-Sleep -Seconds 8
sc.exe query $CfServiceName | Out-String | ForEach-Object { Log $_.TrimEnd() }

Log "============================================================"
Log "Install complete"
Log "Local:  $healthUri"
Log "Public: https://$Hostname/health"
Log "EXIT=0"
exit 0
