@echo off
REM alert_monitor.bat - Windows 任务计划包装 (V007.58 2026-07-15)
REM 用法:
REM   1. 配置: tools/alert_monitor_config.json (有 webhook)
REM   2. 手动测试: alert_monitor.bat --test-im
REM   3. 跑一次: alert_monitor.bat --check-now
REM   4. Windows 任务计划: 每 5 分钟
REM      - 程序: d:\filework\release-prep-worktree\tools\alert_monitor.bat
REM      - 参数: (空)
REM      - 起始: d:\filework\release-prep-worktree\tools

cd /d "%~dp0"
setlocal

REM 用 python.exe (避免 py launcher 找不到)
set PYTHON=python

REM 默认跑一次 (Windows 任务计划这样调)
%PYTHON% alert_monitor.py --check-now >> alert_monitor.log 2>&1

REM 退出码
exit /b %ERRORLEVEL%