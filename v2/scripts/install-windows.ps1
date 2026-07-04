# Printer Middleware v2 — Windows one-click installer
# Run via install.bat (self-elevates to Administrator)

param(
    [switch]$SkipCloudflare,
    [switch]$MiddlewareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvDir = Join-Path $RootDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$SiteEnvPath = Join-Path $RootDir "config\site.env"
$SiteEnvExample = Join-Path $RootDir "config\site.env.example"
$AppEnvPath = Join-Path $RootDir "config\app.env"
$AppEnvExample = Join-Path $RootDir "config\app.env.example"
$PrintersExample = Join-Path $RootDir "config\printers.json.example"
$PrintersPath = Join-Path $RootDir "config\printers.json"
$LogsDir = Join-Path $RootDir "logs"
$DataDir = Join-Path $RootDir "data"
$ServiceName = "PrinterMiddlewareV2"
$CloudflaredService = "CloudflaredV2"
$NssmCandidates = @(
    (Join-Path $RootDir "nssm.exe"),
    (Join-Path (Split-Path $RootDir -Parent) "nssm.exe")
)

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) { return }
    Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
    ) -WorkingDirectory $RootDir
    exit 0
}

function Read-EnvFile([string]$Path) {
    $settings = @{}
    if (-not (Test-Path $Path)) { return $settings }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2) { $settings[$parts[0].Trim()] = $parts[1].Trim() }
    }
    return $settings
}

function Find-Python {
    $candidates = @(
        (Get-Command python -ErrorAction SilentlyContinue)?.Source,
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    foreach ($path in $candidates) {
        $version = & $path -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -ge "3.8") { return $path }
    }
    return $null
}

function Ensure-Python {
    Write-Step "Checking Python 3.8+"
    $python = Find-Python
    if (-not $python) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "  Installing Python via winget..."
            winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
            Start-Sleep -Seconds 3
            $python = Find-Python
        }
    }
    if (-not $python) {
        throw "Python 3.8+ not found. Install from https://www.python.org/downloads/ (check 'Add to PATH')"
    }
    Write-Host "  OK: $python"
    return $python
}

function Ensure-Venv([string]$PythonPath) {
    Write-Step "Virtual environment and dependencies"
    if (-not (Test-Path $VenvDir)) {
        & $PythonPath -m venv $VenvDir
    }
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $RootDir "requirements.txt")
    Write-Host "  OK: venv ready"
}

function Ensure-ConfigFiles {
    Write-Step "Configuration files"
    foreach ($pair in @(
        @($SiteEnvExample, $SiteEnvPath),
        @($AppEnvExample, $AppEnvPath),
        @($PrintersExample, $PrintersPath)
    )) {
        if (-not (Test-Path $pair[1]) -and (Test-Path $pair[0])) {
            Copy-Item $pair[0] $pair[1]
            Write-Host "  Created $(Split-Path $pair[1] -Leaf)"
        }
    }
    New-Item -ItemType Directory -Force -Path $LogsDir, $DataDir | Out-Null
}

function Find-Nssm {
    foreach ($path in $NssmCandidates) {
        if (Test-Path $path) { return $path }
    }
    throw "nssm.exe not found. Place nssm.exe in v2 folder or repo root."
}

