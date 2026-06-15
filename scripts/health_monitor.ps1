# health_monitor.ps1 (v3.18 Layer 4)
# Background health monitor: ping /health every N seconds, restart on failure.
#
# Usage:
#   Start-Process powershell -ArgumentList '-NoProfile','-File','scripts\health_monitor.ps1','-Port','3010' -WindowStyle Hidden
#
# Stop:
#   Create file .health_monitor_3010.stop in project root

param(
    [int]$Port = 3010,
    [int]$IntervalSec = 5,
    [int]$HealthTimeoutSec = 3,
    [int]$FailureThreshold = 2,
    [string]$HealthPath = '/health'
)

$ErrorActionPreference = 'Continue'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$logFile = Join-Path $rootDir ".health_monitor_${Port}.log"
$stopFile = Join-Path $rootDir ".health_monitor_${Port}.stop"
$pidFile = Join-Path $rootDir ".health_monitor_${Port}.pid"
$serviceManagerScript = Join-Path $scriptDir 'service_manager.ps1'

function Write-Log {
    param([string]$Message)
    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssZ')
    Add-Content -Path $logFile -Value "[$ts] $Message" -ErrorAction SilentlyContinue
}

try { Set-Content -Path $pidFile -Value $PID -ErrorAction SilentlyContinue } catch {}
Write-Log "Health monitor started: port=$Port interval=${IntervalSec}s"

function Test-HealthEndpoint {
    param([int]$Port, [string]$Path, [int]$TimeoutSec)
    try {
        $uri = "http://localhost:${Port}${Path}"
        $req = [System.Net.HttpWebRequest]::Create($uri)
        $req.Timeout = $TimeoutSec * 1000
        $req.Method = 'GET'
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return ($code -ge 200 -and $code -lt 500)
    }
    catch {
        return $false
    }
}

function Restart-BackendService {
    param([int]$Port)
    Write-Log "Triggering backend restart (port=$Port)..."
    try {
        $p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-File',$serviceManagerScript,'start','-Port',$Port) -PassThru -WindowStyle Hidden
        Write-Log "Restart invoked, monitor_pid=$($p.Id)"
    }
    catch {
        Write-Log "Restart failed: $($_.Exception.Message)"
    }
}

$failures = 0

while ($true) {
    if (Test-Path $stopFile) {
        Write-Log "Stop file detected, exiting"
        Remove-Item $stopFile -ErrorAction SilentlyContinue
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        exit 0
    }

    $ok = Test-HealthEndpoint -Port $Port -Path $HealthPath -TimeoutSec $HealthTimeoutSec
    if ($ok) {
        if ($failures -gt 0) {
            Write-Log "Health recovered after $failures failures"
        }
        $failures = 0
    }
    else {
        $failures += 1
        Write-Log "Health check failed ($failures/$FailureThreshold) port=$Port"
        if ($failures -ge $FailureThreshold) {
            Write-Log "Threshold reached, restarting backend"
            Restart-BackendService -Port $Port
            $failures = 0
            Start-Sleep -Seconds 10
        }
    }

    Start-Sleep -Seconds $IntervalSec
}
