# Install a second Rynan middleware instance for R10E / printer P1.
# Target: C:\printer-middleware-r10e
# Local:  http://127.0.0.1:5004
# Public: https://r10e-printer.k95foods.com
#
# Does NOT modify existing PrinterMiddleware / Cloudflared / Domino services.
# Does NOT stop unrelated cloudflared processes.

param(
    [string]$TargetDir = "C:\printer-middleware-r10e",
    [string]$SourceDir = "",
    [string]$Hostname = "r10e-printer.k95foods.com",
    [string]$TunnelName = "r10e-printer",
    [int]$Port = 5004,
    [string]$HostAddr = "0.0.0.0",
    [string]$ServiceName = "PrinterMiddlewareR10E",
    [string]$CfServiceName = "CloudflaredR10E",
    [string]$PrinterId = "P1",
    [string]$PrinterIp = "192.168.1.120",
    [int]$PrinterPort = 2030,
    [switch]$SkipCloudflare,
    [switch]$SkipCopy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $SourceDir) {
    $SourceDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
}
$SourceDir = $SourceDir.TrimEnd("\")
$TargetDir = $TargetDir.TrimEnd("\")

function Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    if ($script:LogFile) {
        Add-Content -Path $script:LogFile -Value $line -ErrorAction SilentlyContinue
    }
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
        "-File", "`"$PSCommandPath`"",
        "-TargetDir", "`"$TargetDir`"",
        "-SourceDir", "`"$SourceDir`"",
        "-Hostname", $Hostname,
        "-TunnelName", $TunnelName,
        "-Port", "$Port",
        "-HostAddr", $HostAddr,
        "-ServiceName", $ServiceName,
        "-CfServiceName", $CfServiceName,
        "-PrinterId", $PrinterId,
        "-PrinterIp", $PrinterIp,
        "-PrinterPort", "$PrinterPort"
    )
    if ($SkipCloudflare) { $argList += "-SkipCloudflare" }
    if ($SkipCopy) { $argList += "-SkipCopy" }
    $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $proc.ExitCode
}

function Find-Python {
    $candidates = @(
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
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

function Find-Nssm {
    param([string]$PreferDir)
    $local = Join-Path $PreferDir "nssm.exe"
    if (Test-Path $local) { return $local }
    $live = "C:\printer-middleware\nssm.exe"
    if (Test-Path $live) { return $live }
    $cmd = Get-Command nssm -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $wingetLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\nssm.exe"
    if (Test-Path $wingetLinks) { return $wingetLinks }
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

function New-RandomToken([int]$Bytes = 24) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buffer)
    $rng.Dispose()
    return ([System.BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

function Deploy-AppCopy {
    param([string]$From, [string]$To)

    Log "Copying app from $From -> $To"
    New-Item -ItemType Directory -Force -Path $To | Out-Null

    $excludeDirs = @(
        ".git", ".venv", "venv", "__pycache__", "logs", "domino", "v2", "sdk",
        "node_modules", ".cursor", "agent-transcripts"
    )
    $excludeFiles = @(
        "*.pyc", "*.pyo", ".env", "config\\site.env", "config\\printers.json",
        "app\\db\\*.db", "app\\db\\*.db-*"
    )

    $xd = @()
    foreach ($d in $excludeDirs) { $xd += @("/XD", $d) }
    $xf = @()
    foreach ($f in $excludeFiles) { $xf += @("/XF", $f) }

    $args = @(
        $From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"
    ) + $xd + $xf

    & robocopy @args | Out-Null
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        throw "robocopy failed with exit code $code"
    }
    Log "Copy complete (robocopy exit $code)"
}

function Write-SiteEnvIfMissing {
    param([string]$Path)

    if (Test-Path $Path) {
        Log "Keeping existing $Path"
        return
    }

    $secret = New-RandomToken 32
    $apiKey = "CHANGE_ME_r10e_api_" + (New-RandomToken 8)
    $password = "CHANGE_ME_r10e_pass_" + (New-RandomToken 6)

    $body = @"
# R10E second instance — edit placeholders, then restart PrinterMiddlewareR10E.
SITE_NAME=R10E
TUNNEL_NAME=$TunnelName
PUBLIC_HOSTNAME=$Hostname
PORT=$Port
HOST=$HostAddr
CORS_ORIGINS=*

# Dashboard login (edit these, then restart the service)
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=$password
SECRET_KEY=$secret
API_KEY=$apiKey
SESSION_COOKIE_NAME=pm_r10e_session

CAMERA_IMPORT_ENABLED=true
CAMERA_IMPORT_BATCH_URL=http://192.168.0.68:5001/api/import_batch
CAMERA_IMPORT_TIMEOUT=3
CAMERA_IMPORT_FLOW=immediate
"@
    Set-Content -Path $Path -Value $body -Encoding ASCII
    Log "Wrote $Path with generated placeholders (edit DASHBOARD_PASSWORD / API_KEY)"
}

function Write-PrintersJson {
    param([string]$Path)

    $json = @"
{
  "$PrinterId": {
    "ip": "$PrinterIp",
    "port": $PrinterPort
  }
}
"@
    Set-Content -Path $Path -Value $json -Encoding ASCII
    Log "Wrote $Path ($PrinterId -> $PrinterIp`:$PrinterPort)"
}