function Install-MiddlewareService([hashtable]$Settings) {
    Write-Step "Installing Windows service: $ServiceName"
    $nssm = Find-Nssm
    $port = if ($Settings.PORT) { $Settings.PORT } else { "5002" }
    $hostAddr = if ($Settings.HOST) { $Settings.HOST } else { "127.0.0.1" }

    & $nssm stop $ServiceName 2>$null
    & $nssm remove $ServiceName confirm 2>$null

    & $nssm install $ServiceName $PythonExe (Join-Path $RootDir "main.py")
    & $nssm set $ServiceName AppDirectory $RootDir
    & $nssm set $ServiceName DisplayName "Printer Middleware v2"
    & $nssm set $ServiceName Description "HTTP to TCP printer bridge for ERP integration"
    & $nssm set $ServiceName Start SERVICE_AUTO_START
    & $nssm set $ServiceName AppThrottle 1500
    & $nssm set $ServiceName AppExit Default Restart
    & $nssm set $ServiceName AppRestartDelay 5000
    & $nssm set $ServiceName AppStdout (Join-Path $LogsDir "service-output.log")
    & $nssm set $ServiceName AppStderr (Join-Path $LogsDir "service-error.log")
    & $nssm set $ServiceName AppRotateFiles 1
    & $nssm set $ServiceName AppRotateBytes 10485760

    $envBlock = @(
        "PYTHONUNBUFFERED=1",
        "HOST=$hostAddr",
        "PORT=$port"
    ) -join "`n"
    & $nssm set $ServiceName AppEnvironmentExtra $envBlock

    & $nssm start $ServiceName
    Start-Sleep -Seconds 4

    $healthUri = "http://127.0.0.1:$port/health"
    try {
        $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 15
        Write-Host "  OK: $healthUri -> $($health.status)"
    } catch {
        throw "Middleware health check failed at $healthUri. See logs\service-error.log"
    }
}

function Install-CloudflaredTunnel([hashtable]$Settings) {
    if ($SkipCloudflare) {
        Write-Host "Skipping Cloudflare tunnel (--SkipCloudflare)"
        return
    }

    Write-Step "Cloudflare tunnel"
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
        } else {
            Write-Warning "cloudflared not found. Install manually for public HTTPS access."
            return
        }
    }

    $hostname = if ($Settings.PUBLIC_HOSTNAME) { $Settings.PUBLIC_HOSTNAME } else { "print-v2.example.com" }
    $port = if ($Settings.PORT) { $Settings.PORT } else { "5002" }
    $tunnelName = if ($Settings.TUNNEL_NAME) { $Settings.TUNNEL_NAME } else { "printer-middleware-v2" }
    $cloudDir = Join-Path $HOME ".cloudflared"
    $configPath = Join-Path $cloudDir "config-v2.yml"

    New-Item -ItemType Directory -Force -Path $cloudDir | Out-Null
    if (-not (Test-Path $configPath)) {
        Write-Host "  Run once: cloudflared tunnel login"
        Write-Host "  Then:     cloudflared tunnel create $tunnelName"
        Write-Host "  Then:     cloudflared tunnel route dns $tunnelName $hostname"
        @(
            "tunnel: REPLACE_WITH_TUNNEL_UUID",
            "credentials-file: $cloudDir\REPLACE.json",
            "ingress:",
            "  - hostname: $hostname",
            "    service: http://127.0.0.1:$port",
            "  - service: http_status:404"
        ) | Set-Content -Path $configPath -Encoding UTF8
        Write-Warning "Edit $configPath with your tunnel UUID and credentials, then rerun install or run scripts\install-cloudflared-service.ps1"
        return
    }

    $nssm = Find-Nssm
    & $nssm stop $CloudflaredService 2>$null
    & $nssm remove $CloudflaredService confirm 2>$null
    & $nssm install $CloudflaredService (Get-Command cloudflared).Source "tunnel --config `"$configPath`" run"
    & $nssm set $CloudflaredService Start SERVICE_AUTO_START
    & $nssm set $CloudflaredService AppExit Default Restart
    & $nssm start $CloudflaredService
    Write-Host "  OK: Cloudflared service started ($hostname)"
}

Ensure-Admin
Write-Host "Printer Middleware v2 installer" -ForegroundColor Green
Write-Host "Root: $RootDir"

if (-not (Test-Path (Join-Path $RootDir "main.py"))) {
    throw "main.py not found. Run installer from v2 folder."
}

Ensure-ConfigFiles
$python = Ensure-Python
Ensure-Venv $python
$settings = Read-EnvFile $SiteEnvPath
Install-MiddlewareService $settings

if (-not $MiddlewareOnly) {
    Install-CloudflaredTunnel $settings
}

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
$port = if ($settings.PORT) { $settings.PORT } else { "5002" }
Write-Host "  Local health: http://127.0.0.1:$port/health"
Write-Host "  Dashboard:    http://127.0.0.1:$port/"
