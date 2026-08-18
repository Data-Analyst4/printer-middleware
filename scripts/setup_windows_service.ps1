param(
    [string]$ServiceName = "PrinterMiddleware",
    [string]$DisplayName = "Printer Middleware",
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

function Get-PythonPath {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Python executable not found. Install Python and retry."
}

function Ensure-Nssm {
    $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssmCmd) {
        return $nssmCmd.Source
    }

    $localNssm = Join-Path $env:ProgramFiles "nssm\nssm.exe"
    if (Test-Path $localNssm) {
        return $localNssm
    }

    Write-Host "Installing NSSM via winget..." -ForegroundColor Cyan
    winget install --id NSSM.NSSM -e --accept-package-agreements --accept-source-agreements | Out-Host

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")

    $nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssmCmd) {
        return $nssmCmd.Source
    }

    # Common winget install location fallback
    $candidates = @(
        "$env:ProgramFiles\nssm\nssm.exe",
        "$env:ProgramFiles\NSSM\win64\nssm.exe",
        "${env:ProgramFiles(x86)}\nssm\nssm.exe",
        "${env:ProgramFiles(x86)}\NSSM\win64\nssm.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "NSSM not found after install. Install NSSM manually and retry."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$mainPath = Join-Path $repoRoot "main.py"
$logsDir = Join-Path $repoRoot "logs"

if (-not (Test-Path $mainPath)) {
    throw "main.py not found at $mainPath"
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$pythonPath = Get-PythonPath
$nssmPath = Ensure-Nssm

Write-Host "Configuring service '$ServiceName' with NSSM..." -ForegroundColor Cyan

# Stop leftover middleware processes that are not service-managed.
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like "*printer-middleware*main.py*" } |
    ForEach-Object {
        Write-Host "Stopping leftover PID $($_.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$prevEap = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $nssmPath stop $ServiceName confirm | Out-Null
Start-Sleep -Seconds 2
& $nssmPath remove $ServiceName confirm | Out-Null
Start-Sleep -Seconds 2
# Also remove any prior non-NSSM service with same name.
sc.exe stop $ServiceName | Out-Null
sc.exe delete $ServiceName | Out-Null
Start-Sleep -Seconds 2
$ErrorActionPreference = $prevEap

& $nssmPath install $ServiceName $pythonPath $mainPath --host $BindHost --port $Port | Out-Host
& $nssmPath set $ServiceName DisplayName $DisplayName | Out-Host
& $nssmPath set $ServiceName Description "Printer middleware API service" | Out-Host
& $nssmPath set $ServiceName AppDirectory $repoRoot | Out-Host
& $nssmPath set $ServiceName Start SERVICE_AUTO_START | Out-Host
& $nssmPath set $ServiceName AppStdout (Join-Path $logsDir "middleware.out.log") | Out-Host
& $nssmPath set $ServiceName AppStderr (Join-Path $logsDir "middleware.err.log") | Out-Host
& $nssmPath set $ServiceName AppRotateFiles 1 | Out-Host
& $nssmPath set $ServiceName AppExit Default Restart | Out-Host
& $nssmPath set $ServiceName AppRestartDelay 5000 | Out-Host

# Windows recovery actions as an extra safety net.
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/10000/restart/30000 | Out-Host
sc.exe failureflag $ServiceName 1 | Out-Host
sc.exe config $ServiceName start= delayed-auto | Out-Host

& $nssmPath start $ServiceName | Out-Host
Start-Sleep -Seconds 5
sc.exe query $ServiceName | Out-Host

Write-Host "Validating health endpoint..." -ForegroundColor Cyan
Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 10 |
    Select-Object -ExpandProperty Content | Out-Host

Write-Host "Service setup complete." -ForegroundColor Green