function Read-SiteEnv([string]$Path) {
    $settings = @{}
    if (-not (Test-Path $Path)) { return $settings }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2) {
            $settings[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    return $settings
}

function Ensure-Venv {
    param([string]$Root, [string]$PythonExe)

    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Log "Creating venv with $PythonExe"
        & $PythonExe -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) { throw "venv create failed" }
    }
    $req = Join-Path $Root "requirements.txt"
    Log "pip install -r requirements.txt"
    & $venvPython -m pip install --upgrade pip | Out-Null
    & $venvPython -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    return $venvPython
}

# --- main ---
Ensure-Admin

if (-not (Test-Path (Join-Path $SourceDir "main.py"))) {
    throw "Source main.py not found under $SourceDir"
}

if (-not $SkipCopy) {
    Deploy-AppCopy -From $SourceDir -To $TargetDir
} elseif (-not (Test-Path (Join-Path $TargetDir "main.py"))) {
    throw "SkipCopy set but $TargetDir\main.py missing"
}

$LogsDir = Join-Path $TargetDir "logs"
$ConfigDir = Join-Path $TargetDir "config"
$DbDir = Join-Path $TargetDir "app\db"
New-Item -ItemType Directory -Force -Path $LogsDir, $ConfigDir, $DbDir | Out-Null
$script:LogFile = Join-Path $LogsDir "install-r10e-full.log"
"" | Set-Content -Path $script:LogFile -Encoding ASCII

Log "============================================================"
Log "R10E install target: $TargetDir"
Log "Source: $SourceDir"
Log "Public hostname: $Hostname"
Log "Local port: $Port"
Log "Services: $ServiceName / $CfServiceName"

$SiteEnvPath = Join-Path $ConfigDir "site.env"
$PrintersPath = Join-Path $ConfigDir "printers.json"
Write-SiteEnvIfMissing -Path $SiteEnvPath
Write-PrintersJson -Path $PrintersPath
$settings = Read-SiteEnv $SiteEnvPath

$pythonBase = Find-Python
if (-not $pythonBase) { throw "Python not found. Install Python 3.11+ first." }
Log "Base Python: $pythonBase"
$VenvPython = Ensure-Venv -Root $TargetDir -PythonExe $pythonBase
Log "Venv Python: $VenvPython"

$Nssm = Find-Nssm -PreferDir $TargetDir
if (-not $Nssm) {
    # Download local nssm into target
    Log "Downloading nssm.exe..."
    $zip = Join-Path $env:TEMP "nssm-2.24.zip"
    $dir = Join-Path $env:TEMP "nssm-2.24"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    $Nssm = Join-Path $TargetDir "nssm.exe"
    Copy-Item (Join-Path $dir "nssm-2.24\win64\nssm.exe") $Nssm -Force
}
elseif ($Nssm -ne (Join-Path $TargetDir "nssm.exe")) {
    Copy-Item $Nssm (Join-Path $TargetDir "nssm.exe") -Force -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $TargetDir "nssm.exe")) {
        $Nssm = Join-Path $TargetDir "nssm.exe"
    }
}
Log "NSSM: $Nssm"

icacls $TargetDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
$pyHome = Split-Path (Split-Path $pythonBase -Parent) -Parent
if ($pyHome -and (Test-Path $pyHome)) {
    icacls $pyHome /grant "SYSTEM:(OI)(CI)RX" /T 2>$null | Out-Null
}

# Middleware service
Log "Installing Windows service $ServiceName on port $Port"
& $Nssm stop $ServiceName 2>$null | Out-Null
& $Nssm remove $ServiceName confirm 2>$null | Out-Null
sc.exe delete $ServiceName 2>$null | Out-Null
Start-Sleep -Seconds 1

& $Nssm install $ServiceName $VenvPython | Out-Null
& $Nssm set $ServiceName AppParameters "main.py --host $HostAddr --port $Port" | Out-Null
& $Nssm set $ServiceName AppDirectory $TargetDir | Out-Null
& $Nssm set $ServiceName DisplayName "Printer Middleware R10E" | Out-Null
& $Nssm set $ServiceName Description "R10E printer middleware (P1) on port $Port -> $Hostname" | Out-Null
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

