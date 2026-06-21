param(
    [string]$TunnelName = "r10-print",
    [string]$Hostname = "r10-print.k95foods.com",
    [int]$Port = 5001,
    [string]$ConfigPath = "$env:USERPROFILE\.cloudflared\config.yml",
    [string]$PrintConfigPath = "$env:USERPROFILE\.cloudflared\config-r10-print.yml",
    [switch]$IncludeHrMiddleware
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

function Invoke-Cloudflared {
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $output = & cloudflared @args 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.ToString()
            } else {
                $_
            }
        }
        return @{
            ExitCode = $LASTEXITCODE
            Output = ($output | Out-String).Trim()
        }
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
}

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

function Get-TunnelIdByName {
    param([string]$Name)

    $result = Invoke-Cloudflared tunnel list
    foreach ($line in ($result.Output -split "`r?`n")) {
        if ($line -match "^([0-9a-f-]{36})\s+(\S+)") {
            if ($Matches[2] -eq $Name) {
                return $Matches[1]
            }
        }
    }

    return $null
}

function Read-IngressRules {
    param([string]$Path)

    $rules = @()
    $current = $null
    $inIngress = $false

    foreach ($line in Get-Content -Path $Path) {
        if ($line -match "^\s*ingress\s*:\s*$") {
            $inIngress = $true
            continue
        }

        if (-not $inIngress) {
            continue
        }

        if ($line -match "^\s*-\s*hostname\s*:\s*(.+?)\s*(?:#.*)?$") {
            if ($current) {
                $rules += $current
            }
            $current = @{
                Hostname = $Matches[1].Trim().Trim("'`"")
                Service = $null
            }
            continue
        }

        if ($line -match "^\s*(?:-\s*)?service\s*:\s*(.+?)\s*(?:#.*)?$") {
            $service = $Matches[1].Trim().Trim("'`"")
            if ($service -eq "http_status:404") {
                continue
            }
            if ($current) {
                $current.Service = $service
            }
        }
    }

    if ($current) {
        $rules += $current
    }

    return $rules | Where-Object { $_.Hostname -and $_.Service }
}

function Get-HrIngressRule {
    param([string]$CloudflaredDir)

    $hrConfigPath = Join-Path $CloudflaredDir "config-v8-middleware.yml"
    if (-not (Test-Path $hrConfigPath)) {
        return $null
    }

    $rules = Read-IngressRules -Path $hrConfigPath
    return $rules | Where-Object { $_.Hostname -eq "v8-mw.k95foods.com" } | Select-Object -First 1
}

function Write-TunnelConfig {
    param(
        [string]$Path,
        [string]$TunnelId,
        [string]$CredentialsFile,
        [array]$IngressRules
    )

    $lines = @(
        "tunnel: $TunnelId",
        "credentials-file: $CredentialsFile",
        "ingress:"
    )

    foreach ($rule in $IngressRules) {
        $lines += "  - hostname: $($rule.Hostname)"
        $lines += "    service: $($rule.Service)"
    }

    $lines += "  - service: http_status:404"
    Set-Content -Path $Path -Value ($lines -join "`n") -Encoding UTF8
}

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Fail "cloudflared is not installed. Install with: choco install cloudflared"
}

$cloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"
if (-not (Test-Path $cloudflaredDir)) {
    New-Item -ItemType Directory -Path $cloudflaredDir -Force | Out-Null
}

$certPath = Join-Path $cloudflaredDir "cert.pem"
if (-not (Test-Path $certPath)) {
    Write-Host ""
    Write-Host "Cloudflare login required. Complete the browser prompt, then return here."
    Write-Host ""
    & cloudflared tunnel login
    if ($LASTEXITCODE -ne 0) {
        Fail "cloudflared tunnel login failed."
    }
    if (-not (Test-Path $certPath)) {
        Fail "Login did not create cert.pem at $certPath"
    }
}

$tunnelId = Get-TunnelIdByName -Name $TunnelName
if (-not $tunnelId) {
    Write-Host "Creating Cloudflare tunnel '$TunnelName'..."
    $createResult = Invoke-Cloudflared tunnel create $TunnelName
    if ($createResult.Output) {
        Write-Host $createResult.Output
    }
    if ($createResult.ExitCode -ne 0) {
        Fail "cloudflared tunnel create '$TunnelName' failed."
    }

    $tunnelId = Get-TunnelIdByName -Name $TunnelName
    if (-not $tunnelId) {
        Fail "Tunnel '$TunnelName' was created but its id could not be resolved."
    }
} else {
    Write-Host "Using existing tunnel '$TunnelName' ($tunnelId)."
}

$credentialsFile = Join-Path $cloudflaredDir "$tunnelId.json"
if (-not (Test-Path $credentialsFile)) {
    Fail "Tunnel credentials file not found at $credentialsFile"
}

Write-Host "Routing DNS: $Hostname -> tunnel '$TunnelName'..."
$dnsResult = Invoke-Cloudflared tunnel route dns $TunnelName $Hostname
if ($dnsResult.Output) {
    Write-Host $dnsResult.Output
}
if ($dnsResult.ExitCode -ne 0 -and $dnsResult.Output -notmatch "already exists|Record already exists|CNAME") {
    Fail "cloudflared tunnel route dns failed: $($dnsResult.Output)"
}

$printRule = @{
    Hostname = $Hostname
    Service = "http://127.0.0.1:$Port"
}

Write-TunnelConfig -Path $PrintConfigPath -TunnelId $tunnelId -CredentialsFile $credentialsFile -IngressRules @($printRule)
Write-Host ""
Write-Host "Print middleware config written:"
Write-Host "  $PrintConfigPath"
Write-Host "  $($printRule.Hostname) -> $($printRule.Service)"

$hrRule = $null
$shouldIncludeHr = $IncludeHrMiddleware.IsPresent -or (-not $IncludeHrMiddleware.IsPresent -and (Test-Path (Join-Path $cloudflaredDir "config-v8-middleware.yml")))
if ($shouldIncludeHr) {
    $hrRule = Get-HrIngressRule -CloudflaredDir $cloudflaredDir
}

$activeIngress = @($printRule)
if ($hrRule) {
    Write-Host ""
    Write-Host "HR attendance middleware detected (separate app on port 8080)."
    Write-Host "Adding v8-mw.k95foods.com to the shared cloudflared service config."

    $activeIngress += $hrRule

    Write-Host "Routing DNS: $($hrRule.Hostname) -> tunnel '$TunnelName'..."
    $hrDnsResult = Invoke-Cloudflared tunnel route dns $TunnelName $hrRule.Hostname
    if ($hrDnsResult.Output) {
        Write-Host $hrDnsResult.Output
    }
    if ($hrDnsResult.ExitCode -ne 0 -and $hrDnsResult.Output -notmatch "already exists|Record already exists|CNAME") {
        Write-Warning "Could not re-route HR hostname DNS automatically. HR may keep using its old tunnel until DNS is updated."
    }
}

$configDir = Split-Path -Parent $ConfigPath
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

if (Test-Path $ConfigPath) {
    $backupPath = "$ConfigPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Copy-Item -Path $ConfigPath -Destination $backupPath -Force
    Write-Host "Backed up previous config.yml to $backupPath"
}

Write-TunnelConfig -Path $ConfigPath -TunnelId $tunnelId -CredentialsFile $credentialsFile -IngressRules $activeIngress

Write-Host ""
Write-Host "Active cloudflared service config written:"
Write-Host "  $ConfigPath"
foreach ($rule in $activeIngress) {
    Write-Host "  $($rule.Hostname) -> $($rule.Service)"
}
Write-Host ""
Write-Host "Note: Printer middleware and HR middleware are separate apps."
Write-Host "      Print API uses port $Port. HR module uses its own port (8080)."
Write-Host ""

exit 0
