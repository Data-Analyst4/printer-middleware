$ErrorActionPreference = "Continue"
$log = "C:\printer-middleware\logs\restart-printermiddleware.log"
Start-Transcript -Path $log -Force
$nssm = "C:\printer-middleware\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "nssm" }
Write-Host "Restarting PrinterMiddleware ..."
& $nssm restart PrinterMiddleware
Start-Sleep -Seconds 4
sc.exe query PrinterMiddleware
try {
  $v = Invoke-WebRequest -Uri "http://127.0.0.1:5000/version" -UseBasicParsing -TimeoutSec 8
  Write-Host "VERSION $($v.Content)"
} catch {
  Write-Host "VERSION_FAIL $($_.Exception.Message)"
}
Stop-Transcript
