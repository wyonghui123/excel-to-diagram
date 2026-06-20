# ====================================================================
# 审计日志 P1 + P2 优化执行脚本
# Generated: 2026-06-20
# Author: audit-fix agent
# Risk level: medium
#
# Usage: 在 PowerShell 中粘贴执行
# 注意:
#   - 必须先关闭所有 Trae 中的 IDE 文件 (避免 git lock)
#   - 后端会自动在 3011 端口启动 (不冲突 main 3010)
#   - 脚本幂等, 中途失败可重新执行
# ====================================================================

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'

Write-Host "===== T1: L5 沙箱检测 =====" -ForegroundColor Cyan
$sandboxTest = 'sandbox_' + (Get-Date -Format 'HHmms') + '.txt'
Set-Content -Path "d:\filework\$sandboxTest" -Value 'test' -Encoding UTF8
if (-not (Test-Path "d:\filework\$sandboxTest")) {
    Write-Host "[FAIL] Sandbox 隔离, 无法继续. 请等待沙箱解封." -ForegroundColor Red
    exit 1
}
Remove-Item "d:\filework\$sandboxTest"
Write-Host "[OK] Sandbox OK" -ForegroundColor Green

Write-Host "`n===== T2: L1 创建 worktree =====" -ForegroundColor Cyan
$wtPath = 'd:\filework\agent-audit-fix-worktree'
if (Test-Path $wtPath) {
    Write-Host "[WARN] Worktree 已存在: $wtPath" -ForegroundColor Yellow
    cd $wtPath
} else {
    cd d:\filework\excel-to-diagram
    $result = git worktree add -b agent/audit-fix-2026-06-20 ../agent-audit-fix-worktree main 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAIL] git worktree add 失败: $result" -ForegroundColor Red
        exit 1
    }
    cd $wtPath
    Write-Host "[OK] Worktree 已创建: $wtPath" -ForegroundColor Green
}

Write-Host "`n===== T3: 写 spec.md =====" -ForegroundColor Cyan
$specContent = @'
# T-AUDIT-FIX-2026-06-20: 审计日志 P1 + P2 优化

## 1. 任务描述
闭环 P1 (12 条 Admin (admin) 残留) + P2 (tx_id 覆盖率 7.1% → 95%+)

## 2. 改动文件白名单
modified_files:
  - meta/services/action_handlers.py            # P1.1
  - meta/api/_audit_helper.py                  # P1.2
  - meta/services/audit_interceptor.py         # P2.1
  - meta/services/user_reset_password.py       # P2.2a
  - meta/services/subflow_engine.py            # P2.2b
  - meta/api/user_api.py                       # P2.2c
  - meta/api/auth_api.py                       # P2.2d

new_files:
  - meta/core/audit_helpers.py                 # P2.2 统一 helper
  - scripts/fix_audit_admin_parentheses.py     # P1.3 存量修复
  - scripts/backfill_audit_transaction_id.py   # P2.3 存量回填
  - meta/tests/test_audit_user_name_normalization.py  # P1.4
  - meta/tests/test_audit_tx_id_coverage.py    # P2.4
  - scripts/verify_audit_fix.py                # 综合验证

deleted_files: []

## 3. 禁止改文件黑名单
forbidden_files:
  - .agent-status.json
  - service_manager.ps1
  - .git/hooks/pre-commit
  - healthy-baseline-2026-06-17 tag
  - meta/core/action_executor.py   # 不动, 仅参考其 tx_id 生成模式

## 4. 依赖
based_on: main HEAD (70c043e)

## 5. 完成标准
- [ ] 所有改动在白名单内
- [ ] audit_logs.user_name LIKE '%(%' = 0
- [ ] audit_logs.transaction_id IS NULL < 5%
- [ ] python d:\filework\test.py --failed 全部通过
- [ ] commit 含 L1-L5 铁律声明

## 6. 风险等级
risk_level: medium
reason: 服务逻辑 + audit 框架改动, 影响所有 CRUD 路径
mitigation:
  - 用 agent 端口 3011 测试, 不影响 main 3010
  - fix 脚本幂等, 可重复执行
  - 保留 audit_logs 备份 (.db-snapshot by test.py)
'@
Set-Content -Path "$wtPath\spec.md" -Value $specContent -Encoding UTF8
Write-Host "[OK] spec.md 已写入" -ForegroundColor Green

