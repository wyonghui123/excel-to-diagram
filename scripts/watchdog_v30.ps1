# watchdog_v30.ps1
# Service health monitor with RESTART LOOP FIX
# v3.0: Fixes 30-second restart popup loop
#
# Key changes from v2.x:
# 1. AUTO-RESTART failure -> RESET deathCount (was: keep incrementing forever)
# 2. AUTO-RESTART max 3 attempts per session (was: infinite)
# 3. Calls pythonw -File restart_backend.py instead of powershell -File service_manager.ps1
#    (was: powershell popup window on every restart attempt)
# 4. After max failures, STOP restart attempts and require manual intervention
#
# Usage:
#   powershell -File scripts/watchdog_v30.ps1
#   powershell -File scripts/watchdog_v30.ps1 -Interval 30
#   powershell -File scripts/watchdog_v30.ps1 -Stop
#
# Stop:
#   powershell -File scripts/watchdog_v30.ps1 -Stop

param(
    [int]$Interval = 30,
    [switch]$Stop
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$pidFile = Join-Path $root '.watchdog_v30.pid'
$logFile = Join-Path $root '.watchdog_v30.log'
$statusFile = Join-Path $root '.service_status.json'
$restartScript = Join-Path $root 'scripts\restart_backend.py'

# ============================================================
# Configuration
# ============================================================
$MaxRestartAttempts = 3          # Max AUTO-RESTART attempts per service
$ResetCountAfterRestart = $true  # Reset deathCount after restart attempt (was the bug)

# ============================================================

function WLog($msg) {
    $ts = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ')
    $line = "[$ts] $msg"
    Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue
    Write-Host $line
}

function Test-Port($port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        $success = $iar.AsyncWaitHandle.WaitOne(2000) -and $client.Connected
        $client.Close()
        return $success
    } catch {
        return $false
    }
}

function Restart-Backend-Once {
    # Restart using pythonw (NO powershell popup)
    WLog "AUTO-RESTART: Calling pythonw restart_backend.py (NO popup)"

    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        $pythonw = "pythonw.exe"
    }

    try {
        $proc = Start-Process -FilePath $pythonw `
            -ArgumentList @($restartScript) `
            -WorkingDirectory $root `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $root 'restart_backend.out') `
            -RedirectStandardError (Join-Path $root 'restart_backend.err') `
            -PassThru

        # Wait for restart to complete (up to 40 seconds, waitress needs 10-35s)
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Port 3010) {
                $ready = $true
                break
            }
        }

        if ($ready) {
            WLog "AUTO-RESTART: Backend restarted successfully (port 3010 OPEN)"
            return $true
        } else {
            WLog "AUTO-RESTART: Backend port 3010 still closed after 40s"
            return $false
        }
    } catch {
        WLog "AUTO-RESTART: Exception: $($_.Exception.Message)"
        return $false
    }
}

# ============================================================
# Stop mode
# ============================================================
if ($Stop) {
    if (Test-Path $pidFile) {
        $wp = [int](Get-Content $pidFile)
        try {
            Stop-Process -Id $wp -Force -ErrorAction SilentlyContinue
            WLog "Watchdog stopped (PID=$wp)"
        } catch {}
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

# ============================================================
# Single-instance lock
# ============================================================
if (Test-Path $pidFile) {
    $existing = [int](Get-Content $pidFile)
    if (Get-Process -Id $existing -ErrorAction SilentlyContinue) {
        WLog "Watchdog already running (PID=$existing). Exiting."
        exit 1
    } else {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}
Set-Content -Path $pidFile -Value $PID

WLog "============================================================"
WLog "Watchdog v3.0 STARTED (PID=$PID)"
WLog "  Interval: ${Interval}s"
WLog "  MaxRestartAttempts: $MaxRestartAttempts"
WLog "  ResetCountAfterRestart: $ResetCountAfterRestart"
WLog "  Restart method: pythonw (NO popup)"
WLog "============================================================"

# Cleanup on exit
trap {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    WLog "Watchdog exited (cleanup)"
}

# ============================================================
# Main loop
# ============================================================

$cycleNum = 0
$restartAttempts = @{
    'be' = 0
    'fe' = 0
}
$deathCount = @{
    'be' = 0
    'fe' = 0
}
$restartDisabled = @{
    'be' = $false
    'fe' = $false
}

while ($true) {
    $cycleNum++

    # Check backend
    $beOk = Test-Port 3010
    if ($beOk) {
        # Healthy
        if ($deathCount['be'] -gt 0) {
            WLog "RECOVERED: backend 3010 back online (was dead for $($deathCount['be']) cycles)"
            $deathCount['be'] = 0
            $restartAttempts['be'] = 0
            $restartDisabled['be'] = $false
        }
    } else {
        # Dead
        $deathCount['be']++
        WLog "DEAD: backend 3010 not responding (count=$($deathCount['be']))"

        if ($restartDisabled['be']) {
            # Already disabled, just monitor
            if ($cycleNum % 5 -eq 0) {
                WLog "  AUTO-RESTART disabled for backend (max attempts reached)"
            }
        } elseif ($deathCount['be'] -ge 2) {
            # Trigger AUTO-RESTART
            if ($restartAttempts['be'] -lt $MaxRestartAttempts) {
                $restartAttempts['be']++
                WLog "AUTO-RESTART: backend attempt #$($restartAttempts['be']) of $MaxRestartAttempts"

                $success = Restart-Backend-Once

                # *** KEY FIX: Reset deathCount after restart attempt ***
                # (Previously: kept incrementing, causing infinite loop)
                if ($ResetCountAfterRestart) {
                    WLog "  Resetting deathCount['be'] to 0 (post-attempt)"
                    $deathCount['be'] = 0
                }

                if (-not $success -and $restartAttempts['be'] -ge $MaxRestartAttempts) {
                    WLog "CRITICAL: Max restart attempts ($MaxRestartAttempts) reached for backend"
                    WLog "  AUTO-RESTART DISABLED. Manual intervention required."
                    $restartDisabled['be'] = $true
                }
            } else {
                WLog "  Max attempts reached, AUTO-RESTART skipped"
                $restartDisabled['be'] = $true
            }
        }
    }

    # Check frontend (similar logic, simplified)
    $feOk = Test-Port 3004
    if ($feOk) {
        if ($deathCount['fe'] -gt 0) {
            WLog "RECOVERED: frontend 3004 back online"
            $deathCount['fe'] = 0
            $restartAttempts['fe'] = 0
        }
    } else {
        $deathCount['fe']++
        if ($cycleNum % 5 -eq 0) {
            WLog "DEAD: frontend 3004 (count=$($deathCount['fe']))"
        }
    }

    # Heartbeat every 10 cycles
    if ($cycleNum % 10 -eq 0) {
        WLog "HEARTBEAT cycle=$cycleNum be=$($beOk) fe=$($feOk) restarts=be:$($restartAttempts['be'])/$MaxRestartAttempts fe:$($restartAttempts['fe'])/$MaxRestartAttempts"
    }

    Start-Sleep -Seconds $Interval
}