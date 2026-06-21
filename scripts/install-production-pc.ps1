# Production PC one-shot install (Admin PowerShell).
# Prerequisites: extract repo ZIP to C:\printer-middleware first.
# Turn OFF Windows Store python.exe / python3.exe aliases before running
# (Settings -> Apps -> App execution aliases).

#Requires -RunAsAdministrator

param(
    [string]$AppDir = "C:\printer-middleware",
    [string]$TunnelName = "r10-printer",
    [string]$Hostname = "r10-printer.k95foods.com",
    [int]$Port = 5001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Error $Message
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Printer Middleware - Production PC Full Install" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Folder:   $AppDir"
Write-Host "  Port:     $Port"
Write-Host "  Tunnel:   $TunnelName"
Write-Host "  Public:   https://$Hostname"
Write-Host ""

if (-not (Test-Path $AppDir)) {
    Fail "Folder not found: $AppDir`nExtract the GitHub ZIP to C:\printer-middleware first."
}

if (-not (Test-Path (Join-Path $AppDir "main.py"))) {
    Fail "main.py not found in $AppDir. Extract the full project ZIP first."
}

Set-Location $AppDir

$HelpersPath = Join-Path $AppDir "scripts\install-helpers.ps1"
if (-not (Test-Path $HelpersPath)) {
    Fail "Missing $HelpersPath. Download latest develop ZIP from GitHub."
}
. $HelpersPath

Write-Step "Checking Windows Store Python aliases"
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd -and (Test-IsWindowsStorePythonStub -Path $pythonCmd.Source)) {
    Fail @"
Windows Store python alias is still ON.

Fix manually, then rerun this script:
  Settings -> Apps -> Advanced app settings -> App execution aliases
  Turn OFF: python.exe and python3.exe
"@
}

Write-Step "Installing / verifying Python 3.11"
$pythonExe = Ensure-PythonRuntime
Write-Host "  Using: $pythonExe"

Write-Step "Installing / verifying cloudflared"
$cloudflaredExe = Resolve-CloudflaredPath -AllowMissing
if (-not $cloudflaredExe) {
    Write-Host "  Installing cloudflared via winget..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail "cloudflared not found and winget unavailable. Install cloudflared manually."
    }
    $winget = Invoke-External -FilePath "winget" -ArgumentList @(
        "install", "--id", "Cloudflare.cloudflared", "-e",
        "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity"
    )
    if ($winget.Output) { Write-Host $winget.Output }
    Start-Sleep -Seconds 3
    Refresh-SessionPath
    $cloudflaredExe = Resolve-CloudflaredPath
}
Write-Host "  Using: $cloudflaredExe"
$env:Path = "$(Split-Path -Parent $cloudflaredExe);$env:Path"

Write-Step "Creating virtual environment and installing packages"
$venvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if ((Test-Path (Join-Path $AppDir ".venv")) -and -not (Test-Path $venvPython)) {
    Remove-Item (Join-Path $AppDir ".venv") -Recurse -Force
}
if (-not (Test-Path $venvPython)) {
    $venvResult = Invoke-Python -PythonRef $pythonExe -ArgumentList @("-m", "venv", (Join-Path $AppDir ".venv"))
    if ($venvResult.ExitCode -ne 0) {
        Fail "Failed to create venv: $($venvResult.Output)"
    }
}
$pipInstall = Invoke-External -FilePath $venvPython -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
if ($pipInstall.ExitCode -ne 0) { Fail "pip upgrade failed: $($pipInstall.Output)" }
$reqInstall = Invoke-External -FilePath $venvPython -ArgumentList @("-m", "pip", "install", "-r", (Join-Path $AppDir "requirements.txt"))
if ($reqInstall.ExitCode -ne 0) { Fail "pip install requirements failed: $($reqInstall.Output)" }
Write-Host "  OK: packages installed"

Write-Step "Site configuration"
$siteEnv = Join-Path $AppDir "config\site.env"
$siteExample = Join-Path $AppDir "config\site.env.example"
if (-not (Test-Path $siteEnv) -and (Test-Path $siteExample)) {
    Copy-Item $siteExample $siteEnv
}
if (-not (Test-Path $siteEnv)) {
    @"
SITE_NAME=R10
TUNNEL_NAME=$TunnelName
PUBLIC_HOSTNAME=$Hostname
PORT=$Port
HOST=0.0.0.0
CORS_ORIGINS=*
"@ | Set-Content $siteEnv -Encoding UTF8
}
Write-Host "  Edit printer IPs in config\printers.json before go-live."

$printersJson = Join-Path $AppDir "config\printers.json"
$printersExample = Join-Path $AppDir "config\printers.json.example"
if (-not (Test-Path $printersJson) -and (Test-Path $printersExample)) {
    Copy-Item $printersExample $printersJson
}

Write-Step "Testing Python import"
$importTest = Invoke-External -FilePath $venvPython -ArgumentList @("-c", "import main; print('import ok')")
if ($importTest.ExitCode -ne 0) {
    Fail "App import failed: $($importTest.Output)"
}
Write-Host "  $($importTest.Output)"

Write-Step "Installing PrinterMiddleware Windows service"
$middlewareBat = Join-Path $AppDir "install_middleware_service.bat"
if (-not (Test-Path $middlewareBat)) { Fail "Missing $middlewareBat" }
& cmd.exe /c "`"$middlewareBat`" $Port"
if ($LASTEXITCODE -ne 0) { Fail "install_middleware_service.bat failed with exit code $LASTEXITCODE" }

Start-Sleep -Seconds 5
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 15
    if ($health.status -ne "healthy") { Fail "Local health returned: $($health.status)" }
    Write-Host "  OK: http://127.0.0.1:$Port/health"
} catch {
    Fail "Local health check failed. Check logs\service-error.log"
}

Write-Step "Setting up Cloudflare tunnel + Cloudflared service"
$tunnelScript = Join-Path $AppDir "scripts\setup-production-tunnel.ps1"
if (-not (Test-Path $tunnelScript)) { Fail "Missing $tunnelScript" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tunnelScript -TunnelName $TunnelName -Hostname $Hostname -Port $Port
if ($LASTEXITCODE -ne 0) { Fail "setup-production-tunnel.ps1 failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Install complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Local:   http://127.0.0.1:$Port/health"
Write-Host "  Public:  https://$Hostname/health"
Write-Host ""
Write-Host "  Services:"
sc.exe query PrinterMiddleware
Write-Host ""
sc.exe query Cloudflared
Write-Host ""

exit 0
