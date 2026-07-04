# One-click setup: dependencies, middleware service, Cloudflare tunnel service.
# Run via install.bat (self-elevates to Administrator).

param(
    [switch]$SkipCloudflareLogin,
    [switch]$TunnelAndCloudflaredOnly
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
$HelpersPath = Join-Path $RootDir "scripts\install-helpers.ps1"
if (-not (Test-Path $HelpersPath)) {
    throw "Missing $HelpersPath"
}
. $HelpersPath

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
    if ($TunnelAndCloudflaredOnly) { $argList += "-TunnelAndCloudflaredOnly" }
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

function Test-Preflight {
    Write-Step "Preflight checks"

    if (-not (Test-IsAdmin)) {
        throw "Administrator privileges are required. Right-click install.bat and choose Run as administrator."
    }

    if (-not (Test-Path (Join-Path $RootDir "main.py"))) {
        throw "main.py was not found. Make sure you extracted the full ZIP into the install folder."
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warning "winget was not found. Python and cloudflared must already be installed manually."
        Write-Warning "Download Python: https://www.python.org/downloads/"
        Write-Warning "Download cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    } else {
        Write-Host "  OK: winget found"
    }

    try {
        Invoke-WebRequest -Uri "https://www.cloudflare.com" -UseBasicParsing -TimeoutSec 15 | Out-Null
        Write-Host "  OK: internet access"
    } catch {
        Write-Warning "Internet check failed. winget, Cloudflare login, and tunnel setup require internet."
    }
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
    $script:PythonExe = Ensure-PythonRuntime
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
    if (-not $script:PythonExe) {
        throw "Python executable was not resolved before virtual environment setup."
    }

    $venvDir = Join-Path $RootDir ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"

    if ((Test-Path $venvDir) -and -not (Test-Path $venvPython)) {
        Write-Host "  Removing incomplete virtual environment..."
        Remove-Item $venvDir -Recurse -Force
    }

    # Recreate venv if it was built from per-user Python (service cannot use it).
    if ((Test-Path $venvPython) -and -not (Test-VenvUsesMachinePython -VenvPython $venvPython)) {
        Write-Host "  Existing .venv uses per-user Python; recreating with machine-wide Python..."
        Remove-Item $venvDir -Recurse -Force
    }

    if (-not (Test-Path $venvPython)) {
        Write-Host "  Creating virtual environment with machine-wide Python..."
        $venvResult = Invoke-Python -PythonRef $script:PythonExe -ArgumentList @("-m", "venv", $venvDir)
        if ($venvResult.ExitCode -ne 0) {
            throw "Failed to create virtual environment: $($venvResult.Output)"
        }
    }

    if (-not (Test-Path $venvPython)) {
        throw "Virtual environment python was not created at $venvPython"
    }

    if (-not (Test-VenvUsesMachinePython -VenvPython $venvPython)) {
        throw "Virtual environment is still linked to per-user Python. Install Python for all users and rerun install.bat."
    }

    Write-Host "  Installing Python packages..."
    $pipUpgrade = Invoke-External -FilePath $venvPython -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
    if ($pipUpgrade.ExitCode -ne 0) {
        throw "Failed to upgrade pip: $($pipUpgrade.Output)"
    }

    $pipInstall = Invoke-External -FilePath $venvPython -ArgumentList @("-m", "pip", "install", "-r", (Join-Path $RootDir "requirements.txt"))
    if ($pipInstall.ExitCode -ne 0) {
        throw "Failed to install Python packages: $($pipInstall.Output)"
    }

    Write-Step "Granting Local System access to app folders"
    Grant-SystemProjectAccess -RootDir $RootDir
}

function Ensure-CloudflareTunnel {
    param([hashtable]$Settings)

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
        $loginResult = Invoke-Cloudflared @("tunnel", "login")
        if ($loginResult.ExitCode -ne 0) {
            throw "cloudflared tunnel login failed: $($loginResult.Output)"
        }
    }
    if (-not (Test-Path $certPath)) {
        throw "Cloudflare cert.pem missing. Run: cloudflared tunnel login"
    }

    $tunnelId = Get-TunnelIdByName -Name $tunnelName
    if (-not $tunnelId) {
        Write-Host "  Creating tunnel '$tunnelName'..."
        $createResult = Invoke-Cloudflared @("tunnel", "create", $tunnelName)
        if ($createResult.Output) {
            Write-Host "  $($createResult.Output)"
        }
        if ($createResult.ExitCode -ne 0) {
            throw "cloudflared tunnel create failed: $($createResult.Output)"
        }

        $tunnelId = Get-TunnelIdByName -Name $tunnelName
        if (-not $tunnelId -and $createResult.Output -match "([0-9a-f-]{36})") {
            $tunnelId = $Matches[1]
        }
        if (-not $tunnelId) {
            throw "Could not determine tunnel ID after create."
        }
    } else {
        Write-Host "  OK: tunnel '$tunnelName' exists ($tunnelId)"
    }

    Write-Host "  Ensuring DNS route $hostname ..."
    $dnsResult = Invoke-Cloudflared @("tunnel", "route", "dns", $tunnelName, $hostname)
    if ($dnsResult.Output) {
        Write-Host "  $($dnsResult.Output)"
    }
    if ($dnsResult.ExitCode -ne 0 -and $dnsResult.Output -notmatch "already exists|Record already exists|CNAME") {
        Write-Warning "DNS route may already exist or could not be updated automatically."
    }

    $credentialsFile = Join-Path $CloudflaredDir "$tunnelId.json"
    if (-not (Test-Path $credentialsFile)) {
        throw "Tunnel credentials not found at $credentialsFile"
    }

    $ingressRules = @(
        @{
            Hostname = $hostname
            Service = "http://127.0.0.1:$port"
        }
    )

    $hrConfigPath = Join-Path $CloudflaredDir "config-v8-middleware.yml"
    $hrRules = Read-IngressRules -Path $hrConfigPath | Where-Object { $_.Hostname -eq "v8-mw.k95foods.com" }
    foreach ($hrRule in $hrRules) {
        $existingHostnames = @($ingressRules | ForEach-Object { $_.Hostname })
        if ($existingHostnames -notcontains $hrRule.Hostname) {
            Write-Host "  Keeping HR middleware hostname in shared tunnel config: $($hrRule.Hostname)"
            $ingressRules += $hrRule
            $hrDnsResult = Invoke-Cloudflared @("tunnel", "route", "dns", $tunnelName, $hrRule.Hostname)
            if ($hrDnsResult.Output) {
                Write-Host "  $($hrDnsResult.Output)"
            }
        }
    }

    if (Test-Path $CloudflaredConfig) {
        $backupPath = "$CloudflaredConfig.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $CloudflaredConfig $backupPath -Force
        Write-Host "  Backed up previous config to $backupPath"
    }

    Write-TunnelConfig -Path $CloudflaredConfig -TunnelId $tunnelId -CredentialsFile $credentialsFile -IngressRules $ingressRules
    Write-Host "  Wrote $CloudflaredConfig"
}

