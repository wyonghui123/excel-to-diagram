@echo off
REM alert_monitor.bat - Windows Task Scheduler wrapper (V007.59 2026-07-16)
REM Run alert_monitor.py --check-now with absolute paths (avoid Task Scheduler PATH issues)

cd /d "%~dp0"

REM Absolute Python path (avoid relying on PATH in Task Scheduler context)
where python >nul 2>nul && (
    "python" "%~dp0alert_monitor.py" --check-now >> "%~dp0alert_monitor.log" 2>&1
) || (
    REM fallback to py launcher
    py "%~dp0alert_monitor.py" --check-now >> "%~dp0alert_monitor.log" 2>&1
)

exit /b %ERRORLEVEL%
