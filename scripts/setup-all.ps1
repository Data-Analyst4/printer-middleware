# One-click setup: dependencies, middleware service, Cloudflare tunnel service.
# Run via install.bat (self-elevates to Administrator).

param(
    [switch]$SkipCloudflareLogin
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SiteEnvPath = Join-Path $RootDir "config\site.env"
$SiteEnvExample = Join-Path $RootDir "config\site.env.example"
$PrintersPath = Join-Path $RootDir "config\printers.json"
$PrintersExample = Join-Path $RootDir "config\printers.json.example"
$CloudflaredDir = Join-Path $HOME ".cloudflared"
$CloudflaredConfig = Join-Path $CloudflaredDir "config.yml"

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
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    if ($SkipCloudflareLogin) { $argList += "-SkipCloudflareLogin" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList ($argList -join " ") -WorkingDirectory $RootDir
    exit 0
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

function Refresh-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Find-InstalledExecutable {
    param(
        [string]$Name,
        [string[]]$CandidatePaths
    )

    if (Get-Command $Name -ErrorAction SilentlyContinue) {
        return (Get-Command $Name -ErrorAction Stop).Source
    }

    foreach ($candidate in $CandidatePaths) {
        if (Test-Path $candidate) {
            $parent = Split-Path -Parent $candidate
            if ($env:Path -notlike "*$parent*") {
                $env:Path = "$parent;$env:Path"
            }
            return $candidate
        }
    }

    return $null
}

function Ensure-Command {
    param(
        [string]$Name,
        [string[]]$CandidatePaths = @(),
        [scriptblock]$InstallAction
    )

    Refresh-SessionPath

    $existing = Find-InstalledExecutable -Name $Name -CandidatePaths $CandidatePaths
    if ($existing) {
        Write-Host "  OK: $Name found at $existing"
        return
    }

    Write-Host "  Installing $Name..."
    & $InstallAction

    Start-Sleep -Seconds 2
    Refresh-SessionPath

    $installed = Find-InstalledExecutable -Name $Name -CandidatePaths $CandidatePaths
    if (-not $installed) {
        throw "$Name is still missing after install attempt. Open a new Administrator Command Prompt and rerun install.bat, or restart the PC and rerun install.bat."
    }

    Write-Host "  OK: $Name found at $installed"
}

function Ensure-Python {
    Ensure-Command "python" @(
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe"
    ) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --disable-interactivity
        } else {
            throw "Python not found. Install from https://www.python.org/downloads/ (check Add to PATH), then rerun install.bat"
        }
    }
}

function Ensure-Cloudflared {
    Ensure-Command "cloudflared" @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:ProgramData\chocolatey\bin\cloudflared.exe"
    ) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements --disable-interactivity
        } elseif (Get-Command choco -ErrorAction SilentlyContinue) {
            choco install cloudflared -y
        } else {
            throw "cloudflared not found. Install with: winget install Cloudflare.cloudflared"
        }
    }
}

function Ensure-Venv {
    $venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "  Creating virtual environment..."
        python -m venv (Join-Path $RootDir ".venv")
    }
    Write-Host "  Installing Python packages..."
    & $venvPython -m pip install --upgrade pip | Out-Null
    & $venvPython -m pip install -r (Join-Path $RootDir "requirements.txt")
}

function Get-TunnelIdByName([string]$Name) {
    $output = cloudflared tunnel list 2>&1 | Out-String
    foreach ($line in ($output -split "`n")) {
        if ($line -match "^\s*([0-9a-f-]{36})\s+$([regex]::Escape($Name))\s") {
            return $Matches[1]
        }
    }
    return $null
}

function Ensure-CloudflareTunnel([hashtable]$Settings) {
    $tunnelName = $Settings["TUNNEL_NAME"]
    $hostname = $Settings["PUBLIC_HOSTNAME"]
    $port = $Settings["PORT"]

    if (-not $tunnelName -or -not $hostname) {
        throw "TUNNEL_NAME and PUBLIC_HOSTNAME must be set in config/site.env"
    }

    New-Item -ItemType Directory -Force -Path $CloudflaredDir | Out-Null

    $certPath = Join-Path $CloudflaredDir "cert.pem"
    if (-not (Test-Path $certPath) -and -not $SkipCloudflareLogin) {
        Write-Host ""
        Write-Host "  Cloudflare login required (one-time)." -ForegroundColor Yellow
        Write-Host "  A browser will open. Log in and select k95foods.com."
        Write-Host ""
        cloudflared tunnel login
    }
    if (-not (Test-Path $certPath)) {
        throw "Cloudflare cert.pem missing. Run: cloudflared tunnel login"
    }

    $tunnelId = Get-TunnelIdByName -Name $tunnelName
    if (-not $tunnelId) {
        Write-Host "  Creating tunnel '$tunnelName'..."
        $createOutput = cloudflared tunnel create $tunnelName 2>&1 | Out-String
        $tunnelId = Get-TunnelIdByName -Name $tunnelName
        if (-not $tunnelId -and $createOutput -match "([0-9a-f-]{36})") {
            $tunnelId = $Matches[1]
        }
        if (-not $tunnelId) {
            throw "Could not determine tunnel ID after create. Output: $createOutput"
        }
    } else {
        Write-Host "  OK: tunnel '$tunnelName' exists ($tunnelId)"
    }

    Write-Host "  Ensuring DNS route $hostname ..."
    cloudflared tunnel route dns $tunnelName $hostname 2>&1 | Out-Null

    $credentialsFile = Join-Path $CloudflaredDir "$tunnelId.json"
    if (-not (Test-Path $credentialsFile)) {
        throw "Tunnel credentials not found at $credentialsFile"
    }

    $configText = @"
tunnel: $tunnelId
credentials-file: $credentialsFile
ingress:
  - hostname: $hostname
    service: http://127.0.0.1:$port
  - service: http_status:404
"@

    Set-Content -Path $CloudflaredConfig -Value $configText -Encoding UTF8
    Write-Host "  Wrote $CloudflaredConfig"
}

