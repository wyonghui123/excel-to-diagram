# start.ps1
# Unified startup entry point - the ONLY command an Agent needs
# Usage: powershell -File scripts/start.ps1

param(
    [switch]$Force
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$envFile = Join-Path $root '.env'
$serviceManager = Join-Path $root 'scripts\service_manager.ps1'

function Read-EnvPort {
    param($key, $default)
    if (Test-Path $envFile) {
        try {
            $lines = Get-Content $envFile -ErrorAction Stop
            foreach ($line in $lines) {
                $trimmed = $line.Trim()
                if ($trimmed -and -not $trimmed.StartsWith('#')) {
                    $parts = $trimmed -split '=', 2
                    if ($parts.Length -eq 2 -and $parts[0].Trim() -eq $key) {
                        $val = $parts[1].Trim()
                        if ($val -match '^\d+$') { return [int]$val }
                    }
                }
            }
        } catch {}
    }
    return $default
}

function Test-Port {
    param($port)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', $port)
        $tcp.Close()
        $tcp.Dispose()
        return $true
    } catch {
        return $false
    }
}

$flaskPort = Read-EnvPort -key 'FLASK_PORT' -default 3010
$vitePort  = Read-EnvPort -key 'VITE_DEV_PORT' -default 3004

$banner = '=' * 60

Write-Host ''
Write-Host "  $banner"
Write-Host '    Excel-to-Diagram  Unified Startup'
Write-Host "  $banner"
Write-Host ''

if ($Force) {
    Write-Host '  [FORCE MODE] Restarting all services...'
    $result = & powershell -File $serviceManager restart 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $result
        Write-Host ''
        Write-Host '  [ERROR] Service restart failed'
        Write-Host "  $banner"
        exit 1
    }
} else {
    $frontendUp = Test-Port -port $vitePort
    $backendUp  = Test-Port -port $flaskPort

    if ($frontendUp -and $backendUp) {
        Write-Host '  [OK] Both frontend and backend are already running'
    } else {
        $what = @()
        if (-not $frontendUp) { $what += "Frontend(port $vitePort)" }
        if (-not $backendUp)  { $what += "Backend(port $flaskPort)" }
        Write-Host "  [STARTING] $($what -join ', ')..."

        $result = & powershell -File $serviceManager start 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host $result
            Write-Host ''
            Write-Host '  [ERROR] Service start failed'
            Write-Host "  $banner"
            exit 1
        }
    }
}

$divider = '-' * 60

Write-Host ''
Write-Host "  $divider"
Write-Host '  Status:'
$feStatus = if (Test-Port -port $vitePort)  { 'RUNNING' } else { 'STOPPED' }
$beStatus = if (Test-Port -port $flaskPort) { 'RUNNING' } else { 'STOPPED' }
Write-Host "    Frontend (Vite)    : $feStatus  ->  http://localhost:$vitePort"
Write-Host "    Backend  (Flask)   : $beStatus  ->  http://localhost:$flaskPort"
Write-Host "  $divider"

if ((Test-Port -port $vitePort) -and (Test-Port -port $flaskPort)) {
    Write-Host ''
    Write-Host "  [READY] Open browser: http://localhost:$vitePort"
    Write-Host "  $banner"
    Write-Host ''
    exit 0
} else {
    Write-Host ''
    Write-Host '  [WARNING] Some services are not ready'
    Write-Host "  $banner"
    Write-Host ''
    exit 1
}
