# service_manager.ps1
# 统一服务管理器 - PowerShell 版本
# 用法: .\scripts\service_manager.ps1 [status|start|stop|restart|force-restart] [-Port <3010-3019>]
# 用法: python scripts/service_manager.py [status|start|stop|restart] [--port <port>]
# 🆕 v3.18: 多 Agent 端口隔离 (-Port 3010-3019)

param(
    [Parameter(Position=0)]
    [ValidateSet('status','start','stop','restart','force-restart','start-fe','start-be','watchdog','watchdog-start','watchdog-stop','clear-stale-lock','list-locks','preflight')]
    [string]$Command = 'status',

    [Parameter()]
    [ValidateRange(1, 65535)]
    [int]$Port = 3010,

    # [P0 v3.18+] 调试铁律: preflight 检查 - 要求 status 文件足够新
    [Parameter()]
    [switch]$RequireFresh,

    [Parameter()]
    [ValidateRange(10, 86400)]
    [int]$MaxAge = 60
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
# 🆕 v3.18: per-port 状态/锁文件 (支持多 agent 并行)
$statusFile = Join-Path $root ".service_status_$Port.json"
$lockFile = Join-Path $root ".service_manager_$Port.lock"
$logFile = Join-Path $root ".service_manager_$Port.log"
$envFile = Join-Path $root '.env'
$watchdogScript = Join-Path $root 'scripts\watchdog.ps1'
$watchdogPidFile = Join-Path $root '.watchdog.pid'

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

$flaskPort = Read-EnvPort 'FLASK_PORT' $Port
$vitePort  = Read-EnvPort 'VITE_DEV_PORT' 3004

$services = @{
    frontend = @{ port=$vitePort;  name='Frontend (Vite)';     cmd='cmd.exe'; args=@('/c','npm run dev');   wait=8 }
    # 🆕 v3.9 备选: gevent_server.py (真流式 SSE, 但 SQLite 锁问题)
    # 当前: waitress_server.py (8 线程, 稳定)
    # 可手动切换: 改 backend 行的 cmd 和 args
    # 🆕 v3.19: 用 pythonw.exe 避免 console 窗口弹窗
    # pythonw = GUI Python, 不会创建 console 窗口
    # stdout/stderr 重定向到日志文件 (service_manager 处理)
    $pythonExe = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe) {
        $pythonExe = 'python'
    }
    backend  = @{ port=$flaskPort; name='Backend (Waitress)';   cmd=$pythonExe;  args=@('waitress_server.py');     wait=10 }
}

function Write-Log($msg) {
    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $line = "[$ts] $msg"
    Write-Host $line
    try { Add-Content -Path $logFile -Value $line -ErrorAction SilentlyContinue } catch {}
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

<#
.SYNOPSIS
  清理 test_temp 目录中过期的 -wal/-shm 残留文件
.DESCRIPTION
  这些文件来自 pytest snapshot, 当测试被 kill 时不会自动清理, 长期堆积
  会导致 DB Health Monitor 报警 (Temp file count HIGH)。建议每次启动时清理。
  🆕 v3.18: 加超时机制, 避免大量文件时阻塞 stop 流程超过 30s
#>
function Clean-StaleTempFiles() {
    $testTempDir = Join-Path $root 'test_temp'
    if (-not (Test-Path $testTempDir)) { return }

    $cleaned = 0
    $startTime = Get-Date
    $timeoutSeconds = 30  # 最多 30s, 防止 stop 卡住

    $walJob = Start-Job -ScriptBlock {
        param($dir)
        $n = 0
        Get-ChildItem $dir -Filter '*db-wal' -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
            $n++
        }
        Get-ChildItem $dir -Filter '*db-shm' -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
            $n++
        }
        return $n
    } -ArgumentList $testTempDir

    $completed = Wait-Job $walJob -Timeout $timeoutSeconds
    if ($null -eq $completed) {
        Stop-Job $walJob -Force
        Remove-Job $walJob -Force
        Write-Log "[CLEAN-TEMP] Timeout after ${timeoutSeconds}s, aborting"
        return
    }
    $cleaned = Receive-Job $walJob
    Remove-Job $walJob -Force

    $elapsed = ((Get-Date) - $startTime).TotalSeconds
    if ($cleaned -gt 0) {
        Write-Log "[CLEAN-TEMP] Removed $cleaned stale WAL/SHM files from test_temp in $([int]$elapsed)s"
    }
}

function Get-StatusData {
    if (Test-Path $statusFile) {
        try { return Get-Content $statusFile -Raw | ConvertFrom-Json } catch { return @{} }
    }
    return @{}
}

function Set-StatusData($data) {
    $data | ConvertTo-Json -Depth 3 | Set-Content $statusFile -Encoding UTF8
}

<#
.SYNOPSIS
  [P0 v3.18+] 调试铁律: 检查 status 文件是否"足够新" (避免"重启了但没生效"陷阱)
.DESCRIPTION
  校验 .service_status_<port>.json 的 started_at 距今 < $MaxAge 秒
  返回 $true = 新鲜 (可放心使用), $false = 过时 (应先 restart)
  退出码: 0 = OK, 1 = stale (含修复提示)
