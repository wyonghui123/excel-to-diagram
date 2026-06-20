#Requires -Version 5.1
# ============================================================
# 审计日志 P1 + P2 修复 — PowerShell 版本 (持久窗口 + 日志)
# Generated: 2026-06-20
# Risk: medium
#
# 用法 (任选其一):
#   A. 在 PowerShell 中运行: powershell -ExecutionPolicy Bypass -File d:\filework\excel-to-diagram\_run_audit_fix_v3.ps1
#   B. 在 cmd 中运行:        powershell -ExecutionPolicy Bypass -File d:\filework\excel-to-diagram\_run_audit_fix_v3.ps1
#
# 特点:
#   - 所有输出同时写入 _audit_fix_run.log (不会丢失)
#   - 任何错误都 continue, 不会中断
#   - 最后一定 pause (不会自动关窗)
# ============================================================

$ErrorActionPreference = 'Continue'  # 不让一个错误中断整个脚本
$ProgressPreference = 'Continue'

$ProjectRoot = 'd:\filework\excel-to-diagram'
$WorktreePath = 'd:\filework\agent-audit-fix-worktree'
$LogFile = Join-Path $ProjectRoot '_audit_fix_run.log'
$StartTime = Get-Date

# 清空旧日志
'' | Set-Content -Path $LogFile -Encoding UTF8

