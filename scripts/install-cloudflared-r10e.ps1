# Install only CloudflaredR10E (middleware already running). Requires Administrator.
$ErrorActionPreference = "Stop"
$TargetDir = "C:\printer-middleware-r10e"
$LogsDir = Join-Path $TargetDir "logs"
$Nssm = Join-Path $TargetDir "nssm.exe"
$CfServiceName = "CloudflaredR10E"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$configPath = Join-Path $env:USERPROFILE ".cloudflared\config-r10e-printer.yml"
$credFile = Join-Path $env:USERPROFILE ".cloudflared\4bbd4b82-3985-498a-85bd-9b104e7b9155.json"
$log = Join-Path $LogsDir "install-cloudflared-r10e.log"

function Log([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m
    Add-Content -Path $log -Value $line
    Write-Host $line
}

New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
"" | Set-Content $log -Encoding ASCII

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $p = Start-Process powershell.exe -Verb RunAs -ArgumentList $arg -Wait -PassThru
    exit $p.ExitCode
}

if (-not (Test-Path $configPath)) { throw "Missing $configPath" }
if (-not (Test-Path $credFile)) { throw "Missing $credFile" }
if (-not (Test-Path $Nssm)) { throw "Missing $Nssm" }
if (-not (Test-Path $cf)) { throw "Missing $cf" }

$systemCfDir = "C:\Windows\System32\config\systemprofile\.cloudflared"
New-Item -ItemType Directory -Force -Path $systemCfDir | Out-Null
Copy-Item $credFile $systemCfDir -Force
Copy-Item $configPath $systemCfDir -Force
$certPath = Join-Path $env:USERPROFILE ".cloudflared\cert.pem"
if (Test-Path $certPath) { Copy-Item $certPath $systemCfDir -Force -ErrorAction SilentlyContinue }
icacls (Join-Path $env:USERPROFILE ".cloudflared") /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
icacls $systemCfDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
Log "Synced credentials to SYSTEM profile"

# Stop temporary manual r10e cloudflared (user-session) if present
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*config-r10e-printer.yml*" } |
    ForEach-Object {
        Log "Stopping manual cloudflared PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

$prev = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $Nssm stop $CfServiceName 2>&1 | Out-Null
& $Nssm remove $CfServiceName confirm 2>&1 | Out-Null
sc.exe delete $CfServiceName 2>&1 | Out-Null
Start-Sleep -Seconds 1
$ErrorActionPreference = $prev

$cfArgs = "tunnel --no-autoupdate --config `"$configPath`" run"
& $Nssm install $CfServiceName $cf | Out-Null
& $Nssm set $CfServiceName AppParameters $cfArgs | Out-Null
& $Nssm set $CfServiceName AppDirectory $TargetDir | Out-Null
& $Nssm set $CfServiceName DisplayName "Cloudflared Tunnel R10E" | Out-Null
& $Nssm set $CfServiceName Description "Cloudflare tunnel for r10e-printer.k95foods.com" | Out-Null
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

foreach ($svc in @("PrinterMiddleware", "Cloudflared", "DominoPrinterMiddleware", "DominoCloudflared", "PrinterMiddlewareR10E")) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($s) { Log ("$svc = $($s.Status)") }
}

Log "EXIT=0"
exit 0