function Show-ServiceLogs {
    param([string]$RootDir)

    $outputLog = Join-Path $RootDir "logs\service-output.log"
    $errorLog = Join-Path $RootDir "logs\service-error.log"

    foreach ($logPath in @($outputLog, $errorLog)) {
        if (Test-Path $logPath) {
            Write-Host ""
            Write-Host "--- Last 20 lines of $logPath ---" -ForegroundColor Yellow
            Get-Content $logPath -Tail 20 | ForEach-Object { Write-Host $_ }
        }
    }
}

function Test-LocalHealth {
    param(
        [string]$Port,
        [string]$RootDir
    )

    $uri = "http://127.0.0.1:$Port/health"

    Write-Host "  Ensuring PrinterMiddleware service is started..."
    sc.exe start PrinterMiddleware | Out-Null
    Start-Sleep -Seconds 5

    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $uri -TimeoutSec 5
            if ($response.status -eq "healthy") {
                Write-Host "  OK: $uri"
                return
            }
        } catch {
            $service = Get-Service -Name PrinterMiddleware -ErrorAction SilentlyContinue
            if ($service -and $service.Status -ne "Running") {
                sc.exe start PrinterMiddleware | Out-Null
            }
            Start-Sleep -Seconds 5
        }
    }

    Write-Host ""
    sc.exe query PrinterMiddleware
    Show-ServiceLogs -RootDir $RootDir
    throw "Middleware health check failed at $uri. Review the log lines above, then run: sc.exe start PrinterMiddleware"
}

