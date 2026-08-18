$ErrorActionPreference = "Continue"
Start-Transcript -Path "C:\Users\HP\Projects\printer-middleware\logs\restart-middleware.log" -Force
Write-Host "Stopping PrinterMiddleware to close printer TCP sockets..."
nssm.exe stop PrinterMiddleware
Start-Sleep -Seconds 3
Write-Host "Starting PrinterMiddleware..."
nssm.exe start PrinterMiddleware
Start-Sleep -Seconds 3
sc.exe query PrinterMiddleware
try {
  $h = Invoke-WebRequest -Uri "http://127.0.0.1:5000/health" -UseBasicParsing -TimeoutSec 5
  Write-Host "HEALTH $($h.StatusCode) $($h.Content)"
} catch {
  Write-Host "HEALTH_FAIL $($_.Exception.Message)"
}
Stop-Transcript
