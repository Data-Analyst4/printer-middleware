function Test-IsWindowsStorePythonStub {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    return ($Path -match "\\WindowsApps\\python\.exe$" -or $Path -match "\\WindowsApps\\PythonSoftwareFoundation")
}

function Test-RealPythonExecutable {
    param([string]$Path)

    if (-not $Path -or -not (Test-Path $Path)) {
        return $false
    }

    if (Test-IsWindowsStorePythonStub -Path $Path) {
        return $false
    }

    $result = Invoke-External -FilePath $Path -ArgumentList @("--version")
    return ($result.ExitCode -eq 0 -and $result.Output -match "Python 3\.")
}

function Resolve-PythonPath {
    $candidatePaths = @(
        "$env:LocalAppData\Programs\Python\Python313\python.exe",
        "$env:LocalAppData\Programs\Python\Python312\python.exe",
        "$env:LocalAppData\Programs\Python\Python311\python.exe",
        "$env:LocalAppData\Programs\Python\Python310\python.exe",
        "C:\Program Files\Python313\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-RealPythonExecutable -Path $candidate) {
            return $candidate
        }
    }

    Refresh-SessionPath

    foreach ($commandName in @("python", "python3")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and (Test-RealPythonExecutable -Path $command.Source)) {
            return $command.Source
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        foreach ($versionArg in @("-3.13", "-3.12", "-3.11", "-3.10")) {
            $result = Invoke-External -FilePath $pyLauncher.Source -ArgumentList @($versionArg, "--version")
            if ($result.ExitCode -eq 0) {
                return "$($pyLauncher.Source)|$versionArg"
            }
        }
    }

    return $null
}

function Invoke-Python {
    param(
        [string]$PythonRef,
        [string[]]$ArgumentList
    )

    if ($PythonRef -match "\|") {
        $parts = $PythonRef -split "\|", 2
        return Invoke-External -FilePath $parts[0] -ArgumentList @($parts[1]) + $ArgumentList
    }

    return Invoke-External -FilePath $PythonRef -ArgumentList $ArgumentList
}

function Ensure-PythonRuntime {
    $python = Resolve-PythonPath
    if ($python) {
        Write-Host "  OK: python found at $python"
        return $python
    }

    $stub = Get-Command python -ErrorAction SilentlyContinue
    if ($stub -and (Test-IsWindowsStorePythonStub -Path $stub.Source)) {
        Write-Host "  Detected Windows Store python alias (not a real install)."
        Write-Host "  Installing Python 3.11..."
    } else {
        Write-Host "  Python not found. Installing Python 3.11..."
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Real Python was not found. Install Python 3.11 from https://www.python.org/downloads/ and check 'Add python.exe to PATH', then rerun install.bat"
    }

    $installResult = Invoke-External -FilePath "winget" -ArgumentList @(
        "install",
        "--id", "Python.Python.3.11",
        "-e",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity"
    )
    if ($installResult.Output) {
        Write-Host $installResult.Output
    }

    Start-Sleep -Seconds 3
    Refresh-SessionPath

    $python = Resolve-PythonPath
    if (-not $python) {
        throw "Python is still unavailable after install attempt. Install Python 3.11 manually, disable Settings > Apps > Advanced app settings > App execution aliases for python.exe, then rerun install.bat"
    }

    Write-Host "  OK: python found at $python"
    return $python
}

function Refresh-SessionPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Invoke-External {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $output = & $FilePath @ArgumentList 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.ToString()
            } else {
                $_
            }
        }
        return @{
            ExitCode = $LASTEXITCODE
            Output = ($output | Out-String).Trim()
        }
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Invoke-Cloudflared {
    param([string[]]$ArgumentList)

    $cloudflaredPath = Resolve-CloudflaredPath -AllowMissing
    if (-not $cloudflaredPath) {
        return @{
            ExitCode = 1
            Output = "cloudflared executable not found"
        }
    }

    return Invoke-External -FilePath $cloudflaredPath -ArgumentList $ArgumentList
}

