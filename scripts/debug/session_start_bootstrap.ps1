# scripts/debug/session_start_bootstrap.ps1
# V4.0 SessionStart Hook - 自动启动 watchdog + 后端检查
#
# 背景：2026-06-21 调试事故 - 用户重启 Trae IDE 后：
#       1. watchdog 进程被杀死（powershell -File watchdog.ps1 -Interval 30）
#       2. 后端进程被杀死（python.exe waitress_server.py）
#       3. Agent 不知道这两个服务挂了，盲目调试 → 误以为服务在跑
#
# V4.0 修复：Trae SessionStart 时自动检查并启动必要服务。
#
# 输入：stdin JSON (Trae Hook 格式)
#   {
#     "session_id": "...",
#     "hook_event_name": "SessionStart",
#     "source": "startup"
#   }
#
# 输出：stdout 纯文本（注入到模型上下文的提示）

$ErrorActionPreference = 'Continue'

# V4.0.1: 动态检测项目根（不再硬编码路径）
$projectRoot = $env:TRAE_PROJECT_DIR
if (-not $projectRoot) {
    $bootstrapDir = Split-Path -Parent $PSCommandPath
    $projectRoot = Split-Path -Parent (Split-Path -Parent $bootstrapDir)
}
$projectRoot = $projectRoot -replace '/', '\'

# 读取 stdin（仅用于验证 hook 被触发）
$raw = ''
try {
    $raw = [Console]::In.ReadToEnd()
} catch {
    $raw = ''
}

$messages = @()
$messages += "[V4.0 SessionStart Bootstrap] 启动中..."

# 检查 watchdog
$watchdogPidFile = Join-Path $projectRoot '.watchdog.pid'
$watchdogRunning = $false
if (Test-Path $watchdogPidFile) {
    try {
        $wp = [int](Get-Content $watchdogPidFile -ErrorAction SilentlyContinue)
        $existing = Get-Process -Id $wp -ErrorAction SilentlyContinue
        if ($existing) {
            $watchdogRunning = $true
            $messages += "[OK] watchdog 已在跑 (PID=$wp)"
        }
    } catch {}
}

if (-not $watchdogRunning) {
    $messages += "[i] watchdog 未运行,启动中..."
    $watchdogScript = Join-Path $projectRoot 'scripts\watchdog.ps1'
    if (Test-Path $watchdogScript) {
        try {
            $wp = Start-Process -FilePath 'powershell' `
                -ArgumentList "-File `"$watchdogScript`" -Interval 30" `
                -WorkingDirectory $projectRoot `
                -WindowStyle Hidden -PassThru
            Start-Sleep -Seconds 1
            if ($wp -and -not $wp.HasExited) {
                $messages += "[OK] watchdog 启动成功 (PID=$($wp.Id))"
            } else {
                $messages += "[X] watchdog 启动失败"
            }
        } catch {
            $messages += "[X] watchdog 启动异常: $_"
        }
    } else {
        $messages += "[X] watchdog 脚本不存在: $watchdogScript"
    }
}

# 检查后端（仅警告，不自动启动 - 避免阻塞 SessionStart）
$backendPort = 3010
$backendUp = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect('127.0.0.1', $backendPort)
    $tcp.Close()
    $backendUp = $true
} catch {
    $backendUp = $false
}

if ($backendUp) {
    $messages += "[OK] 后端端口 $backendPort 监听中"
} else {
    $messages += "[!] 后端端口 $backendPort 未监听 (重启 IDE 后被杀,可用 'python scripts/debug/restart/restart_safe.py start' 启动)"
}

# 检查 Terminal 锁定（V4.0 新增）
$terminalLockFile = Join-Path $projectRoot '.terminal_lock.json'
if (Test-Path $terminalLockFile) {
    try {
        $lock = Get-Content $terminalLockFile -Raw | ConvertFrom-Json
        $messages += "[!] Terminal 锁定: $($lock.reason) (locked at $($lock.locked_at))"
    } catch {}
}

# 输出纯文本到模型上下文
$output = $messages -join "`n"
Write-Host $output
exit 0