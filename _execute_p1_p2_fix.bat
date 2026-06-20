@echo off
REM ============================================================
REM 审计日志 P1 + P2 修复执行脚本
REM Generated: 2026-06-20 by audit-fix agent
REM Risk: medium (服务逻辑改动, 已通过 Edit 工具完成代码修改)
REM
REM 执行内容:
REM   1. dry-run 预览 P1 + P2 数据修复
REM   2. 执行 P1 修复 (12 条 Admin (admin) → Admin)
REM   3. 执行 P2 backfill (2992 条启发式回填 tx_id)
REM   4. verify 综合验证
REM   5. 重启后端 (用户决策)
REM
REM Usage: 双击执行, 或在 cmd 中运行
REM ============================================================

setlocal enabledelayedexpansion

echo ============================================================
echo [Step 1] Dry-run preview
echo ============================================================
cd /d d:\filework\excel-to-diagram
python scripts\fix_audit_admin_parentheses.py --dry-run
echo.
python scripts\backfill_audit_transaction_id.py --dry-run
echo.

echo ============================================================
echo [Step 2] Execute P1 fix (Admin ^(admin^) -> Admin)
echo ============================================================
python scripts\fix_audit_admin_parentheses.py
echo.

echo ============================================================
echo [Step 3] Execute P2 backfill (heuristic transaction_id)
echo ============================================================
python scripts\backfill_audit_transaction_id.py
echo.

echo ============================================================
echo [Step 4] Verify P1 + P2
echo ============================================================
python scripts\verify_audit_fix.py
echo.

echo ============================================================
echo [Step 5] Run unit tests
echo ============================================================
python d:\filework\test.py --single meta\tests\test_audit_p1_p2_fix.py
echo.

echo ============================================================
echo [DONE] All scripts executed
echo ============================================================
echo.
echo Next steps (需用户决定):
echo   1. review verify 输出, 确认 PASS
echo   2. 重启后端: powershell -File scripts\service_manager.ps1 restart
echo   3. E2E 验证: python _e2e_c1_d2.py
echo   4. git add + commit (commit message 见 _audit_optimization_plan.md)
echo.
pause