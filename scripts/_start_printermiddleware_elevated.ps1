$ErrorActionPreference = "Continue"
$log = "C:\printer-middleware\logs\restart-printermiddleware.log"
Start-Transcript -Path $log -Append
$nssm = "C:\printer-middleware\nssm.exe"
if (-not (Test-Path $nssm)) { $nssm = "nssm" }
Write-Host "PrinterMiddleware current state:"
sc.exe query PrinterMiddleware
Write-Host "nssm continue ..."
& $nssm continue PrinterMiddleware
Start-Sleep -Seconds 2
Write-Host "nssm start ..."
& $nssm start PrinterMiddleware
Start-Sleep -Seconds 4
sc.exe query PrinterMiddleware
try {
  $v = Invoke-WebRequest -Uri "http://127.0.0.1:5000/version" -UseBasicParsing -TimeoutSec 8
  Write-Host "VERSION $($v.Content)"
} catch {
  Write-Host "VERSION_FAIL $($_.Exception.Message)"
  Write-Host "nssm restart ..."
  & $nssm restart PrinterMiddleware
  Start-Sleep -Seconds 5
  sc.exe query PrinterMiddleware
  try {
    $v2 = Invoke-WebRequest -Uri "http://127.0.0.1:5000/version" -UseBasicParsing -TimeoutSec 8
    Write-Host "VERSION $($v2.Content)"
  } catch {
    Write-Host "VERSION_FAIL2 $($_.Exception.Message)"
  }
}
Stop-Transcript
