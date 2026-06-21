# scripts/debug/hooks_pre_tool_use.ps1
# V4.0 PreToolUse Hook - 拦截根目录调试脚本写入
#
# 背景：Agent 持续在项目根目录写 debug_*.py / analyze_*.py / query_*.py 等临时调试脚本，
#       每次写都增加 .agent-violations.json 计数（已累积 348 个）。
#       V3 dashboard 能检测但不能阻止。V4.0 在 hook 层强制拦截。
#
# 输入：stdin JSON (Trae Hook 格式)
#   {
#     "tool_name": "Write",
#     "tool_input": {"file_path": "...", "content": "..."},
#     ...
#   }
#
# 输出：stdout JSON (Hook 决策)
#   {
#     "hookSpecificOutput": {
#       "hookEventName": "PreToolUse",
#       "permissionDecision": "deny",
#       "permissionDecisionReason": "..."
#     }
#   }
#
# 退出码 0 = 正常；2 = 拒绝

# V4.0: 禁用 .ps1 写日志避免 hook 递归
$ErrorActionPreference = 'Stop'

# 读取 stdin
$raw = ''
try {
    $raw = [Console]::In.ReadToEnd()
} catch {
    # 没有 stdin 输入 - 允许
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

if (-not $raw) {
    Write-Host '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# 解析 JSON
try {
    $payload = $raw | ConvertFrom-Json -ErrorAction Stop
} catch {
    # JSON 解析失败 - 允许
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

# V4.0 违规模式：项目根目录的调试脚本
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
)

# 提取相对路径（项目根目录判断）
$projectRoot = 'd:\filework\excel-to-diagram'
$relPath = $filePath

# 规范化路径（统一使用 / 或 \）
$normalizedFilePath = $filePath -replace '/', '\'

if ($normalizedFilePath.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    $relPath = $normalizedFilePath.Substring($projectRoot.Length).TrimStart('\', '/')
} elseif ($normalizedFilePath.StartsWith('d:\filework\excel-to-diagram', [System.StringComparison]::OrdinalIgnoreCase)) {
    $relPath = $normalizedFilePath.Substring('d:\filework\excel-to-diagram'.Length).TrimStart('\', '/')
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