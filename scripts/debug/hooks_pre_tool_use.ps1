# scripts/debug/hooks_pre_tool_use.ps1
# V4.0 PreToolUse Hook - 拦截根目录调试脚本写入
#
# V4.0.1 修复：用 TRAE_PROJECT_DIR 动态检测项目根（不在硬编码路径）

# V4.0: 禁用 .ps1 写日志避免 hook 递归
$ErrorActionPreference = 'Stop'

# V4.0.1: 动态检测项目根（关键修复 - 不再硬编码路径）
$projectRoot = $env:TRAE_PROJECT_DIR
if (-not $projectRoot) {
    # 回退：从 hook 脚本位置推断
    $hookDir = Split-Path -Parent $PSCommandPath
    $projectRoot = Split-Path -Parent (Split-Path -Parent $hookDir)
}
$projectRoot = $projectRoot -replace '/', '\'

# 读取 stdin
$raw = ''
try {
    $raw = [Console]::In.ReadToEnd()
} catch {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

if (-not $raw) {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

try {
    $payload = $raw | ConvertFrom-Json -ErrorAction Stop
} catch {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

$toolName = $payload.tool_name
if ($toolName -ne 'Write') {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

$filePath = $payload.tool_input.file_path
if (-not $filePath) {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# V4.0 违规模式：项目根目录的调试脚本（包括 .py 和 .ps1）
$violationPatterns = @(
    'debug_.*\.py$'
    'analyze_.*\.py$'
    'query_.*\.py$'
    'check_.*\.py$'
    'test_.*\.py$'
    'inspect_.*\.py$'
    'tmp_.*\.py$'
    'tmp\.py$'
    '_debug.*\.py$'
    '_test.*\.py$'
    '_restart.*\.ps1$'      # V4.0.1: 新增 .ps1 模式
    '_debug.*\.ps1$'
    '_test.*\.ps1$'
)

# 提取相对路径
$relPath = $filePath

# 规范化路径（统一使用 \）
$normalizedFilePath = $filePath -replace '/', '\'

if ($normalizedFilePath.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relPath = $normalizedFilePath.Substring($projectRoot.Length).TrimStart('\', '/')
}

# 根目录判断：相对路径不包含 \ 或 /（说明在项目根目录）
$isInRoot = -not ($relPath.Contains('\') -or $relPath.Contains('/'))

if (-not $isInRoot) {
    # 不在根目录 - 允许
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# 检查是否匹配违规模式
$fileName = Split-Path -Leaf $relPath
$matchedPattern = $null
foreach ($pat in $violationPatterns) {
    if ($fileName -match $pat) {
        $matchedPattern = $pat
        break
    }
}

if (-not $matchedPattern) {
    # 不匹配违规模式 - 允许
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# V4.0: 命中违规模式 - 拒绝
$reason = "[V4.0 Hook 拦截] 禁止在项目根目录写入调试脚本: '$fileName' (匹配模式: $matchedPattern)。`n"
$reason += "应该写到:`n"
$reason += "  - scripts/debug/test_<name>.py (测试脚本)`n"
$reason += "  - scripts/debug/check_<name>.py (检查脚本)`n"
$reason += "  - scripts/debug/analyze_<name>.py (分析脚本)`n"
$reason += "  - scripts/debug/tmp/<name>.py (临时脚本,避免提交)`n"
$reason += "参考: docs/V4_REFACTOR.md 第 3 节"

$response = @{
    hookSpecificOutput = @{
        hookEventName = "PreToolUse"
        permissionDecision = "deny"
        permissionDecisionReason = $reason
    }
} | ConvertTo-Json -Depth 3 -EscapeHandling EscapeNonAscii

# 记录违规到日志
$logDir = Join-Path $projectRoot '.trae\debug\logs'
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logFile = Join-Path $logDir 'hook_violations.log'
$ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssZ')
Add-Content -Path $logFile -Value "[$ts] DENY Write $filePath (matched: $matchedPattern)" -ErrorAction SilentlyContinue

Write-Host $response
exit 2  # 退出码 2 = 拒绝