function Initialize-InstallSettings {
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
    return $settings
}

function Finish-TunnelAndCloudflaredInstall {
    param([hashtable]$Settings)

    Write-Step "Configuring Cloudflare tunnel for $($Settings['PUBLIC_HOSTNAME'])"
    Ensure-CloudflareTunnel -Settings $Settings

    Write-Step "Syncing cloudflared config for Local System (fixes public 1033/530)"
    Sync-CloudflaredConfigForSystemService

    Stop-ManualCloudflaredProcesses

    Write-Step "Installing cloudflared Windows service (auto-start on boot)"
    $cloudflaredInstaller = Join-Path $RootDir "install_cloudflared_service.bat"
    if (-not (Test-Path $cloudflaredInstaller)) { throw "Missing $cloudflaredInstaller" }
    & cmd.exe /c "`"$cloudflaredInstaller`""
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "install_cloudflared_service.bat returned exit code $LASTEXITCODE. Attempting repair..."
    }

    Ensure-CloudflaredServiceHealthy -RootDir $RootDir

    Start-Sleep -Seconds 3
    Write-Step "Final status"
    Write-Host ""
    sc.exe query PrinterMiddleware
    Write-Host ""
    sc.exe query Cloudflared

    $verifyScript = Join-Path $RootDir "scripts\verify_production.ps1"
    if (Test-Path $verifyScript) {
        Write-Step "Running verification"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyScript -Port $Settings["PORT"] -Hostname $Settings["PUBLIC_HOSTNAME"]
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Verification reported issues. See INSTALL_GUIDE.md troubleshooting section."
        }
    }

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  Install complete" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Local:   http://127.0.0.1:$($Settings['PORT'])/health"
    Write-Host "  Public:  https://$($Settings['PUBLIC_HOSTNAME'])/health"
    Write-Host ""
    Write-Host "  On every Windows boot:"
    Write-Host "    - PrinterMiddleware starts automatically"
    Write-Host "    - cloudflared starts automatically"
    Write-Host "    - Both restart automatically after crash"
    Write-Host ""
    Write-Host "  Edit printers:  config\printers.json"
    Write-Host "  Edit domain:    config\site.env  (then rerun install.bat)"
    Write-Host ""
}

Ensure-Admin
Set-Location $RootDir

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
if ($TunnelAndCloudflaredOnly) {
    Write-Host "  Printer Middleware - Finish Tunnel Install" -ForegroundColor Green
} else {
    Write-Host "  Printer Middleware - One-Click Install" -ForegroundColor Green
}
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Project: $RootDir"

if (-not $TunnelAndCloudflaredOnly) {
    Test-Preflight
}

$settings = Initialize-InstallSettings

if ($TunnelAndCloudflaredOnly) {
    Write-Step "Verifying middleware locally"
    Test-LocalHealth -Port $settings["PORT"] -RootDir $RootDir
    Finish-TunnelAndCloudflaredInstall -Settings $settings
    exit 0
}

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
Test-LocalHealth -Port $settings["PORT"] -RootDir $RootDir

Finish-TunnelAndCloudflaredInstall -Settings $settings
exit 0

# Unreachable: Finish-TunnelAndCloudflaredInstall prints completion banner and exits above.