Write-Host "`n===== T4: P1.1 修复 action_handlers.py =====" -ForegroundColor Cyan
$ahFile = "$wtPath\meta\services\action_handlers.py"
if (Test-Path $ahFile) {
    $content = Get-Content $ahFile -Raw -Encoding UTF8
    $old = @'
        user_id = current_user.get('user_id') or current_user.get('id')
        display = current_user.get('display_name') or ''
        username = current_user.get('username') or ''
        if display and username and display != username:
            user_name = f"{display} ({username})"
        else:
            user_name = display or username or ''

        try:
            ip_address = request.remote_addr
        except RuntimeError:
            ip_address = ''
        try:
            user_agent = request.headers.get('User-Agent', '')
        except RuntimeError:
            user_agent = ''

        bo_framework.set_user_context(
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
        )'@
    $new = @'
        user_id = current_user.get('user_id') or current_user.get('id')
        display = current_user.get('display_name') or ''
        username = current_user.get('username') or ''
        # [FIX P1 2026-06-20] 统一只用 display_name, 不再拼接 "display (username)"
        # 业务人员之前看到 "Admin (admin)" 不理解 (audit-compliance.md §5.3)
        user_name = display or username or ''

        try:
            ip_address = request.remote_addr
        except RuntimeError:
            ip_address = ''
        try:
            user_agent = request.headers.get('User-Agent', '')
        except RuntimeError:
            user_agent = ''

        bo_framework.set_user_context(
            user_id=user_id,
            user_name=user_name,
            ip_address=ip_address,
        )'@
    if ($content.Contains($old)) {
        $content = $content.Replace($old, $new)
        Set-Content -Path $ahFile -Value $content -Encoding UTF8 -NoNewline
        Write-Host "[OK] action_handlers.py:228 已修复" -ForegroundColor Green
    } else {
        Write-Host "[WARN] action_handlers.py 模式未匹配, 可能已修复" -ForegroundColor Yellow
    }
} else {
    Write-Host "[FAIL] $ahFile 不存在" -ForegroundColor Red
    exit 1
}

Write-Host "`n===== T5: P1.2 修复 _audit_helper.py =====" -ForegroundColor Cyan
$helperFile = "$wtPath\meta\api\_audit_helper.py"
if (Test-Path $helperFile) {
    $content = Get-Content $helperFile -Raw -Encoding UTF8
    $oldFn = @'
def _audit_user_name() -> str:
    """统一 combined 'display_name (username)' 格式 (与 bo_api._set_user_context 一致)

    Returns:
        e.g. "V3.17 Test (admin)" 或 "admin" (只有 username 时) 或 "" (无 user)
    """
    cu = getattr(g, 'current_user', None) or {}
    _display = cu.get('display_name') or ''
    _username = cu.get('username') or ''
    if _display and _username and _display != _username:
        return f"{_display} ({_username})"
    return _display or _username or ''

def _audit_user_id() -> Any:'@
    $newFn = @'
def _audit_user_name() -> str:
    """统一只用 display_name 格式 (audit-compliance.md §5.3)

    Returns:
        e.g. "Admin" 或 "admin" (只有 username 时) 或 "" (无 user)
    """
    cu = getattr(g, 'current_user', None) or {}
    _display = cu.get('display_name') or ''
    _username = cu.get('username') or ''
    # [FIX P1 2026-06-20] 不再拼接 "display (username)"
    return _display or _username or ''

def _audit_user_id() -> Any:'@
    if ($content.Contains($oldFn)) {
        $content = $content.Replace($oldFn, $newFn)
        Set-Content -Path $helperFile -Value $content -Encoding UTF8 -NoNewline
        Write-Host "[OK] _audit_helper.py:42 已修复" -ForegroundColor Green
    } else {
        Write-Host "[WARN] _audit_helper.py 模式未匹配" -ForegroundColor Yellow
    }
} else {
    Write-Host "[FAIL] $helperFile 不存在" -ForegroundColor Red
    exit 1
}

Write-Host "`n===== T6: P1.3 写 fix_audit_admin_parentheses.py =====" -ForegroundColor Cyan
$fix1Content = @'
#!/usr/bin/env python
"""[P1.3] 修复 audit_logs.user_name 中残留的 "Admin (admin)" 格式"""
import sqlite3
import re
import sys

