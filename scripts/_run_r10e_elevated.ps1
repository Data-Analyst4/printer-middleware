$ErrorActionPreference = "Continue"
$log = "C:\printer-middleware-r10e\logs\install-r10e-elevated.log"
New-Item -ItemType Directory -Force -Path "C:\printer-middleware-r10e\logs" | Out-Null
try {
  & "C:\Users\HP\Projects\printer-middleware\scripts\install-r10e-full.ps1" `
    -TargetDir "C:\printer-middleware-r10e" `
    -SourceDir "C:\Users\HP\Projects\printer-middleware" `
    -Hostname "r10e-printer.k95foods.com" `
    -TunnelName "r10e-printer" `
    -Port 5004 `
    -SkipCopy `
    *>&1 | Out-File -FilePath $log -Encoding utf8
  "EXIT=$LASTEXITCODE" | Add-Content $log
  exit $LASTEXITCODE
} catch {
  $_ | Out-String | Out-File -FilePath $log -Append -Encoding utf8
  "EXIT=1" | Add-Content $log
  exit 1
}
