$ErrorActionPreference = "Continue"
$src = "C:\Users\HP\Projects\printer-middleware"
$dst = "C:\printer-middleware"
$nssm = "C:\Users\HP\AppData\Local\Microsoft\WinGet\Links\nssm.exe"
$py = "C:\Users\HP\AppData\Local\Programs\Python\Python312\python.exe"
$log = "C:\printer-middleware-move.log"

function Log($m) { $line = "$(Get-Date -Format o) $m"; Add-Content -Path $log -Value $line; Write-Host $line }

try {
  Log "Stopping PrinterMiddleware..."
  & $nssm stop PrinterMiddleware confirm 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 3
  sc.exe stop PrinterMiddleware 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 2

  # Kill leftover python processes running main.py from old path
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine -like "*printer-middleware*main.py*"
  } | ForEach-Object {
    Log "Killing leftover PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

  Log "Removing old service..."
  & $nssm remove PrinterMiddleware confirm 2>&1 | Out-String | ForEach-Object { Log $_ }
  sc.exe delete PrinterMiddleware 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 2

  if (Test-Path $dst) {
    Log "Destination already exists: $dst — removing it first"
    Remove-Item -LiteralPath $dst -Recurse -Force -ErrorAction Stop
  }

  Log "Copying $src -> $dst"
  New-Item -ItemType Directory -Path $dst -Force | Out-Null
  # robocopy is more reliable with locked/long paths
  $rc = Start-Process -FilePath robocopy -ArgumentList @($src, $dst, '/E', '/COPY:DAT', '/R:2', '/W:2', '/NFL', '/NDL', '/NP') -Wait -PassThru -NoNewWindow
  Log "robocopy exit=$($rc.ExitCode)"
  if ($rc.ExitCode -ge 8) { throw "robocopy failed with code $($rc.ExitCode)" }

  if (-not (Test-Path (Join-Path $dst 'main.py'))) { throw "main.py missing after copy" }

  # Grant SYSTEM access
  icacls $dst /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
  $logs = Join-Path $dst 'logs'
  if (-not (Test-Path $logs)) { New-Item -ItemType Directory -Path $logs -Force | Out-Null }
  $db = Join-Path $dst 'app\db'
  if (-not (Test-Path $db)) { New-Item -ItemType Directory -Path $db -Force | Out-Null }

  Log "Installing service from new location..."
  & $nssm install PrinterMiddleware $py
  & $nssm set PrinterMiddleware AppParameters "$dst\main.py --host 0.0.0.0 --port 5000"
  & $nssm set PrinterMiddleware DisplayName "Printer Middleware"
  & $nssm set PrinterMiddleware Description "Printer middleware API for remote web apps and printer communication"
  & $nssm set PrinterMiddleware AppDirectory $dst
  & $nssm set PrinterMiddleware Start SERVICE_DELAYED_AUTO_START
  & $nssm set PrinterMiddleware AppStdout "$logs\service-output.log"
  & $nssm set PrinterMiddleware AppStderr "$logs\service-error.log"
  & $nssm set PrinterMiddleware AppRotateFiles 1
  & $nssm set PrinterMiddleware AppRotateOnline 1
  & $nssm set PrinterMiddleware AppRotateBytes 10485760
  & $nssm set PrinterMiddleware AppNoConsole 1
  & $nssm set PrinterMiddleware AppExit Default Restart
  & $nssm set PrinterMiddleware AppRestartDelay 5000
  & $nssm set PrinterMiddleware AppThrottle 1500
  & $nssm set PrinterMiddleware AppEnvironmentExtra "PYTHONUNBUFFERED=1" "HOST=0.0.0.0" "PORT=5000" "CORS_ORIGINS=*" "PRINTER_READ_TIMEOUT=5" "PRINTER_FIRE_AND_FORGET=false"
  sc.exe failure PrinterMiddleware reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
  sc.exe failureflag PrinterMiddleware 1 | Out-Null

  Log "Starting service..."
  sc.exe start PrinterMiddleware 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 4
  $svc = Get-Service PrinterMiddleware -ErrorAction SilentlyContinue
  Log "Service status: $($svc.Status)"
  Log "AppDirectory now: $((& $nssm get PrinterMiddleware AppDirectory))"

  # Try remove old folder (may fail if Cursor has it locked)
  Log "Attempting to remove old folder $src"
  try {
    Remove-Item -LiteralPath $src -Recurse -Force -ErrorAction Stop
    Log "Old folder removed."
  } catch {
    Log "Could not remove old folder (likely locked by Cursor/IDE): $($_.Exception.Message)"
    Log "You can delete C:\Users\HP\Projects\printer-middleware manually after closing Cursor."
  }

  Log "DONE OK"
} catch {
  Log "FAILED: $($_.Exception.Message)"
  exit 1
}