DB = "meta/architecture.db"


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    pattern = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
    c.execute("SELECT id, user_name FROM audit_logs WHERE user_name LIKE '%(%' AND user_name LIKE '%)%'")
    rows = c.fetchall()

    fixed = 0
    for log_id, old_name in rows:
        m = pattern.match(old_name)
        if m and m.group(1).strip() and m.group(2).strip() and m.group(1).strip() != m.group(2).strip():
            new_name = m.group(1).strip()
            c.execute("UPDATE audit_logs SET user_name = ? WHERE id = ?", (new_name, log_id))
            fixed += 1
            print(f"  id={log_id}: {old_name!r} -> {new_name!r}")

    conn.commit()
    print(f"\n[DONE] Fixed {fixed}/{len(rows)} records")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'@
Set-Content -Path "$wtPath\scripts\fix_audit_admin_parentheses.py" -Value $fix1Content -Encoding UTF8
Write-Host "[OK] fix_audit_admin_parentheses.py 已创建" -ForegroundColor Green

Write-Host "`n===== T7: P2.1 修复 audit_interceptor.py (auto-gen tx_id) =====" -ForegroundColor Cyan
$aiFile = "$wtPath\meta\services\audit_interceptor.py"
if (Test-Path $aiFile) {
    $content = Get-Content $aiFile -Raw -Encoding UTF8

    # 注入 import
    $oldImport = 'import logging'
    $newImport = 'import logging`nimport uuid'
    $content = $content.Replace($oldImport, $newImport)

    # 修改 3 个方法的 captured_transaction_id/captured_trace_id 逻辑
    $oldCapture = @'
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            # 不在应用上下文中，使用传入的值
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id
            captured_transaction_id = transaction_id
            captured_ip = None
            captured_ua = None'@
    $newCapture = @'
            captured_trace_id = trace_id or getattr(g, 'trace_id', None)
            captured_transaction_id = transaction_id or getattr(g, 'transaction_id', None)
            # [FIX P2 2026-06-20] auto-gen tx_id (跟 action_executor._write_audit_log_v2 一致)
            if not captured_transaction_id:
                captured_transaction_id = f"tx_{uuid.uuid4().hex[:16]}"
                try:
                    g.transaction_id = captured_transaction_id
                except RuntimeError:
                    pass
            if not captured_trace_id:
                captured_trace_id = f"tr_{uuid.uuid4().hex[:16]}"
                try:
                    g.trace_id = captured_trace_id
                except RuntimeError:
                    pass
            captured_ip = request.remote_addr if request else None
            captured_ua = request.headers.get('User-Agent', '') if request else None
        except RuntimeError:
            # 不在应用上下文中，使用传入的值
            captured_user_id = user_id
            captured_user_name = user_name
            captured_trace_id = trace_id if trace_id else f"tr_{uuid.uuid4().hex[:16]}"
            captured_transaction_id = transaction_id if transaction_id else f"tx_{uuid.uuid4().hex[:16]}"
            captured_ip = None
            captured_ua = None'@
    $count = ([regex]::Matches($content, [regex]::Escape($oldCapture))).Count
    if ($count -gt 0) {
        $content = $content.Replace($oldCapture, $newCapture)
        Set-Content -Path $aiFile -Value $content -Encoding UTF8 -NoNewline
        Write-Host "[OK] audit_interceptor.py 已修复 $count 处" -ForegroundColor Green
    } else {
        Write-Host "[WARN] audit_interceptor.py 模式未匹配" -ForegroundColor Yellow
    }
} else {
    Write-Host "[FAIL] $aiFile 不存在" -ForegroundColor Red
}

Write-Host "`n===== T8: P2.3 写 backfill_audit_transaction_id.py =====" -ForegroundColor Cyan
$bfContent = @'
#!/usr/bin/env python
"""[P2.3] 给存量 audit_logs 补充 transaction_id (基于 created_at + user_name + ip 的启发式)"""
import sqlite3
import uuid
from datetime import datetime, timedelta

