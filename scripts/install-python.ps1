# Installs real Python 3.11 and verifies it is not the Windows Store stub.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-IsWindowsStorePythonStub {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    return ($Path -match "\\WindowsApps\\python\.exe$" -or $Path -match "\\WindowsApps\\PythonSoftwareFoundation")
}

function Test-RealPython {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path $Path)) { return $false }
    if (Test-IsWindowsStorePythonStub -Path $Path) { return $false }
    $output = & $Path --version 2>&1 | Out-String
    return ($LASTEXITCODE -eq 0 -and $output -match "Python 3\.")
}

function Find-RealPython {
    $paths = @(
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe"
    )
    foreach ($path in $paths) {
        if (Test-RealPython -Path $path) { return $path }
    }
    $discovered = Get-ChildItem -Path "$env:LocalAppData\Programs\Python" -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    foreach ($item in $discovered) {
        if (Test-RealPython -Path $item.FullName) { return $item.FullName }
    }
    return $null
}

Write-Host "Checking Python..."
$realPython = Find-RealPython
if ($realPython) {
    Write-Host "OK: Real Python already installed at $realPython"
    exit 0
}

$stub = Get-Command python -ErrorAction SilentlyContinue
if ($stub -and (Test-IsWindowsStorePythonStub -Path $stub.Source)) {
    Write-Host "Found Windows Store python stub at $($stub.Source)"
    Write-Host "This is NOT real Python."
}

Write-Host "Installing Python 3.11 via winget..."
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is not available. Install Python manually from https://www.python.org/downloads/"
}

& winget install Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --disable-interactivity
Start-Sleep -Seconds 5

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"

$realPython = Find-RealPython
if (-not $realPython) {
    Write-Host ""
    Write-Host "Python installed but not detected yet." -ForegroundColor Yellow
    Write-Host "Do this manually, then rerun fix-python-and-install.bat:" -ForegroundColor Yellow
    Write-Host "  Settings > Apps > Advanced app settings > App execution aliases"
    Write-Host "  Turn OFF python.exe and python3.exe"
    throw "Real Python still not found."
}

Write-Host "OK: Real Python ready at $realPython"
exit 0
