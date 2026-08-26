$ErrorActionPreference = "Continue"
$log = "C:\printer-middleware-r10e\logs\restart-r10e.log"
Start-Transcript -Path $log -Force
$nssm = "C:\printer-middleware-r10e\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "nssm" }
Write-Host "Restarting PrinterMiddlewareR10E ..."
& $nssm restart PrinterMiddlewareR10E
Start-Sleep -Seconds 4
sc.exe query PrinterMiddlewareR10E
try {
  $v = Invoke-WebRequest -Uri "http://127.0.0.1:5004/version" -UseBasicParsing -TimeoutSec 8
  Write-Host "VERSION $($v.Content)"
} catch {
  Write-Host "VERSION_FAIL $($_.Exception.Message)"
}
Stop-Transcript
