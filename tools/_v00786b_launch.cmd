@echo off
:: V007.86b launcher - 用 explorer.exe 触发 UAC 弹窗
:: 用户需要: 看到 UAC 弹窗 -> 点 "是" -> 自动跑 V007.86b_PERMANENT_FIX.ps1
echo === V007.86b Permanent Fix ===
echo.
echo Will request UAC elevation to fix yonaa_alert_monitor scheduled task.
echo When UAC prompt appears, click "Yes".
echo.
pause
start "" "powershell.exe" "-NoProfile" "-ExecutionPolicy" "Bypass" "-File" "D:\filework\worktrees\release-prep\tools\_v00786b_permanent_fix.ps1"
