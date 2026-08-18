$ErrorActionPreference = "Continue"
$log = "C:\Users\HP\Projects\printer-middleware\scripts\setup_windows_service.log"
try {
  & "C:\Users\HP\Projects\printer-middleware\scripts\setup_windows_service.ps1" *>&1 | Out-File -FilePath $log -Encoding utf8
  "EXIT=0" | Add-Content $log
  exit 0
} catch {
  $_ | Out-String | Out-File -FilePath $log -Encoding utf8
  "EXIT=1" | Add-Content $log
  exit 1
}
