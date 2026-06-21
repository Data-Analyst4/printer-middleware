param(
    [string]$TargetDir = "C:\printer-middleware",
    [string]$ZipUrl = "https://github.com/Data-Analyst4/printer-middleware/archive/refs/heads/develop.zip"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

$tempRoot = Join-Path $env:TEMP "printer-middleware-download"
$zipPath = Join-Path $tempRoot "develop.zip"
$extractRoot = Join-Path $tempRoot "extract"

Write-Host "Downloading from $ZipUrl ..."

if (Test-Path $tempRoot) {
    Remove-Item $tempRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
New-Item -ItemType Directory -Path $extractRoot -Force | Out-Null

try {
    Invoke-WebRequest -Uri $ZipUrl -OutFile $zipPath -UseBasicParsing
} catch {
    Fail "Download failed: $($_.Exception.Message)"
}

Write-Host "Extracting..."
Expand-Archive -Path $zipPath -DestinationPath $extractRoot -Force

$extractedFolder = Get-ChildItem -Path $extractRoot -Directory | Select-Object -First 1
if (-not $extractedFolder) {
    Fail "Downloaded archive did not contain a folder."
}

if (Test-Path $TargetDir) {
    $backupDir = "$TargetDir-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Write-Host "Target exists. Moving old folder to $backupDir"
    Move-Item -Path $TargetDir -Destination $backupDir
}

Move-Item -Path $extractedFolder.FullName -Destination $TargetDir

$printersExample = Join-Path $TargetDir "config\printers.json.example"
$printersPath = Join-Path $TargetDir "config\printers.json"
if (-not (Test-Path $printersPath) -and (Test-Path $printersExample)) {
    Copy-Item $printersExample $printersPath
    Write-Host "Created config\printers.json from example."
}

Write-Host "Done. Files are in $TargetDir"
exit 0
