@echo off
REM ============================================================
REM Push to origin (网络恢复后手动执行)
REM ============================================================
REM 用途: 同步本地 17 commits 到 GitHub origin
REM 当 AI 工具网络受限时, 使用此脚本手动执行
REM ============================================================

cd /d D:\filework\excel-to-diagram

echo ==========================================
echo  Push to origin: release/integrated-main
echo  Local HEAD ahead of origin: 17 commits
echo ==========================================
echo.

REM 显示待 push 的 commits
git log --oneline origin/release/integrated-main..HEAD

echo.
echo ==========================================
echo  Start push...
echo ==========================================
echo.

REM 实际 push
git push origin release/integrated-main

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ==========================================
    echo  [ FAILED ] Push failed, check network
    echo  Try: ping github.com
    echo  Try: git remote -v
    echo ==========================================
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  [ DONE ] Push succeeded
echo ==========================================
pause