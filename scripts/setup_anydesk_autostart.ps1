# Install AnyDesk system-wide and enable auto-start on boot + lock screen.
# Requires Administrator. Prefer: setup_anydesk_autostart.bat
#
# Portable / Startup-folder AnyDesk only runs after a user logs in.
# A proper install with --start-with-win registers the Windows service so
# AnyDesk is available at power-on and on the lock / sign-in screen.

param(
    [string]$InstallerPath = "",
    [string]$InstallDir = "${env:ProgramFiles(x86)}\AnyDesk",
    [string]$UnattendedPassword = "",
    [switch]$SkipPasswordPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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
    if ($InstallerPath) { $argList += @("-InstallerPath", "`"$InstallerPath`"") }
    if ($InstallDir) { $argList += @("-InstallDir", "`"$InstallDir`"") }
    if ($UnattendedPassword) { $argList += @("-UnattendedPassword", "`"$UnattendedPassword`"") }
    if ($SkipPasswordPrompt) { $argList += "-SkipPasswordPrompt" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -WorkingDirectory (Split-Path -Parent $PSCommandPath)
    exit 0
}

function Find-AnyDeskInstaller {
    param([string]$Preferred)

    if ($Preferred -and (Test-Path $Preferred)) {
        return (Resolve-Path $Preferred).Path
    }

    $candidates = @(
        "$env:USERPROFILE\Downloads\AnyDesk.exe",
        "$env:USERPROFILE\Desktop\AnyDesk.exe",
        "$PSScriptRoot\..\AnyDesk.exe",
        "$InstallDir\AnyDesk.exe"
    )

    foreach ($path in $candidates) {
        if (Test-Path $path) {
            return (Resolve-Path $path).Path
        }
    }

    return $null
}

function Find-InstalledAnyDesk {
    $candidates = @(
        "$InstallDir\AnyDesk.exe",
        "${env:ProgramFiles(x86)}\AnyDesk\AnyDesk.exe",
        "$env:ProgramFiles\AnyDesk\AnyDesk.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }

    $svc = Get-CimInstance Win32_Service -Filter "Name='AnyDesk'" -ErrorAction SilentlyContinue
    if ($svc -and $svc.PathName -match '"([^"]+AnyDesk\.exe)"') {
        $exe = $Matches[1]
        if (Test-Path $exe) { return $exe }
    }
    return $null
}

function Get-AnyDeskService {
    Get-Service -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "*anydesk*" -or $_.DisplayName -like "*AnyDesk*"
    } | Select-Object -First 1
}

function Remove-UserStartupShortcut {
    $startupDirs = @(
        "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
        "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
    )
    foreach ($dir in $startupDirs) {
        if (-not (Test-Path $dir)) { continue }
        Get-ChildItem $dir -Filter "*AnyDesk*" -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "Removing user Startup shortcut: $($_.FullName)" -ForegroundColor Yellow
            Remove-Item $_.FullName -Force
        }
    }
}

function Wait-ForService {
    param(
        [int]$Seconds = 20
    )
    for ($i = 0; $i -lt $Seconds; $i++) {
        $svc = Get-AnyDeskService
        if ($svc) { return $svc }
        Start-Sleep -Seconds 1
    }
    return $null
}

Ensure-Admin

Write-Step "Locating AnyDesk"
$installer = Find-AnyDeskInstaller -Preferred $InstallerPath
$installed = Find-InstalledAnyDesk

if (-not $installer -and -not $installed) {
    throw "AnyDesk.exe not found. Place it in Downloads (or pass -InstallerPath) and retry."
}

if ($installer) {
    Write-Host "Installer: $installer"
} else {
    Write-Host "Already installed: $installed"
}

Write-Step "Installing AnyDesk with Windows service auto-start"
# --start-with-win registers the background service used before login / on lock screen.
# Use a single ArgumentList string so paths with spaces are not split by Start-Process.
if ($installer -and (-not $installed -or ($installer -ne $installed))) {
    $argString = "--install `"$InstallDir`" --start-with-win --create-shortcuts --create-desktop-icon --silent"
    if (Get-AnyDeskService) {
        $argString = "--install `"$InstallDir`" --start-with-win --create-shortcuts --create-desktop-icon --remove-first --silent"
    }
    Write-Host "Running: `"$installer`" $argString"
    $proc = Start-Process -FilePath $installer -ArgumentList $argString -Wait -PassThru
    if ($null -ne $proc.ExitCode -and $proc.ExitCode -ne 0) {
        Write-Host "Installer exit code: $($proc.ExitCode) (continuing to verify service)" -ForegroundColor Yellow
    }
} elseif ($installed) {
    Write-Host "Re-applying start-with-win on existing install..."
    $argString = "--install `"$InstallDir`" --start-with-win --silent"
    Start-Process -FilePath $installed -ArgumentList $argString -Wait | Out-Null
}

$anydeskExe = Find-InstalledAnyDesk
if (-not $anydeskExe) {
    throw "AnyDesk did not install to $InstallDir. Install manually, then re-run this script."
}
Write-Host "Installed binary: $anydeskExe"

Write-Step "Ensuring AnyDesk Windows service is Automatic + Running"
$svc = Wait-ForService -Seconds 25
if (-not $svc) {
    # Some builds need an explicit service start after silent install.
    & $anydeskExe --start-service 2>$null
    & $anydeskExe --restart-service 2>$null
    $svc = Wait-ForService -Seconds 15
}

if (-not $svc) {
    throw "AnyDesk service not found after install. Open AnyDesk once as Admin and choose 'Install AnyDesk on this computer'."
}

Write-Host "Service: $($svc.Name) ($($svc.DisplayName))"
Set-Service -Name $svc.Name -StartupType Automatic
if ($svc.Status -ne "Running") {
    Start-Service -Name $svc.Name
}
& $anydeskExe --restart-service 2>$null
Start-Sleep -Seconds 2
$svc = Get-Service -Name $svc.Name
Write-Host "Status: $($svc.Status), StartType: $((Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'").StartMode)"

Write-Step "Cleaning portable Startup shortcut (service replaces it)"
Remove-UserStartupShortcut

Write-Step "Unattended access (needed for lock-screen remote control)"
$passwordToSet = $UnattendedPassword
if (-not $passwordToSet -and -not $SkipPasswordPrompt) {
    $secure = Read-Host "Set AnyDesk unattended access password (Enter to skip)" -AsSecureString
    if ($secure.Length -gt 0) {
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $passwordToSet = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

if ($passwordToSet) {
    $passwordToSet | & $anydeskExe --set-password
    Write-Host "Unattended access password set." -ForegroundColor Green
} else {
    Write-Host "Skipped. In AnyDesk go to Settings > Security > enable unattended access and set a password." -ForegroundColor Yellow
}

Write-Step "AnyDesk ID"
try {
    $id = & $anydeskExe --get-id 2>$null
    if ($id) {
        Write-Host "This PC AnyDesk ID: $id" -ForegroundColor Green
    }
} catch {
    Write-Host "Could not read AnyDesk ID yet (open AnyDesk once if blank)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done. AnyDesk should now:" -ForegroundColor Green
Write-Host "  - Start when the PC powers on (Windows service)"
Write-Host "  - Stay available on the lock / sign-in screen"
Write-Host "  - Accept unattended connections if a password was set"
Write-Host ""
Write-Host "Tip: In Windows Settings > Accounts > Sign-in options, you can also turn on"
Write-Host "'Use my sign-in info to automatically finish setting up after an update' if needed."
Write-Host "For remote unlock, unattended access password is required."