$envLines = @(
    "PYTHONUNBUFFERED=1",
    "HOST=$HostAddr",
    "PORT=$Port",
    "CORS_ORIGINS=*"
)
foreach ($key in @(
    "DASHBOARD_USER", "DASHBOARD_PASSWORD", "SECRET_KEY", "API_KEY",
    "SESSION_COOKIE_NAME", "CAMERA_IMPORT_ENABLED", "CAMERA_IMPORT_BATCH_URL",
    "CAMERA_IMPORT_TIMEOUT", "CAMERA_IMPORT_FLOW", "SITE_NAME"
)) {
    if ($settings.ContainsKey($key) -and $settings[$key]) {
        $envLines += "$key=$($settings[$key])"
    }
}
$envExtra = $envLines -join "`r`n"
& $Nssm set $ServiceName AppEnvironmentExtra $envExtra | Out-Null
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
sc.exe failureflag $ServiceName 1 | Out-Null
sc.exe config $ServiceName start= delayed-auto | Out-Null

& $Nssm start $ServiceName | Out-Null
Start-Sleep -Seconds 5

$healthOk = $false
$healthUri = "http://127.0.0.1:$Port/health"
for ($i = 1; $i -le 18; $i++) {
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

# Restart helper for this instance
$restartBat = @"
@echo off
setlocal EnableExtensions
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0' -Wait"
  exit /b %ERRORLEVEL%
)
set "SERVICE_NAME=$ServiceName"
set "NSSM_EXE=%~dp0nssm.exe"
if not exist "%NSSM_EXE%" set "NSSM_EXE=nssm"
echo Restarting "%SERVICE_NAME%"...
"%NSSM_EXE%" restart "%SERVICE_NAME%"
timeout /t 2 /nobreak >nul
sc.exe query "%SERVICE_NAME%"
echo Health: curl http://127.0.0.1:$Port/health
pause
"@
Set-Content -Path (Join-Path $TargetDir "restart-middleware.bat") -Value $restartBat -Encoding ASCII

if ($SkipCloudflare) {
    Log "Cloudflare skipped (-SkipCloudflare)"
    Log "Local ready: $healthUri"
    Log "EXIT=0"
    exit 0
}

# Cloudflare — separate tunnel + service; do not touch existing Cloudflared / DominoCloudflared
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

$configPath = Join-Path $cloudDir "config-r10e-printer.yml"
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

# SYSTEM profile: copy credentials + this config only (do not overwrite other configs destructively)
$systemCfDir = "C:\Windows\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Force -Path $systemCfDir | Out-Null
Copy-Item $credFile $systemCfDir -Force
Copy-Item $configPath $systemCfDir -Force
if (Test-Path $certPath) { Copy-Item $certPath $systemCfDir -Force -ErrorAction SilentlyContinue }
icacls $cloudDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
icacls $systemCfDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null

# Install ONLY CloudflaredR10E — never stop Cloudflared / DominoCloudflared
Log "Installing $CfServiceName service (existing tunnels left running)"
& $Nssm stop $CfServiceName 2>$null | Out-Null
& $Nssm remove $CfServiceName confirm 2>$null | Out-Null
sc.exe delete $CfServiceName 2>$null | Out-Null
Start-Sleep -Seconds 1

$cfArgs = "tunnel --no-autoupdate --config `"$configPath`" run"
& $Nssm install $CfServiceName $cf | Out-Null
& $Nssm set $CfServiceName AppParameters $cfArgs | Out-Null
& $Nssm set $CfServiceName AppDirectory $TargetDir | Out-Null
& $Nssm set $CfServiceName DisplayName "Cloudflared Tunnel R10E" | Out-Null
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
sc.exe config $CfServiceName start= delayed-auto | Out-Null

& $Nssm start $CfServiceName | Out-Null
Start-Sleep -Seconds 8
sc.exe query $CfServiceName | Out-String | ForEach-Object { Log $_.TrimEnd() }

# Confirm existing services still running
foreach ($svc in @("PrinterMiddleware", "Cloudflared", "DominoPrinterMiddleware", "DominoCloudflared")) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) {
        Log ("Existing service ${svc}: " + $s.Status)
    }
}

Log "============================================================"
Log "Install complete"
Log "Local:  $healthUri"
Log "Public: https://$Hostname/health"
Log "Edit login: $SiteEnvPath  then run restart-middleware.bat"
Log "EXIT=0"
exit 0
