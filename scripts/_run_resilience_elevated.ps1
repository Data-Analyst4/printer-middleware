$ErrorActionPreference = "Continue"
$log = "C:\Users\HP\Projects\printer-middleware\scripts\test_service_resilience.log"
try {
  & "C:\Users\HP\Projects\printer-middleware\scripts\test_service_resilience.ps1" *>&1 | Out-File -FilePath $log -Encoding utf8
  "EXIT=0" | Add-Content $log
  exit 0
} catch {
  $_ | Out-String | Out-File -FilePath $log -Append -Encoding utf8
  "EXIT=1" | Add-Content $log
  exit 1
}