#>
function Test-ServiceFresh {
    param([int]$MaxAgeSeconds = 60)

    if (-not (Test-Path $statusFile)) {
        Write-Log "[PREFLIGHT] FAIL: status file missing: $statusFile"
        Write-Host "  [BLOCKED] Service status file not found." -ForegroundColor Red
        Write-Host "  Hint: Run: service_manager.ps1 start -Port $Port"
        return $false
    }

    $data = Get-StatusData
    if (-not $data) {
        Write-Log "[PREFLIGHT] FAIL: status file empty/corrupt"
        Write-Host "  [BLOCKED] Status file empty/corrupt." -ForegroundColor Red
        Write-Host "  Hint: Run: service_manager.ps1 start -Port $Port"
        return $false
    }

    # 找到最早 started_at (前端的 started_at, 不是 backend)
    $earliest = $null
    foreach ($svcName in @('frontend', 'backend')) {
        $svc = $data.$svcName
        if ($svc -and $svc.started_at) {
            $ts = [datetime]$svc.started_at
            if (-not $earliest -or $ts -lt $earliest) {
                $earliest = $ts
            }
        }
    }
    if (-not $earliest) {
        Write-Log "[PREFLIGHT] FAIL: no started_at in status file"
        Write-Host "  [BLOCKED] No started_at found in status file." -ForegroundColor Red
        Write-Host "  Hint: Run: service_manager.ps1 restart -Port $Port"
        return $false
    }

    $age = (Get-Date) - $earliest
    $ageSec = [int]$age.TotalSeconds
    if ($ageSec -gt $MaxAgeSeconds) {
        Write-Log "[PREFLIGHT] FAIL: service age=${ageSec}s > ${MaxAgeSeconds}s (stale)"
        Write-Host "  [BLOCKED] Service started ${ageSec}s ago (> ${MaxAgeSeconds}s)." -ForegroundColor Red
        Write-Host "  Started at: $($earliest.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        Write-Host "  Hint: Code may have changed but service is still running OLD code." -ForegroundColor Yellow
        Write-Host "  Run: service_manager.ps1 restart -Port $Port"
        return $false
    }

    Write-Log "[PREFLIGHT] OK: service age=${ageSec}s <= ${MaxAgeSeconds}s"
    Write-Host "  [OK] Service fresh: started ${ageSec}s ago (limit: ${MaxAgeSeconds}s)"
    return $true
}

function Wait-Lock {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Path $lockFile)) {
            try {
                # 🆕 v3.18: 记录持有者 PID + 时间戳 + 命令名 (便于诊断锁竞争)
                $lockContent = "PID=$PID`nstarted=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))`ncommand=$Command`nport=$Port"
                Set-Content -Path $lockFile -Value $lockContent
                return $true
            } catch {
                Start-Sleep -Seconds 2
                continue
            }
        }
        # 🆕 v3.18: 自动检测 stale lock - 持有者进程已死时自动清理
        $holderInfo = Get-StaleLockHolder $lockFile
        if ($holderInfo -and $holderInfo.IsStale) {
            Write-Log "[LOCK] Detected stale lock (PID=$($holderInfo.Pid) not alive), auto-cleaning"
            Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
            continue
        }
        $age = ((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalSeconds
        # 老逻辑: 5 分钟无更新视为 stale
        if ($age -gt 300) {
            Write-Log "[LOCK] Lock age=$([int]$age)s > 300s, treating as stale"
            Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
            continue
        }
        # 🆕 报告持有者信息便于诊断
        $holderMsg = if ($holderInfo) { " held by PID=$($holderInfo.Pid)" } else { "" }
        Write-Log "Waiting for lock (age=$([int]$age)s)${holderMsg}..."
        Start-Sleep -Seconds 2
    }
    Write-Log 'ERROR: Could not acquire lock'
    return $false
}

function Release-Lock {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}

<#
.SYNOPSIS
  解析 lock 文件, 返回持有者信息
.DESCRIPTION
  返回的对象包含:
    - Pid: 持有者进程 PID (若无则 $null)
    - Started: 持有者启动时间 (ISO 8601)
    - Command: 持有者正在执行的 service_manager 子命令
    - IsStale: 持有者进程是否已死 (true = 可安全清理)
#>
function Get-StaleLockHolder($file) {
    if (-not (Test-Path $file)) { return $null }
    try {
        $raw = Get-Content $file -ErrorAction SilentlyContinue
        if (-not $raw) { return $null }

        $info = [PSCustomObject]@{
            Pid = $null
            Started = $null
            Command = $null
            Port = $null
            IsStale = $true  # 默认 stale
        }

        foreach ($line in $raw) {
            $line = $line.Trim()
            if ($line -match '^PID=(\d+)$') { $info.Pid = [int]$matches[1] }
            elseif ($line -match '^started=(.+)$') { $info.Started = $matches[1] }
            elseif ($line -match '^command=(.+)$') { $info.Command = $matches[1] }
            elseif ($line -match '^port=(\d+)$') { $info.Port = [int]$matches[1] }
        }

        if ($info.Pid) {
            $proc = Get-Process -Id $info.Pid -ErrorAction SilentlyContinue
            $info.IsStale = ($null -eq $proc)
        } else {
            $info.IsStale = $true
        }
        return $info
    } catch {
        return $null
    }
}