function Resolve-CloudflaredPath {
    param([switch]$AllowMissing)

    $candidates = @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:ProgramData\chocolatey\bin\cloudflared.exe"
    )

    Refresh-SessionPath

    if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
        return (Get-Command cloudflared -ErrorAction Stop).Source
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $parent = Split-Path -Parent $candidate
            if ($env:Path -notlike "*$parent*") {
                $env:Path = "$parent;$env:Path"
            }
            return $candidate
        }
    }

    $whereOutput = & where.exe cloudflared 2>$null | Select-Object -First 1
    if ($whereOutput -and (Test-Path $whereOutput)) {
        return $whereOutput
    }

    if ($AllowMissing) {
        return $null
    }

    throw "cloudflared executable not found. Install with: winget install Cloudflare.cloudflared"
}

function Find-InstalledExecutable {
    param(
        [string]$Name,
        [string[]]$CandidatePaths
    )

    Refresh-SessionPath

    if ($Name -eq "cloudflared") {
        $resolved = Resolve-CloudflaredPath -AllowMissing
        if ($resolved) {
            return $resolved
        }
    }

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

    $whereOutput = & where.exe $Name 2>$null | Select-Object -First 1
    if ($whereOutput -and (Test-Path $whereOutput)) {
        return $whereOutput
    }

    return $null
}

function Stop-ManualCloudflaredProcesses {
    $processes = Get-Process -Name cloudflared -ErrorAction SilentlyContinue
    if (-not $processes) {
        return
    }

    Write-Host "  Stopping manual cloudflared process(es) before installing Windows service..."
    $processes | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

function Get-TunnelIdByName {
    param([string]$Name)

    $result = Invoke-Cloudflared @("tunnel", "list")
    foreach ($line in ($result.Output -split "`r?`n")) {
        if ($line -match "^([0-9a-f-]{36})\s+(\S+)") {
            if ($Matches[2] -eq $Name) {
                return $Matches[1]
            }
        }
    }

    return $null
}

function Read-IngressRules {
    param([string]$Path)

    $rules = @()
    $current = $null
    $inIngress = $false

    if (-not (Test-Path $Path)) {
        return $rules
    }

    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*ingress\s*:\s*$") {
            $inIngress = $true
            continue
        }

        if (-not $inIngress) {
            continue
        }

        if ($line -match "^\s*-\s*hostname\s*:\s*(.+?)\s*(?:#.*)?$") {
            if ($current) {
                $rules += $current
            }
            $current = @{
                Hostname = $Matches[1].Trim().Trim("'`"")
                Service = $null
            }
            continue
        }

        if ($line -match "^\s*(?:-\s*)?service\s*:\s*(.+?)\s*(?:#.*)?$") {
            $service = $Matches[1].Trim().Trim("'`"")
            if ($service -eq "http_status:404") {
                continue
            }
            if ($current) {
                $current.Service = $service
            }
        }
    }

    if ($current) {
        $rules += $current
    }

    return $rules | Where-Object { $_.Hostname -and $_.Service }
}

function Write-TunnelConfig {
    param(
        [string]$Path,
        [string]$TunnelId,
        [string]$CredentialsFile,
        [array]$IngressRules
    )

    $lines = @(
        "tunnel: $TunnelId",
        "credentials-file: $CredentialsFile",
        "ingress:"
    )

    foreach ($rule in $IngressRules) {
        $lines += "  - hostname: $($rule.Hostname)"
        $lines += "    service: $($rule.Service)"
    }

    $lines += "  - service: http_status:404"
    Set-Content -Path $Path -Value ($lines -join "`n") -Encoding UTF8
}

function Test-CloudflaredServiceRunning {
    $service = Get-Service -Name Cloudflared -ErrorAction SilentlyContinue
    return ($service -and $service.Status -eq "Running")
}

function Ensure-CloudflaredServiceHealthy {
    param([string]$RootDir)

    if (Test-CloudflaredServiceRunning) {
        Write-Host "  OK: Cloudflared service is RUNNING"
        return
    }

    Write-Host "  Cloudflared service is not RUNNING. Attempting automatic repair..." -ForegroundColor Yellow
    $finishScript = Join-Path $RootDir "finish_cloudflared_service.bat"
    if (-not (Test-Path $finishScript)) {
        throw "Cloudflared service is not running and finish_cloudflared_service.bat was not found."
    }

    & cmd.exe /c "`"$finishScript`""
    Start-Sleep -Seconds 3

    if (-not (Test-CloudflaredServiceRunning)) {
        throw "Cloudflared service is still not RUNNING. Run finish_cloudflared_service.bat as Administrator."
    }

    Write-Host "  OK: Cloudflared service recovered"
}
