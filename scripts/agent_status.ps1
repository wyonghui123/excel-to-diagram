# agent_status.ps1
# Multi-Agent Status Dashboard

$ErrorActionPreference = 'Continue'
$registryDir = 'd:\filework\.agent_registry'
$portsFile = Join-Path $registryDir 'ports.json'
$stateFile = Join-Path $registryDir 'state.json'

function Show-Header {
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Cyan
    Write-Host "  Multi-Agent Status Dashboard" -ForegroundColor Cyan
    Write-Host "==============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Ports {
    if (-not (Test-Path $portsFile)) {
        Write-Host "  [!] Port registry not found: $portsFile" -ForegroundColor Yellow
        return
    }

    try {
        $ports = Get-Content $portsFile -Raw | ConvertFrom-Json
    } catch {
        Write-Host "  [X] Failed to parse port registry: $_" -ForegroundColor Red
        return
    }

    if (-not $ports.agents -or $ports.agents.PSObject.Properties.Count -eq 0) {
        Write-Host "  [i] No agent port allocation" -ForegroundColor Gray
        return
    }

    Write-Host "--- Port Allocation -------------------------------------------" -ForegroundColor Green
    Write-Host ""
    Write-Host ("  {0,-12} {1,-15} {2,-15} {3,-30}" -f "Agent", "Frontend", "Backend", "Worktree") -ForegroundColor White
    Write-Host "  " ("-" * 75) -ForegroundColor Gray

    foreach ($agentId in $ports.agents.PSObject.Properties.Name) {
        $info = $ports.agents.$agentId
        $feStatus = if (Test-NetConnection -ComputerName localhost -Port $info.frontend -InformationLevel Quiet) {
            "[" + $info.frontend + "] IN USE"
        } else {
            "[" + $info.frontend + "] free"
        }
        $beStatus = if (Test-NetConnection -ComputerName localhost -Port $info.backend -InformationLevel Quiet) {
            "[" + $info.backend + "] IN USE"
        } else {
            "[" + $info.backend + "] free"
        }
        Write-Host ("  {0,-12} {1,-15} {2,-15} {3,-30}" -f $agentId, $feStatus, $beStatus, $info.worktree)
    }
    Write-Host ""
}

function Show-State {
    if (-not (Test-Path $stateFile)) {
        Write-Host "  [i] State file not found (agents may not be running)" -ForegroundColor Gray
        return
    }

    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
    } catch {
        Write-Host "  [X] Failed to parse state file: $_" -ForegroundColor Red
        return
    }

    if (-not $state.agents -or $state.agents.PSObject.Properties.Count -eq 0) {
        Write-Host "  [i] No active agents" -ForegroundColor Gray
        return
    }

    Write-Host "--- Agent State -----------------------------------------------" -ForegroundColor Green
    Write-Host ""

    foreach ($agentId in $state.agents.PSObject.Properties.Name) {
        $info = $state.agents.$agentId
        $statusIcon = switch ($info.status) {
            "running" { "[OK]" }
            "idle" { "[--]" }
            "error" { "[X]" }
            default { "[?]" }
        }
        $statusColor = switch ($info.status) {
            "running" { "Green" }
            "idle" { "Yellow" }
            "error" { "Red" }
            default { "White" }
        }

        Write-Host "  $statusIcon Agent: $agentId" -ForegroundColor $statusColor
        Write-Host ("      Status:   " + $info.status)
        if ($info.task) { Write-Host ("      Task:     " + $info.task) }
        if ($info.started_at) { Write-Host ("      Started:  " + $info.started_at) }
        if ($info.resources) {
            Write-Host ("      CPU:      " + $info.resources.cpu_percent + "%")
            Write-Host ("      Memory:   " + $info.resources.memory_mb + "MB")
        }
        if ($info.services) {
            foreach ($svc in $info.services.PSObject.Properties.Name) {
                $svcInfo = $info.services.$svc
                Write-Host ("      " + $svc + ": " + $svcInfo.status + " (port: " + $svcInfo.port + ", pid: " + $svcInfo.pid + ")")
            }
        }
        if ($info.tests) {
            $total = $info.tests.total
            $passed = $info.tests.passed
            $failed = $info.tests.failed
            $pct = 0
            if ($total -gt 0) { $pct = [math]::Round(($passed + $failed) * 100 / $total, 1) }
            Write-Host ("      Tests:    " + $passed + " passed, " + $failed + " failed / " + $total + " total (" + $pct + "%)")
            if ($info.tests.current) { Write-Host ("      Current:  " + $info.tests.current) }
        }
        Write-Host ""
    }
}

function Show-Resources {
    $cpu = (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples.CookedValue
    $os = Get-CimInstance Win32_OperatingSystem
    $memPct = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 100 / $os.TotalVisibleMemorySize, 1)
    $memAvailGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)

    Write-Host "--- System Resources ------------------------------------------" -ForegroundColor Green
    Write-Host ""
    Write-Host ("  CPU:    {0,5:N1} %" -f $cpu)
    Write-Host ("  Memory: {0,5:N1} % (free: {1} GB)" -f $memPct, $memAvailGB)

    if ($cpu -gt 80 -or $memPct -gt 85) {
        $color = 'Red'
        $verdict = '[BLOCKED] resources tight'
    } elseif ($cpu -gt 60 -or $memPct -gt 70) {
        $color = 'Yellow'
        $verdict = '[WARN] resources normal'
    } else {
        $color = 'Green'
        $verdict = '[OK] resources sufficient'
    }
    Write-Host "  $verdict" -ForegroundColor $color
    Write-Host ""
}

# Main
Show-Header
Show-Resources
Show-Ports
Show-State
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""
