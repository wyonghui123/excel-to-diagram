# scripts/debug/hooks_shell_guard.ps1
# PreToolUse Hook - 命令工具三条硬拦截（L1 / L2 / L3）
#
# L1: 禁裸 pytest        -> 唯一入口 python d:\filework\test.py
# L2: 禁 curl 别名        -> 用 curl.exe
# L3: 禁 Get-Process python 判活 / taskkill /IM python.exe 杀服务 -> 用 service_manager
#
# 契约：stdin 为 JSON {tool_name, tool_input:{command}}；exit 2 + JSON = 拒绝，exit 0 = 放行。
# 任何内部异常一律放行（fail-open），避免 hook 自身故障堵死所有命令。

$ErrorActionPreference = 'Stop'

function Write-Allow {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# 项目根（用于日志路径）
$projectRoot = $env:TRAE_PROJECT_DIR
if (-not $projectRoot) {
    $hookDir = Split-Path -Parent $PSCommandPath
    $projectRoot = Split-Path -Parent (Split-Path -Parent $hookDir)
}
$projectRoot = $projectRoot -replace '/', '\'

# 1. 读取 stdin
$raw = ''
try { $raw = [Console]::In.ReadToEnd() } catch { Write-Allow }
if (-not $raw) { Write-Allow }

# 2. 解析 payload
$payload = $null
try { $payload = $raw | ConvertFrom-Json -ErrorAction Stop } catch { Write-Allow }

$toolName = [string]$payload.tool_name
if (-not $toolName) { $toolName = [string]$env:TRAE_TOOL_NAME }

# 只关心命令类工具（不同 Trae 版本命名不同，全部兼容）
$shellTools = @('Bash', 'Shell', 'run_command', 'RunCommand', 'runCommand', 'execute_command')
if ($shellTools -notcontains $toolName) { Write-Allow }

# 3. 提取命令文本
$cmd = ''
if ($payload.tool_input -is [string]) {
    $cmd = [string]$payload.tool_input
} elseif ($payload.tool_input) {
    foreach ($k in @('command', 'cmd', 'shell_command', 'script')) {
        $v = $payload.tool_input.$k
        if ($v) { $cmd = [string]$v; break }
    }
}
if (-not $cmd) { $cmd = [string]$env:TRAE_TOOL_INPUT }
if (-not $cmd) { Write-Allow }

# 4. 规则表（只覆盖 L1/L2/L3 三条，不扩大范围）
$rules = @(
    @{
        Rule    = 'L1'
        Test    = '(?i)(?<![\w.])pytest(\.exe)?(?![\w.])'
        Reason  = '禁止直接运行 pytest（铁律 L1）。唯一入口：python d:\filework\test.py --failed|--all|--single|--file'
    },
    @{
        Rule    = 'L2'
        Test    = '(?i)(?<![\w.\\/-])curl(?!\.exe)(?![\w.-])'
        Reason  = '禁止使用 curl 别名（铁律 L2，PowerShell 中是 Invoke-WebRequest）。请改用 curl.exe'
    },
    @{
        Rule    = 'L3'
        Test    = '(?i)(?<![\w.-])Get-Process(?![\w-])[^;|&]*?(?<![\w.-])python'
        Reason  = '禁止用 Get-Process python 判活（铁律 L3）。请用 python scripts/service_manager.py status'
    },
    @{
        Rule    = 'L3'
        Test    = '(?i)\btaskkill(\.exe)?\b[^;|&]*\/im\s+["'']?python'
        Reason  = '禁止用 taskkill /IM python*.exe 杀服务（铁律 L3）。请用 python scripts/service_manager.py stop|restart'
    }
)

$hit = $null
foreach ($r in $rules) {
    try {
        if ($cmd -match $r.Test) { $hit = $r; break }
    } catch { }
}
if (-not $hit) { Write-Allow }

# 5. 拒绝
$reason = "[$($hit.Rule) Hook 拦截] $($hit.Reason)`n命令: $($cmd)"

$response = @{
    hookSpecificOutput = @{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = $reason
    }
} | ConvertTo-Json -Depth 3

try {
    $logDir = Join-Path $projectRoot '.trae\debug\logs'
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssZ')
    Add-Content -Path (Join-Path $logDir 'hook_violations.log') `
        -Value "[$ts] DENY $toolName ($($hit.Rule)) $cmd" -ErrorAction SilentlyContinue
} catch { }

Write-Host $response
exit 2