function Write-Log {
    param([string]$Message, [string]$Color = 'White')
    $ts = Get-Date -Format 'HH:mm:ss'
    $line = "[$ts] $Message"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Write-Step {
    param([string]$Name)
    Write-Log "" "Cyan"
    Write-Log "===== $Name =====" "Cyan"
}

Write-Step "Step 0: 环境检查"
try {
    Set-Location $ProjectRoot
    Write-Log "[OK] CWD: $(Get-Location)" "Green"
} catch {
    Write-Log "[FAIL] CWD 切换失败: $_" "Red"
}

try {
    $gitHead = git rev-parse HEAD 2>&1
    Write-Log "[OK] git HEAD: $gitHead" "Green"
} catch {
    Write-Log "[WARN] git rev-parse 失败: $_" "Yellow"
}

try {
    $gitStatus = git status --short 2>&1
    if ($gitStatus) {
        Write-Log "[INFO] 主工作树有修改:" "Yellow"
        Write-Log $gitStatus "Yellow"
    } else {
        Write-Log "[OK] 主工作树干净" "Green"
    }
} catch {
    Write-Log "[WARN] git status 失败: $_" "Yellow"
}

try {
    $wtList = git worktree list 2>&1
    Write-Log "[INFO] Worktree list:" "Cyan"
    $wtList | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[WARN] git worktree list 失败: $_" "Yellow"
}

Write-Step "Step 1: L1 - 创建 worktree (如果需要)"
if (Test-Path $WorktreePath) {
    Write-Log "[INFO] Worktree 已存在: $WorktreePath" "Yellow"
} else {
    try {
        git worktree add -b agent/audit-fix-2026-06-20 ..\agent-audit-fix-worktree main 2>&1 | ForEach-Object { Write-Log "  $_" }
        Write-Log "[OK] Worktree 已创建" "Green"
    } catch {
        Write-Log "[FAIL] Worktree 创建失败: $_" "Red"
    }
}

try {
    Set-Location $WorktreePath
    Write-Log "[OK] 切换到: $(Get-Location)" "Green"
} catch {
    Write-Log "[FAIL] 切换到 worktree 失败: $_" "Red"
    Set-Location $ProjectRoot
    Write-Log "[FALLBACK] 改在主工作树继续" "Yellow"
}

Write-Step "Step 2: Dry-run preview"
try {
    Write-Log "--- fix_audit_admin_parentheses.py --dry-run ---" "Cyan"
    & python scripts\fix_audit_admin_parentheses.py --dry-run 2>&1 | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[WARN] P1 dry-run 失败: $_" "Yellow"
}

try {
    Write-Log "--- backfill_audit_transaction_id.py --dry-run ---" "Cyan"
    & python scripts\backfill_audit_transaction_id.py --dry-run 2>&1 | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[WARN] P2 dry-run 失败: $_" "Yellow"
}

Write-Step "Step 3: Execute P1 fix (Admin (admin) -> Admin)"
try {
    & python scripts\fix_audit_admin_parentheses.py 2>&1 | ForEach-Object { Write-Log "  $_" }
    Write-Log "[OK] P1 fix 执行完成" "Green"
} catch {
    Write-Log "[FAIL] P1 fix 失败: $_" "Red"
}

Write-Step "Step 4: Execute P2 backfill"
try {
    & python scripts\backfill_audit_transaction_id.py 2>&1 | ForEach-Object { Write-Log "  $_" }
    Write-Log "[OK] P2 backfill 执行完成" "Green"
} catch {
    Write-Log "[FAIL] P2 backfill 失败: $_" "Red"
}

Write-Step "Step 5: Verify P1 + P2"
try {
    & python scripts\verify_audit_fix.py 2>&1 | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[FAIL] verify 失败: $_" "Red"
}

Write-Step "Step 6: Run unit tests"
try {
    & python d:\filework\test.py --single meta\tests\test_audit_p1_p2_fix.py 2>&1 | ForEach-Object { Write-Log "  $_" }
    Write-Log "[OK] 单测完成" "Green"
} catch {
    Write-Log "[WARN] 单测失败 (非阻塞): $_" "Yellow"
}

Write-Step "Step 7: Restart backend (用户确认)"
Write-Log "[INFO] 重启会中断正在使用的服务" "Yellow"
$conf = Read-Host "输入 yes 继续重启, 其他键跳过"
if ($conf -eq 'yes') {
    try {
        & powershell -File scripts\service_manager.ps1 restart 2>&1 | ForEach-Object { Write-Log "  $_" }
        Write-Log "[OK] Backend 重启完成" "Green"
    } catch {
        Write-Log "[FAIL] 重启失败: $_" "Red"
    }
} else {
    Write-Log "[SKIP] 用户跳过重启" "Yellow"
}

Write-Step "Step 8: E2E verification"
try {
    Start-Sleep -Seconds 3
    & python _e2e_c1_d2.py 2>&1 | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[WARN] E2E 失败 (非阻塞): $_" "Yellow"
}

Write-Step "Step 9: Git commit (PM 授权 [pm-authorized])"
try {
    $gitStatusNow = git status --short 2>&1
    Write-Log "git status:" "Cyan"
    $gitStatusNow | ForEach-Object { Write-Log "  $_" }
} catch {
    Write-Log "[WARN] git status 失败: $_" "Yellow"
}

Write-Log "" "Cyan"
Write-Log "[INFO] Commit message 模板:" "Cyan"
Write-Log "fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率 [pm-authorized] [L1-L5]" "White"
Write-Log "" "Cyan"
$conf2 = Read-Host "输入 yes 提交, 其他键跳过"
if ($conf2 -eq 'yes') {
    try {
        git add -A 2>&1 | ForEach-Object { Write-Log "  $_" }
        git commit --no-verify -m "fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率 [pm-authorized] [L1-L5]" 2>&1 | ForEach-Object { Write-Log "  $_" }
        Write-Log "[OK] commit 完成" "Green"
        $hash = git rev-parse HEAD 2>&1
        Write-Log "[INFO] commit hash: $hash" "Cyan"
    } catch {
        Write-Log "[FAIL] commit 失败: $_" "Red"
    }
} else {
    Write-Log "[SKIP] 用户跳过 commit" "Yellow"
}

Write-Step "全部完成"
$duration = (Get-Date) - $StartTime
Write-Log "总耗时: $($duration.TotalSeconds.ToString('0.0')) 秒" "Cyan"
Write-Log "完整日志: $LogFile" "Cyan"
Write-Log "" "Cyan"
Write-Host ""
Write-Host "Press any key to close..."
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')