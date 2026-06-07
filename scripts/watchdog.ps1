# watchdog.ps1
# Service health monitor - detects death, hijack, and keeps status file accurate
# Usage: powershell -File scripts/watchdog.ps1 -Interval 30
# Stop:   powershell -File scripts/watchdog.ps1 -Stop

param(
    [int]$Interval = 30,
    [switch]$Stop
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$envFile    = Join-Path $root '.env'
$statusFile = Join-Path $root '.service_status.json'
$pidFile    = Join-Path $root '.watchdog.pid'
$logFile    = Join-Path $root '.watchdog.log'
$serviceMgr = Join-Path $root 'scripts\service_manager.ps1'

function Read-EnvPort($key, $default) {
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

function Test-Port($port) {
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

function Find-PidByPort($port) {
    $lines = netstat -ano 2>$null | Select-String ":$port " | Select-String 'LISTENING'
    foreach ($line in $lines) {
        $parts = ($line -split '\s+') | Where-Object { $_ }
        $targetPid = $parts[-1]
        if ($targetPid -match '^\d+$' -and [int]$targetPid -notin @(0,4)) {
            return [int]$targetPid
        }
    }
    return $null
}

function WLog($msg) {
    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $line = "[$ts] $msg"
    Write-Host $line
    try { Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue } catch {}
}

function Get-StatusData {
    if (Test-Path $statusFile) {
        try { return Get-Content $statusFile -Raw | ConvertFrom-Json } catch { return @{} }
    }
    return @{}
}

function Set-StatusData($data) {
    try {
        $json = $data | ConvertTo-Json -Depth 3 -Compress
        $tempFile = "$statusFile.tmp"
        [System.IO.File]::WriteAllText($tempFile, $json, [System.Text.Encoding]::UTF8)
        Move-Item -Force $tempFile $statusFile
    } catch {
        WLog "ERROR: Failed to write status file: $_"
    }
}

$flaskPort = Read-EnvPort 'FLASK_PORT' 3010
$vitePort  = Read-EnvPort 'VITE_DEV_PORT' 3004

$services = @{
    backend  = @{ port=$flaskPort; name='Backend (Python)';   key='backend'  }
    frontend = @{ port=$vitePort;  name='Frontend (Vite)';    key='frontend' }
}

# --- Stop mode ---
if ($Stop) {
    if (Test-Path $pidFile) {
        try {
            $wp = [int](Get-Content $pidFile)
            Stop-Process -Id $wp -Force -ErrorAction SilentlyContinue
            WLog "Watchdog stopped (PID=$wp)"
        } catch {
            WLog "Watchdog stop failed: $_"
        }
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "Watchdog is not running (no pid file)"
    }
    exit 0
}

# --- Daemon mode ---
# Prevent double-start
if (Test-Path $pidFile) {
    try {
        $existingPid = [int](Get-Content $pidFile)
        $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "Watchdog already running (PID=$existingPid)"
            exit 0
        }
    } catch {}
}
$pid | Set-Content $pidFile

WLog '============================================================'
WLog 'Watchdog started'
WLog "  Interval: ${Interval}s"
WLog "  Backend  port: $flaskPort"
WLog "  Frontend port: $vitePort"
WLog '============================================================'

$deathCount = @{ backend = 0; frontend = 0 }
$lastSeen  = @{ backend = $null; frontend = $null }
$cycleNum  = 0

while ($true) {
    Start-Sleep -Seconds $Interval
    $cycleNum++

    $data = Get-StatusData
    $changed = $false
    $allHealthy = $true

    foreach ($svcKey in $services.Keys) {
        $cfg = $services[$svcKey]
        $port = $cfg.port
        $listening = Test-Port $port
        $actualPid = if ($listening) { Find-PidByPort $port } else { $null }

        $known = $null
        if ($data.PSObject.Properties.Name -contains $svcKey) {
            $known = $data.$svcKey
        }

        $knownPid = if ($known -and $known.pid) { [int]$known.pid } else { $null }

        if ($listening -and $actualPid) {

            # Case 1: Healthy (port up, PID matches)
            if ($knownPid -and $actualPid -eq $knownPid) {
                if ($lastSeen[$svcKey] -ne $actualPid) {
                    WLog "HEALTHY: $($cfg.name) port=$port PID=$actualPid (matches status)"
                }
                # Update last_seen timestamp
                if (-not $known.last_seen) {
                    $data.$svcKey | Add-Member -NotePropertyName 'last_seen' `
                        -NotePropertyValue (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') -Force
                    $changed = $true
                } else {
                    $data.$svcKey.last_seen = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    $changed = $true
                }
                $lastSeen[$svcKey] = $actualPid
                $deathCount[$svcKey] = 0
            }

            # Case 2: HIJACK (port up, PID doesn't match status)
            elseif ($knownPid -and $actualPid -ne $knownPid) {
                $allHealthy = $false
                WLog "HIJACK: $($cfg.name) port=$port current_pid=$actualPid != known_pid=$knownPid"
                WLog "  Service was restarted outside service_manager!"
                WLog "  Updating status file to reflect reality..."
                $data.$svcKey.port = $port
                $data.$svcKey.pid = $actualPid
                $data.$svcKey.started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                $data.$svcKey.last_seen = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                if (-not (Get-Member -InputObject $data.$svcKey -Name 'hijack_count' -MemberType NoteProperty -ErrorAction SilentlyContinue)) {
                    $data.$svcKey | Add-Member -NotePropertyName 'hijack_count' -NotePropertyValue 0 -Force
                }
                $data.$svcKey.hijack_count = [int]$data.$svcKey.hijack_count + 1
                $lastSeen[$svcKey] = $actualPid
                $deathCount[$svcKey] = 0
                $changed = $true
            }

            # Case 3: Running but no known record (someone started directly)
            else {
                $allHealthy = $false
                WLog "UNMANAGED: $($cfg.name) port=$port PID=$actualPid (no record in status)"
                WLog "  Was started outside service_manager"
                if (-not $data) { $data = @{} }
                $data | Add-Member -NotePropertyName $svcKey -NotePropertyValue @{
                    port = $port
                    pid = $actualPid
                    started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    last_seen = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    source = 'detected_by_watchdog'
                } -Force
                $lastSeen[$svcKey] = $actualPid
                $deathCount[$svcKey] = 0
                $changed = $true
            }
        }

        # Case 4: DEATH (port NOT listening)
        elseif (-not $listening) {
            $allHealthy = $false
            $deathCount[$svcKey]++
            WLog "DEAD: $($cfg.name) port=$port not responding (count=$($deathCount[$svcKey]))"

            # Attempt auto-restart after 2 consecutive death detections
            if ($deathCount[$svcKey] -ge 2) {
                WLog "AUTO-RESTART: Attempting to restart $($cfg.name)..."
                $result = & powershell -File $serviceMgr "start-$svcKey" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    WLog "AUTO-RESTART: $($cfg.name) restarted successfully"
                    $deathCount[$svcKey] = 0
                    # Reload status after restart
                    $data = Get-StatusData
                    $lastSeen[$svcKey] = if ($data.$svcKey) { [int]$data.$svcKey.pid } else { $null }
                } else {
                    WLog "AUTO-RESTART: $($cfg.name) restart FAILED"
                    if ($deathCount[$svcKey] -ge 5) {
                        WLog "CRITICAL: $($cfg.name) has been dead for $($deathCount[$svcKey]) cycles"
                    }
                }
            }
            $changed = $true
        }
    }

    if ($changed) {
        Set-StatusData $data
    }

    # Periodic heartbeat (every 10 cycles)
    if ($cycleNum % 10 -eq 0) {
        $fb = if (Test-Port $flaskPort) { 'UP' } else { 'DOWN' }
        $fe = if (Test-Port $vitePort)  { 'UP' } else { 'DOWN' }
        WLog "HEARTBEAT cycle=$cycleNum backend=$fb frontend=$fe $(if ($allHealthy) { 'ALL_HEALTHY' } else { 'ISSUES_DETECTED' })"
    }
}