# ===== 测试运行检测 =====
function Test-RunningTests {
    <#
    .SYNOPSIS
        检测是否有 Playwright 测试进程正在运行
    .DESCRIPTION
        检查是否有 playwright、chromium、chrome 相关的进程
        这些进程通常是 Playwright E2E 测试正在执行
    #>
    try {
        # 方法1: 检查进程名
        $testProcesses = @()
        $possibleNames = @('chromium', 'chrome', 'playwright', 'node')
        foreach ($name in $possibleNames) {
            $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
            if ($procs) {
                $testProcesses += $procs
            }
        }

        # 方法2: 检查命令行参数（更准确）
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', $vitePort)
        $tcp.Close()
        $tcp.Dispose()
        # 如果 Vite 端口可访问，说明前端在运行
        $frontendRunning = $true
    } catch {
        $frontendRunning = $false
    }

    return @{
        hasTestProcesses = ($testProcesses.Count -gt 0)
        testProcesses = $testProcesses
        frontendRunning = $frontendRunning
    }
}

function Assert-NoRunningTests {
    <#
    .SYNOPSIS
        在执行危险操作前检查是否有测试正在运行
    #>
    $check = Test-RunningTests

    if ($check.hasTestProcesses) {
        Write-Log "WARNING: Detected $($check.testProcesses.Count) test-related process(es):"
        foreach ($p in $check.testProcesses) {
            Write-Log "  - PID=$($p.Id) $($p.ProcessName)"
        }
        Write-Log ""
        Write-Log "Tests may be interrupted by this operation."
        Write-Log "Consider waiting for tests to complete, or use 'restart -Force' to proceed anyway."
        return $false
    }

    return $true
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

<#
.SYNOPSIS
  清理所有可能与 architecture.db 竞争的孤儿 Python 进程
.DESCRIPTION
  扫描所有 python.exe 进程，识别其命令行是否包含 "meta\server.py" 或 "waitress_server.py"。
  这些进程如果不在我们的 service_manager 管控下，会导致 SQLite 多进程并发写，损坏 DB。
  在启动 backend 前强制清理，确保只有一个 meta.server.py 持有 DB 句柄。
#>
function Kill-AllOrphanBackends() {
    Write-Log "[KILL-ORPHANS] Scanning for orphan backend processes..."

    # 排除当前 service_manager 自身和 watchdog
    $myPid = $PID
    $watchdogPid = $null
    if (Test-Path $watchdogPidFile) {
        $raw = Get-Content $watchdogPidFile -ErrorAction SilentlyContinue
        if ($raw -and $raw[0] -match '^\d+$') {
            $watchdogPid = [int]$raw[0]
        }
    }

    # 🆕 v3.18 P1 优化: 用 tasklist /v + 进程名过滤替代 WMI (WMI 在大进程列表下慢 10-50x)
    # tasklist 默认输出: "Image Name  PID  Session  Session#  Mem  Status  User  CPU  Window Title"
    # 加 /v 加 Window Title
    $tasklistOut = $null
    $tasklistErr = $null
    $tasklistJob = Start-Job -ScriptBlock {
        $out = cmd.exe /c "tasklist /FI ""IMAGENAME eq python.exe"" /FO CSV /V" 2>&1
        return $out
    }
    $completed = Wait-Job $tasklistJob -Timeout 10
    if ($null -eq $completed) {
        Stop-Job $tasklistJob -Force
        Write-Log "[KILL-ORPHANS] tasklist timeout (>10s), skipping"
        return
    }
    $tasklistOut = Receive-Job $tasklistJob -Keep
    Remove-Job $tasklistJob -Force

    if (-not $tasklistOut) {
        Write-Log "[KILL-ORPHANS] No python processes found."
        return
    }

    # 解析 CSV 输出
    # 格式: "python.exe","1234","Console","1","12,345 K","Running","User","0:00:01","N/A","Window Title"
    $candidates = @()
    $lines = $tasklistOut -split "`r?`n"
    foreach ($line in $lines) {
        $line = $line.Trim()
        if (-not $line -or $line -match '^"Image Name"') { continue }
        # 简单 CSV 解析 (假设没有内嵌引号)
        if ($line -match '^"python\.exe","(\d+)"') {
            # 🆕 v3.18: 不能用 $pid (PowerShell 内置只读变量)
            $procPid = [int]$matches[1]
            # Window Title 字段通常包含命令行
            $parts = $line -split '","'
            $cmd = if ($parts.Count -ge 10) { $parts[9] } else { '' }
            $candidates += [PSCustomObject]@{ Pid = $procPid; Cmd = $cmd }
        }
    }

    if ($candidates.Count -eq 0) {
        Write-Log "[KILL-ORPHANS] No python processes found."
        return
    }

    # 获取已知 PID 列表
    $knownPids = @()
    $status = Get-StatusData -ErrorAction SilentlyContinue
    if ($status) {
        foreach ($svc in $status.PSObject.Properties) {
            if ($svc.Value.pid) { $knownPids += [int]$svc.Value.pid }
        }
    }

    $killed = 0
    foreach ($c in $candidates) {
        if ($c.Pid -eq $myPid) { continue }
        if ($watchdogPid -and $c.Pid -eq $watchdogPid) { continue }
        if ($knownPids -contains $c.Pid) { continue }

        # 用 Window Title 字段判断是否是 backend (粗略但比 WMI 快)
        # meta.server.py / waitress_server.py 启动时, Window Title 通常是命令行
        $isBackend = $false
        $patterns = @('meta\server\.py', 'meta\\server\.py', 'waitress_server\.py', 'waitress_server', 'gunicorn.*meta\.server')
        foreach ($pat in $patterns) {
            if ($c.Cmd -match $pat) { $isBackend = $true; break }
        }
        # 如果 Window Title 为空 (常见于隐藏窗口), 也可能是 backend
        # 此时保守不杀, 只杀能识别的
        if (-not $isBackend) { continue }

        $cmdPreview = $c.Cmd.Substring(0, [Math]::Min(80, $c.Cmd.Length))
        Write-Log "[KILL-ORPHANS] Killing orphan backend PID=$($c.Pid) cmd='$cmdPreview'"
        $taskkillOut = taskkill /F /PID $c.Pid 2>&1
        if ($LASTEXITCODE -eq 0) {
            $killed = $killed + 1
        }
    }
    if ($killed -gt 0) {
        Write-Log "[KILL-ORPHANS] Killed $killed orphan backend process(es). Waiting for DB file lock release..."
        # 等待 SQLite 释放文件锁（Windows 上通常 < 2s）
        Start-Sleep -Seconds 3
    } else {
        Write-Log "[KILL-ORPHANS] No orphan backends found."
    }
}

function Stop-Service($svcName) {
    $cfg = $services[$svcName]
    $portNum = $cfg.port
    $port = $portNum
    Write-Log "Stopping $($cfg.name)..."

    if (-not (Test-Port $port)) {
        Write-Log "  $($cfg.name) already stopped"
        # 即使端口未占用，仍清理可能的孤儿 backend（防止多进程写）
        Kill-AllOrphanBackends
        return $true
    }

    $known = (Get-StatusData).PSObject.Properties
    $knownPid = $null
    foreach ($prop in $known) {
        if ($prop.Name -eq $svcName) {
            $knownPid = $prop.Value.pid
        }
    }

    $killed = $false
    if ($knownPid) {
        try { taskkill /F /PID $knownPid 2>$null | Out-Null; Start-Sleep 2
            if (-not (Test-Port $port)) { $killed = $true; Write-Log "  Stopped via PID $knownPid" }
        } catch {}
    }

    if (-not $killed) {
        $foundPid = Find-PidByPort $port
        if ($foundPid) {
            try { taskkill /F /PID $foundPid 2>$null | Out-Null; Start-Sleep 1
                if (-not (Test-Port $port)) { Write-Log "  Stopped via port scan PID $foundPid" }
            } catch {}
        }
    }

    # wait for port release
    for ($i = 0; $i -lt 10; $i++) {
        if (-not (Test-Port $port)) { break }
        Start-Sleep -Seconds 1
    }

    if (Test-Port $port) {
        Write-Log "  WARNING: Port $port still in use"
        return $false
    } else {
        Write-Log "  $($cfg.name) stopped"
        # 🆕 防止多进程并发写 DB: 清理所有孤儿 backend
        Kill-AllOrphanBackends
        return $true
    }
}

function Start-Service($svcName) {
    $cfg = $services[$svcName]
    $port = $cfg.port

    if (Test-Port $port) {
        Write-Log "$($cfg.name) already running on port $port"
        return $true
    }

    # 🆕 防多进程并发写 DB: 启动前清理所有孤儿 backend
    Kill-AllOrphanBackends

    Write-Log "Starting $($cfg.name)..."
    $argStr = ($cfg.args -join ' ')

    try {
        # 🆕 v3.8: waitress 模式 - FLASK_DEBUG 必须 false (生产模式)
        # 避开 startup_checks 的 CORS 检查 (或显式设 CORS_ALLOWED_ORIGINS)
        $env:FLASK_DEBUG = 'false'
        $env:TESTING = 'false'
        $env:FLASK_ENV = 'production'
        $env:CORS_ALLOWED_ORIGINS = 'http://localhost:5173,http://localhost:3010,http://localhost:3004'
        # 🆕 v3.18: 注入 AGENT_PORT 给 waitress_server.py 用
        $env:AGENT_PORT = $port.ToString()

        $proc = Start-Process -FilePath $cfg.cmd -ArgumentList $argStr `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$root\scripts\logs\$svcName.out" `
            -RedirectStandardError "$root\scripts\logs\$svcName.err" `
            -NoNewWindow

        # wait for port
        $ready = $false
        for ($i = 0; $i -lt $cfg.wait; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Port $port) { $ready = $true; break }
        }

        if ($ready) {
            # Update status file
            $data = Get-StatusData
            if (-not $data) { $data = @{} }
            $data | Add-Member -NotePropertyName $svcName -NotePropertyValue @{
                port = $port
                pid = $proc.Id
                started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
            } -Force
            Set-StatusData $data
            Write-Log "  $($cfg.name) started (PID=$($proc.Id), port=$port)"
            return $true
        } else {
            Write-Log "  $($cfg.name) process spawned but port $port not responding"
            return $false
        }
    } catch {
        Write-Log "  ERROR starting $($cfg.name): $_"
        return $false
    }
}

function Start-Watchdog {
    if (Test-Path $watchdogPidFile) {
        try {
            $wp = [int](Get-Content $watchdogPidFile)
            $existing = Get-Process -Id $wp -ErrorAction SilentlyContinue
            if ($existing) {
                Write-Log "Watchdog already running (PID=$wp)"
                return $true
            }
        } catch {
            # stale pid file or permission denied; will overwrite
        }
    }
    Write-Log "Starting Watchdog..."
    try {
        $wp = Start-Process -FilePath 'powershell' `
            -ArgumentList "-File `"$watchdogScript`" -Interval 30" `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 1
        if ($wp -and -not $wp.HasExited) {
            Write-Log "  Watchdog started (PID=$($wp.Id))"
            return $true
        } else {
            Write-Log "  Watchdog failed to start"
            return $false
        }
    } catch {
        Write-Log "  ERROR starting Watchdog: $_"
        return $false
    }
}

function Stop-Watchdog {
    $script = $watchdogScript
    Write-Log "Stopping Watchdog..."
    & powershell -File $script -Stop 2>&1 | Out-Null
    if (-not (Test-Path $watchdogPidFile)) {
        Write-Log "  Watchdog stopped"
        return $true
    }
    Write-Log "  Watchdog stop may have failed"
    return $false
}

function Show-WatchdogStatus {
    if (Test-Path $watchdogPidFile) {
        try {
            $wp = [int](Get-Content $watchdogPidFile)
            $existing = Get-Process -Id $wp -ErrorAction SilentlyContinue
            if ($existing) {
                Write-Host "  Watchdog          : RUNNING  (PID=$wp)"
            } else {
                Write-Host "  Watchdog          : STALE PID FILE (PID=$wp not found)"
            }
        } catch {
            Write-Host "  Watchdog          : STALE PID FILE"
        }
    } else {
        Write-Host "  Watchdog          : STOPPED"
    }
}

# ===== Main =====
switch ($Command) {
    'status' {
        Write-Host ''
        Write-Host "  Service Status (Port=$Port)"
        Write-Host '  ' + ('=' * 50)
        $data = Get-StatusData
        $allOk = $true
        foreach ($svc in $services.Keys) {
            $cfg = $services[$svc]
            $listening = Test-Port $cfg.port
            $known = $data.$svc
            $status = if ($listening) { 'RUNNING' } else { 'STOPPED' }
            if ($listening) {
                # [v3.18 Layer 4] 校验 listener-PID 是否跟 status.json 报的 PID 一致
                # 防止 21:54-22:29 那类 "service_manager 报 stale PID, 实际 3010 被 orphan 接管" 的 Layer 4 问题
                $listenerPid = (Get-NetTCPConnection -LocalPort $cfg.port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
                $pidMatch = ($listenerPid -eq $known.pid)
                $pidWarn = ''
                if ($listenerPid -and $known.pid -and -not $pidMatch) {
                    $pidWarn = " ⚠️  LISTENER MISMATCH: status.json PID=$($known.pid) but actual listener PID=$listenerPid (orphan process?)"
                    $allOk = $false
                } elseif ($listenerPid -and -not $known.pid) {
                    $pidWarn = " ⚠️  LISTENER ORPHAN: actual PID=$listenerPid not in status.json"
                    $allOk = $false
                }
                Write-Host "  $($cfg.name.PadRight(25)) : $status  (port=$($cfg.port), pid=$($known.pid), since=$($known.started_at))$pidWarn"
            } else {
                Write-Host "  $($cfg.name.PadRight(25)) : $status  (port=$($cfg.port))"
                $allOk = $false
            }
        }
        Show-WatchdogStatus
        Write-Host '  ' + ('=' * 50)
        if ($allOk) {
            Write-Host "  Summary: ALL SERVICES HEALTHY (Port=$Port)"
        } else {
            Write-Host "  Summary: SOME SERVICES NOT RUNNING (Port=$Port)"
        }
        exit $(if ($allOk) { 0 } else { 1 })
    }
    'preflight' {
        # [P0 v3.18+] 调试铁律入口: 跑测试/声称修复前必跑
        # 用途: 校验 .service_status_<port>.json 够新 (避免"重启了但没生效"陷阱)
        # 用法: powershell -File scripts/service_manager.ps1 preflight -Port 3010
        Write-Host ''
        Write-Host "  Preflight Check (Port=$Port, MaxAge=${MaxAge}s)"
        Write-Host '  ' + ('=' * 50)
        $ok = Test-ServiceFresh -MaxAgeSeconds $MaxAge
        Write-Host '  ' + ('=' * 50)
        if ($RequireFresh -and -not $ok) {
            exit 1
        } elseif ($ok) {
            exit 0
        } else {
            exit 1
        }
    }
    'stop' {
        if (-not (Wait-Lock)) { exit 1 }
        try {
            Stop-Watchdog
            $data = Get-StatusData
            foreach ($svc in $services.Keys) {
                Stop-Service $svc
                if ($data.PSObject.Properties.Name -contains $svc) {
                    $data.PSObject.Properties.Remove($svc)
                }
            }
            Set-StatusData $data
            # 🆕 v3.18 P2: 清理 test_temp 中的 -wal/-shm 残留
            Clean-StaleTempFiles
            # 🆕 v3.18 P0: 后端停止后删除 .architecture.lock (由 Python 端释放,
            # 但被 kill 时不会自动释放, 这里兜底删除)
            $dbLockFile = Join-Path -Path $root -ChildPath "meta\.architecture.lock"
            if (Test-Path $dbLockFile) {
                Remove-Item $dbLockFile -Force -ErrorAction SilentlyContinue
                Write-Log "[STOP] Removed stale DB lock: $dbLockFile"
            }
        } finally { Release-Lock }
        exit 0
    }
    'start' {
        if (-not (Wait-Lock)) { exit 1 }
        try {
            $data = Get-StatusData
            if (-not $data) { $data = @{} }

            $jobs = @()
            foreach ($svc in $services.Keys) {
                if (Test-Port $services[$svc].port) {
                    Write-Log "$($services[$svc].name) already running"
                    continue
                }
                $svcCfg = $services[$svc]
                $jobs += Start-Job -Name "svc-$svc" -ScriptBlock {
                    param($svcName, $svcPort, $svcWait, $svcCmd, $svcArgs, $workDir)
                    $argStr = ($svcArgs -join ' ')
                    $proc = Start-Process -FilePath $svcCmd -ArgumentList $argStr `
                        -WorkingDirectory $workDir -WindowStyle Hidden -PassThru `
                        -RedirectStandardOutput "$root\scripts\logs\$svcName.out" `
                        -RedirectStandardError "$root\scripts\logs\$svcName.err" `
                        -NoNewWindow
                    for ($i = 0; $i -lt $svcWait; $i++) {
                        Start-Sleep -Seconds 1
                        $tcp = New-Object System.Net.Sockets.TcpClient
                        try {
                            $tcp.Connect('127.0.0.1', $svcPort)
                            $tcp.Close()
                            $tcp.Dispose()
                            return @{ svc=$svcName; pid=$proc.Id; ok=$true }
                        } catch {}
                    }
                    return @{ svc=$svcName; pid=$proc.Id; ok=$false }
                } -ArgumentList $svc, $svcCfg.port, $svcCfg.wait, $svcCfg.cmd, $svcCfg.args, $root
            }

            $jobs | Wait-Job | Out-Null
            foreach ($job in $jobs) {
                $result = $job | Receive-Job
                $job | Remove-Job -Force
                if ($result.ok) {
                    $data | Add-Member -NotePropertyName $result.svc -NotePropertyValue @{
                        port = $services[$result.svc].port
                        pid = $result.pid
                        started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    } -Force
                    Write-Log "  $($services[$result.svc].name) started (PID=$($result.pid))"
                } else {
                    Write-Log "  $($services[$result.svc].name) process spawned but port not responding"
                }
            }
            Set-StatusData $data
            Start-Watchdog
        } finally { Release-Lock }
        exit 0
    }
    'start-fe' {
        if (-not (Wait-Lock)) { exit 1 }
        try { Start-Service 'frontend' } finally { Release-Lock }
        exit 0
    }
    'start-be' {
        if (-not (Wait-Lock)) { exit 1 }
        try { Start-Service 'backend' } finally { Release-Lock }
        exit 0
    }
    'restart' {
        # 检查是否有测试正在运行
        if (-not (Assert-NoRunningTests)) {
            Write-Log "ABORTED: Tests are running. Wait for them to complete or kill them first."
            Write-Log "To force restart anyway, use: service_manager.ps1 restart -Force"
            exit 1
        }

        if (-not (Wait-Lock)) { exit 1 }
        try {
            foreach ($svc in $services.Keys) {
                Stop-Service $svc
            }
            Start-Sleep -Seconds 1

            $data = Get-StatusData
            if (-not $data) { $data = @{} }

            $jobs = @()
            foreach ($svc in $services.Keys) {
                $svcCfg = $services[$svc]
                $jobs += Start-Job -Name "svc-$svc" -ScriptBlock {
                    param($svcName, $svcPort, $svcWait, $svcCmd, $svcArgs, $workDir)
                    $argStr = ($svcArgs -join ' ')
                    $proc = Start-Process -FilePath $svcCmd -ArgumentList $argStr `
                        -WorkingDirectory $workDir -WindowStyle Hidden -PassThru `
                        -RedirectStandardOutput "$root\scripts\logs\$svcName.out" `
                        -RedirectStandardError "$root\scripts\logs\$svcName.err" `
                        -NoNewWindow
                    for ($i = 0; $i -lt $svcWait; $i++) {
                        Start-Sleep -Seconds 1
                        $tcp = New-Object System.Net.Sockets.TcpClient
                        try {
                            $tcp.Connect('127.0.0.1', $svcPort)
                            $tcp.Close()
                            $tcp.Dispose()
                            return @{ svc=$svcName; pid=$proc.Id; ok=$true }
                        } catch {}
                    }
                    return @{ svc=$svcName; pid=$proc.Id; ok=$false }
                } -ArgumentList $svc, $svcCfg.port, $svcCfg.wait, $svcCfg.cmd, $svcCfg.args, $root
            }

            $jobs | Wait-Job | Out-Null
            foreach ($job in $jobs) {
                $result = $job | Receive-Job
                $job | Remove-Job -Force
                if ($result.ok) {
                    $data | Add-Member -NotePropertyName $result.svc -NotePropertyValue @{
                        port = $services[$result.svc].port
                        pid = $result.pid
                        started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    } -Force
                    Write-Log "  $($services[$result.svc].name) started (PID=$($result.pid))"
                } else {
                    Write-Log "  $($services[$result.svc].name) process spawned but port not responding"
                }
            }
            Set-StatusData $data
            Start-Watchdog
        } finally { Release-Lock }
        exit 0
    }
    'force-restart' {
        # 强制重启：跳过测试运行检测（用于确实需要重启的情况）
        Write-Log "WARNING: Force restart - skipping test detection check"
        if (-not (Wait-Lock)) { exit 1 }
        try {
            foreach ($svc in $services.Keys) {
                Stop-Service $svc
            }
            Start-Sleep -Seconds 1

            $data = Get-StatusData
            if (-not $data) { $data = @{} }

            $jobs = @()
            foreach ($svc in $services.Keys) {
                $svcCfg = $services[$svc]
                $jobs += Start-Job -Name "svc-$svc" -ScriptBlock {
                    param($svcName, $svcPort, $svcWait, $svcCmd, $svcArgs, $workDir)
                    $argStr = ($svcArgs -join ' ')
                    $proc = Start-Process -FilePath $svcCmd -ArgumentList $argStr `
                        -WorkingDirectory $workDir -WindowStyle Hidden -PassThru `
                        -RedirectStandardOutput "$root\scripts\logs\$svcName.out" `
                        -RedirectStandardError "$root\scripts\logs\$svcName.err" `
                        -NoNewWindow
                    for ($i = 0; $i -lt $svcWait; $i++) {
                        Start-Sleep -Seconds 1
                        $tcp = New-Object System.Net.Sockets.TcpClient
                        try {
                            $tcp.Connect('127.0.0.1', $svcPort)
                            $tcp.Close()
                            $tcp.Dispose()
                            return @{ svc=$svcName; pid=$proc.Id; ok=$true }
                        } catch {}
                    }
                    return @{ svc=$svcName; pid=$proc.Id; ok=$false }
                } -ArgumentList $svc, $svcCfg.port, $svcCfg.wait, $svcCfg.cmd, $svcCfg.args, $root
            }

            $jobs | Wait-Job | Out-Null
            foreach ($job in $jobs) {
                $result = $job | Receive-Job
                $job | Remove-Job -Force
                if ($result.ok) {
                    $data | Add-Member -NotePropertyName $result.svc -NotePropertyValue @{
                        port = $services[$result.svc].port
                        pid = $result.pid
                        started_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
                    } -Force
                    Write-Log "  $($services[$result.svc].name) started (PID=$($result.pid))"
                } else {
                    Write-Log "  $($services[$result.svc].name) process spawned but port not responding"
                }
            }
            Set-StatusData $data
            Start-Watchdog
        } finally { Release-Lock }
        exit 0
    }
    'watchdog' {
        Show-WatchdogStatus
        $logFile = Join-Path $root '.watchdog.log'
        if (Test-Path $logFile) {
            Write-Host ''
            Write-Host '  Recent watchdog events:'
            Get-Content $logFile -Tail 10 | ForEach-Object { Write-Host "    $_" }
        }
        exit 0
    }
    'watchdog-start' {
        if (-not (Wait-Lock)) { exit 1 }
        try { Start-Watchdog } finally { Release-Lock }
        exit 0
    }
    'watchdog-stop' {
        if (-not (Wait-Lock)) { exit 1 }
        try { Stop-Watchdog } finally { Release-Lock }
        exit 0
    }
    'list-locks' {
        # 🆕 v3.18: 列出所有已知 lock 文件的状态 (诊断用, 不依赖 $Port 参数)
        Write-Host ''
        Write-Host "  Lock Files Status (All Ports)"
        Write-Host '  ' + ('=' * 60)
        $found = $false
        # 1. 扫描 services 字典中所有端口
        $scannedPorts = @()
        foreach ($svc in $services.Keys) {
            $cfg = $services[$svc]
            $port = $cfg.port
            $scannedPorts += $port
            $lockPath = Join-Path $root ".service_manager_$port.lock"
            if (Test-Path $lockPath) {
                $found = $true
                $holder = Get-StaleLockHolder $lockPath
                $status = if ($holder -and -not $holder.IsStale) { 'ACTIVE' } else { 'STALE' }
                Write-Host "  [$status] $lockPath"
                if ($holder -and $holder.Pid) {
                    Write-Host "          Holder PID : $($holder.Pid)"
                }
                if ($holder -and $holder.Started) {
                    Write-Host "          Started at : $($holder.Started)"
                }
                if ($holder -and $holder.Command) {
                    Write-Host "          Command    : $($holder.Command)"
                }
                $age = [int]((Get-Date) - (Get-Item $lockPath).LastWriteTime).TotalSeconds
                Write-Host "          File age   : ${age}s"
            }
        }
        # 2. 也扫描 $Port 参数的 lock (即使不在 services 字典)
        if ($Port -notin $scannedPorts) {
            $lockPath = Join-Path $root ".service_manager_$Port.lock"
            if (Test-Path $lockPath) {
                $found = $true
                $holder = Get-StaleLockHolder $lockPath
                $status = if ($holder -and -not $holder.IsStale) { 'ACTIVE' } else { 'STALE' }
                Write-Host "  [$status] $lockPath"
            }
        }
        if (-not $found) {
            Write-Host "  No lock files found."
        }
        # 也检查 DB lock
        $dbLock = Join-Path -Path $root -ChildPath "meta\.architecture.lock"
        if (Test-Path $dbLock) {
            Write-Host ''
            Write-Host "  [DB LOCK] $dbLock"
            $raw = Get-Content $dbLock -ErrorAction SilentlyContinue
            if ($raw) { $raw | ForEach-Object { Write-Host "    $_" } }
        }
        Write-Host '  ' + ('=' * 60)
        exit 0
    }
    'clear-stale-lock' {
        # 🆕 v3.18: 安全清理 stale lock (持有者进程已死)
        # 这是绕过 Wait-Lock 的合规方式 - 仍然要检测 stale 才能清
        Write-Host ''
        Write-Host "  Clear Stale Lock (All Ports)"
        Write-Host '  ' + ('=' * 60)
        $cleared = 0
        $skipped = 0
        $scannedPorts = @()
        foreach ($svc in $services.Keys) {
            $cfg = $services[$svc]
            $port = $cfg.port
            $scannedPorts += $port
            $lockPath = Join-Path $root ".service_manager_$port.lock"
            if (-not (Test-Path $lockPath)) { continue }
            $holder = Get-StaleLockHolder $lockPath
            if ($holder -and -not $holder.IsStale) {
                Write-Host "  [SKIP] $lockPath is HELD by LIVE PID=$($holder.Pid)"
                Write-Host "         Started: $($holder.Started), Command: $($holder.Command)"
                Write-Host "         Cannot clear. Either wait for the process to finish or kill it."
                $skipped++
                continue
            }
            if ($holder) {
                Write-Host "  [CLEAR] $lockPath (stale, PID=$($holder.Pid) not alive)"
            } else {
                Write-Host "  [CLEAR] $lockPath (unparseable, removing anyway)"
            }
            Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
            $cleared++
        }
        # 也清理 $Port 参数的 lock (即使不在 services 字典)
        if ($Port -notin $scannedPorts) {
            $lockPath = Join-Path $root ".service_manager_$Port.lock"
            if (Test-Path $lockPath) {
                $holder = Get-StaleLockHolder $lockPath
                if ($holder -and -not $holder.IsStale) {
                    Write-Host "  [SKIP] $lockPath is HELD by LIVE PID=$($holder.Pid)"
                    $skipped++
                } else {
                    Write-Host "  [CLEAR] $lockPath (stale)"
                    Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
                    $cleared++
                }
            }
        }
        # 也清理 DB lock
        $dbLock = Join-Path -Path $root -ChildPath "meta\.architecture.lock"
        if (Test-Path $dbLock) {
            $raw = Get-Content $dbLock -ErrorAction SilentlyContinue
            $holderPid = $null
            if ($raw -and $raw[0] -match '^\d+$') { $holderPid = [int]$raw[0] }
            $isAlive = $false
            if ($holderPid) {
                $proc = Get-Process -Id $holderPid -ErrorAction SilentlyContinue
                $isAlive = ($null -ne $proc)
            }
            if (-not $isAlive) {
                Write-Host "  [CLEAR] $dbLock (stale DB lock)"
                Remove-Item $dbLock -Force -ErrorAction SilentlyContinue
                $cleared++
            } else {
                Write-Host "  [SKIP] $dbLock is HELD by LIVE PID=$holderPid"
                $skipped++
            }
        }
        Write-Host '  ' + ('=' * 60)
        if ($cleared -gt 0) {
            Write-Host "  Cleared $cleared stale lock(s), skipped $skipped active lock(s)."
            exit 0
        } else {
            if ($skipped -gt 0) {
                Write-Host "  No stale locks. $skipped active lock(s) held."
                exit 1
            } else {
                Write-Host "  No lock files found."
                exit 0
            }
        }
    }
}
