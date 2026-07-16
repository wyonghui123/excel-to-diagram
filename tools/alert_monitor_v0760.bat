@echo off
REM alert_monitor_v0760.bat - V007.62 分层监控 wrapper (2026-07-16)
REM
REM 注意: Task Scheduler 任务已直接调 pythonw.exe (no console, 无弹窗)
REM       本文件保留用于手动调试 (会闪一下 cmd 窗口, 但不报错)
REM
REM 用法:
REM   - 手动跑:    cmd /c "D:\filework\release-prep-worktree\tools\alert_monitor_v0760.bat"
REM   - 或直接调:  pythonw.exe D:\...\alert_monitor_v0760.py --config ... --log-file ... --check-now
REM
REM V007.62 修:
REM   - 用绝对路径, 不再依赖 cd /d "%~dp0" (在 Task Scheduler 上下文里偶尔会失败)
REM   - 用 pythonw.exe (no-console) 替代 python.exe, 避免弹窗
REM   - --log-file 让 Python 自己写日志, 不依赖 shell 重定向

setlocal

REM 绝对路径 (避免 Task Scheduler 上下文里 cd 失败)
set "SCRIPT=D:\filework\release-prep-worktree\tools\alert_monitor_v0760.py"
set "CONFIG=D:\filework\release-prep-worktree\tools\alert_monitor_config.json"
set "LOGFILE=D:\filework\release-prep-worktree\tools\alert_monitor_v0760.log"
set "PYTHONW=C:\Users\Administrator\AppData\Local\Python\bin\pythonw.exe"
set "PYTHON=C:\Users\Administrator\AppData\Local\Python\bin\python.exe"

REM 优先 pythonw.exe (无窗口), fallback python.exe (有窗口但能看到输出)
if exist "%PYTHONW%" (
    "%PYTHONW%" "%SCRIPT%" --config "%CONFIG%" --log-file "%LOGFILE%" --check-now
) else (
    "%PYTHON%" "%SCRIPT%" --config "%CONFIG%" --log-file "%LOGFILE%" --check-now
)

endlocal
exit /b %ERRORLEVEL%