function Test-LocalHealth([string]$Port) {
    $uri = "http://127.0.0.1:$Port/health"
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $uri -TimeoutSec 3
            if ($response.status -eq "healthy") {
                Write-Host "  OK: $uri"
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    throw "Middleware health check failed at $uri"
}

Ensure-Admin
Set-Location $RootDir

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Printer Middleware - One-Click Install" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Project: $RootDir"

Write-Step "Loading site configuration"
if (-not (Test-Path $SiteEnvPath)) {
    if (Test-Path $SiteEnvExample) {
        Copy-Item $SiteEnvExample $SiteEnvPath
        Write-Host "  Created config/site.env from example. Edit printer IPs before printing."
    } else {
        throw "Missing config/site.env and config/site.env.example"
    }
}

$settings = Read-SiteEnv $SiteEnvPath
$defaults = @{
    TUNNEL_NAME = "r10-print"
    PUBLIC_HOSTNAME = "r10-print.k95foods.com"
    PORT = "5001"
    HOST = "0.0.0.0"
    CORS_ORIGINS = "*"
}
foreach ($key in $defaults.Keys) {
    if (-not $settings.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($settings[$key])) {
        $settings[$key] = $defaults[$key]
    }
}

Write-Host "  Tunnel:   $($settings['TUNNEL_NAME'])"
Write-Host "  Public:   https://$($settings['PUBLIC_HOSTNAME'])"
Write-Host "  Port:     $($settings['PORT'])"

Write-Step "Printer configuration"
if (-not (Test-Path $PrintersPath)) {
    if (Test-Path $PrintersExample) {
        Copy-Item $PrintersExample $PrintersPath
        Write-Host "  Created config/printers.json from example."
        Write-Host "  IMPORTANT: Edit config/printers.json with real printer IP/port on this LAN."
    } else {
        throw "Missing config/printers.json"
    }
} else {
    Write-Host "  OK: config/printers.json exists"
}

Write-Step "Installing dependencies"
Ensure-Python
Ensure-Cloudflared
Ensure-Venv

$env:PORT = $settings["PORT"]
$env:HOST = $settings["HOST"]
$env:CORS_ORIGINS = $settings["CORS_ORIGINS"]

Write-Step "Installing PrinterMiddleware Windows service (auto-start + auto-restart)"
$middlewareInstaller = Join-Path $RootDir "install_middleware_service.bat"
if (-not (Test-Path $middlewareInstaller)) { throw "Missing $middlewareInstaller" }
& cmd.exe /c "`"$middlewareInstaller`" $($settings['PORT'])"
if ($LASTEXITCODE -ne 0) { throw "install_middleware_service.bat failed with exit code $LASTEXITCODE" }

Write-Step "Verifying middleware locally"
Test-LocalHealth -Port $settings["PORT"]

Write-Step "Configuring Cloudflare tunnel for $($settings['PUBLIC_HOSTNAME'])"
Ensure-CloudflareTunnel -Settings $settings

Write-Step "Installing cloudflared Windows service (auto-start on boot)"
$cloudflaredInstaller = Join-Path $RootDir "install_cloudflared_service.bat"
if (-not (Test-Path $cloudflaredInstaller)) { throw "Missing $cloudflaredInstaller" }
& cmd.exe /c "`"$cloudflaredInstaller`""
if ($LASTEXITCODE -ne 0) { throw "install_cloudflared_service.bat failed with exit code $LASTEXITCODE" }

Start-Sleep -Seconds 3
Write-Step "Final status"
Write-Host ""
sc.exe query PrinterMiddleware
Write-Host ""
sc.exe query Cloudflared

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Install complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Local:   http://127.0.0.1:$($settings['PORT'])/health"
Write-Host "  Public:  https://$($settings['PUBLIC_HOSTNAME'])/health"
Write-Host ""
Write-Host "  On every Windows boot:"
Write-Host "    - PrinterMiddleware starts automatically"
Write-Host "    - cloudflared starts automatically"
Write-Host "    - Both restart automatically after crash"
Write-Host ""
Write-Host "  Edit printers:  config\printers.json"
Write-Host "  Edit domain:    config\site.env  (then rerun install.bat)"
Write-Host ""