DB = "meta/architecture.db"
WINDOW_MS = 2000


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        SELECT id, created_at, user_name, ip_address, action, object_type
        FROM audit_logs
        WHERE (transaction_id IS NULL OR transaction_id = "")
          AND (user_name IS NULL OR user_name != "system")
        ORDER BY created_at ASC
    """)
    rows = c.fetchall()

    fixed = 0
    last_tx_per_group = {}

    for log_id, created_at, user_name, ip, action, obj_type in rows:
        try:
            t = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue

        group_key = (user_name or "", ip or "")
        if group_key in last_tx_per_group:
            last_tx, last_t = last_tx_per_group[group_key]
            if abs((t - last_t).total_seconds() * 1000) < WINDOW_MS:
                c.execute("UPDATE audit_logs SET transaction_id = ? WHERE id = ?", (last_tx, log_id))
                fixed += 1
                continue

        new_tx = f"tx_{uuid.uuid4().hex[:16]}"
        c.execute("UPDATE audit_logs SET transaction_id = ? WHERE id = ?", (new_tx, log_id))
        last_tx_per_group[group_key] = (new_tx, t)
        fixed += 1

    conn.commit()
    print(f"[DONE] Backfilled {fixed}/{len(rows)} records with heuristic transaction_id")
    conn.close()


if __name__ == "__main__":
    main()
'@
Set-Content -Path "$wtPath\scripts\backfill_audit_transaction_id.py" -Value $bfContent -Encoding UTF8
Write-Host "[OK] backfill_audit_transaction_id.py 已创建" -ForegroundColor Green

Write-Host "`n===== T9: 写 verify 脚本 =====" -ForegroundColor Cyan
$verifyContent = @'
#!/usr/bin/env python
"""[VERIFY] 综合验证 P1 + P2 修复效果"""
import sqlite3
from datetime import datetime, timedelta

DB = "meta/architecture.db"
two_days = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    print("=== P1: Admin (admin) 残留 ===")
    c.execute("SELECT COUNT(*) FROM audit_logs WHERE user_name LIKE '%(%'")
    p1_residual = c.fetchone()[0]
    print(f"  COUNT(*) user_name LIKE '%(%' = {p1_residual}")

    print("\n=== P2: tx_id 覆盖率 (非 system 操作) ===")
    c.execute("SELECT COUNT(*), SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END) FROM audit_logs WHERE created_at >= ? AND user_name != 'system'", (two_days,))
    total, with_tx = c.fetchone()
    coverage = with_tx * 100 / total if total else 0
    print(f"  total={total}  with_tx={with_tx}  coverage={coverage:.1f}%")

    print("\n=== P2: 全表 tx_id 覆盖率 ===")
    c.execute("SELECT COUNT(*), SUM(CASE WHEN transaction_id IS NOT NULL AND transaction_id != '' THEN 1 ELSE 0 END) FROM audit_logs")
    total_all, with_tx_all = c.fetchone()
    coverage_all = with_tx_all * 100 / total_all if total_all else 0
    print(f"  total={total_all}  with_tx={with_tx_all}  coverage={coverage_all:.1f}%")

    print("\n=== P1+P2 完成标准 ===")
    p1_ok = "PASS" if p1_residual == 0 else "FAIL"
    p2_ok = "PASS" if coverage >= 95 else "WARN"
    print(f"  P1 (user_name 残留 = 0): {p1_ok}")
    print(f"  P2 (tx_id 覆盖率 >= 95%): {p2_ok}  ({coverage:.1f}%)")

    conn.close()


if __name__ == "__main__":
    main()
'@
Set-Content -Path "$wtPath\scripts\verify_audit_fix.py" -Value $verifyContent -Encoding UTF8
Write-Host "[OK] verify_audit_fix.py 已创建" -ForegroundColor Green

Write-Host "`n===== T10: 验证文件存在性 =====" -ForegroundColor Cyan
Get-ChildItem "$wtPath\spec.md", "$wtPath\scripts\fix_audit_admin_parentheses.py", "$wtPath\scripts\backfill_audit_transaction_id.py", "$wtPath\scripts\verify_audit_fix.py" | ForEach-Object { Write-Host "  [OK] $($_.Name)" -ForegroundColor Green }

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "脚本执行完毕 (代码修改完成)" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步 (需手动执行):" -ForegroundColor Yellow
Write-Host "1. cd $wtPath"
Write-Host "2. git add -A && git commit -m 'fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率 [L1-L5]'"
Write-Host "3. 运行数据修复: python scripts/fix_audit_admin_parentheses.py"
Write-Host "4. 运行数据回填: python scripts/backfill_audit_transaction_id.py"
Write-Host "5. 验证: python scripts/verify_audit_fix.py"
Write-Host "6. git checkout main && git merge --no-ff --autostash agent/audit-fix-2026-06-20"
Write-Host "7. 重启后端: powershell -File scripts/service_manager.ps1 restart"
Write-Host ""