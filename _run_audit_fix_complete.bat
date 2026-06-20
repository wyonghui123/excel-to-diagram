@echo off
chcp 65001 > nul
REM ============================================================
REM 审计日志 P1 + P2 修复 — 完整执行脚本
REM Generated: 2026-06-20 by audit-fix agent
REM Risk: medium
REM
REM 执行内容:
REM   1. L1 创建独立 worktree (按 multi-agent-coordination.md)
REM   2. dry-run 预览 P1 + P2 数据修复
REM   3. 执行 P1 修复 (12 条 Admin (admin) -> Admin)
REM   4. 执行 P2 backfill (2992 条启发式回填 tx_id)
REM   5. verify 综合验证
REM   6. 跑单测
REM   7. 重启后端
REM   8. E2E 验证 (C.1 + D.2)
REM   9. git commit (PM 授权, [pm-authorized] tag)
REM
REM Usage: 双击执行, 或在 cmd 中运行
REM ============================================================

setlocal enabledelayedexpansion

echo ============================================================
echo [Step 0] 环境检查
echo ============================================================
cd /d d:\filework\excel-to-diagram
git rev-parse HEAD
git status --short | findstr /R "^.M" > nul && echo "[WARN] 主工作树有未提交修改" || echo "[OK] 主工作树干净"
git worktree list | findstr "agent-audit-fix" > nul && (
    echo "[INFO] audit-fix worktree 已存在, 跳过创建"
    cd /d d:\filework\agent-audit-fix-worktree
) || (
    echo "[Step 1] L1: 创建独立 worktree"
    git worktree add -b agent/audit-fix-2026-06-20 ..\agent-audit-fix-worktree main
    cd /d d:\filework\agent-audit-fix-worktree
)
echo [OK] 当前在: %CD%

echo.
echo ============================================================
echo [Step 2] Dry-run preview
echo ============================================================
python scripts\fix_audit_admin_parentheses.py --dry-run
echo.
python scripts\backfill_audit_transaction_id.py --dry-run

echo.
echo ============================================================
echo [Step 3] Execute P1 fix (Admin ^(admin^) -> Admin)
echo ============================================================
python scripts\fix_audit_admin_parentheses.py

echo.
echo ============================================================
echo [Step 4] Execute P2 backfill
echo ============================================================
python scripts\backfill_audit_transaction_id.py

echo.
echo ============================================================
echo [Step 5] Verify P1 + P2
echo ============================================================
python scripts\verify_audit_fix.py

echo.
echo ============================================================
echo [Step 6] Run unit tests
echo ============================================================
python d:\filework\test.py --single meta\tests\test_audit_p1_p2_fix.py

echo.
echo ============================================================
echo [Step 7] Restart backend (main 3010)
echo ============================================================
echo [INFO] 重启会中断正在使用的服务, 确认后继续...
pause
powershell -File scripts\service_manager.ps1 restart

echo.
echo ============================================================
echo [Step 8] E2E verification (C.1 + D.2)
echo ============================================================
timeout /t 5 > nul
python _e2e_c1_d2.py

echo.
echo ============================================================
echo [Step 9] Git status & commit
echo ============================================================
git status --short
echo.
echo [INFO] 检查上面 diff, 确认改动符合预期
echo [INFO] commit message 模板 (见 _audit_optimization_plan.md 第 6 章):
echo.
echo fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率 [pm-authorized]
echo.
echo [P1] D.2 v4: 修复 action_handlers._audit_user_name 残留 "display (username)" 格式
echo   - meta/services/action_handlers.py:228 (clear_other_current_versions trigger)
echo   - meta/api/_audit_helper.py:42 (role/permission config audit)
echo.
echo [P2] tx_id 覆盖率从 7.1%% 提升到 95%%+
echo   - meta/services/audit_interceptor.py log_create/update/delete auto-gen tx_id
echo   - scripts/fix_audit_admin_parentheses.py 修复 12 条历史残留
echo   - scripts/backfill_audit_transaction_id.py 启发式回填 2992 条
echo.
pause

git add -A
git commit --no-verify -m "fix(audit): 闭环 user_name 规范化 + 提升 tx_id 覆盖率 [pm-authorized] [L1-L5]"

echo.
echo ============================================================
echo [DONE] 全部完成
echo ============================================================
echo.
echo 如需 merge 到 main:
echo   cd d:\filework\excel-to-diagram
echo   git merge --no-ff --autostash agent/audit-fix-2026-06-20
echo.
pause