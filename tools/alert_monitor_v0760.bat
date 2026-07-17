@echo off
REM alert_monitor_v0760.bat - V007.62 layered monitor wrapper (2026-07-16)
REM V007.86b fix: paths updated to release-prep/
REM
REM Usage:
REM   - Manual: cmd /c "D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.bat"
REM   - Or direct:  pythonw.exe D:\...\alert_monitor_v0760.py --config ... --log-file ... --check-now
REM
REM V007.62 fix:
REM   - Absolute paths, no cd /d "%~dp0" dependency
REM   - pythonw.exe (no-console) instead of python.exe
REM   - --log-file for Python to write log itself

setlocal

set "SCRIPT=D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.py"
set "CONFIG=D:\filework\worktrees\release-prep\tools\alert_monitor_config.json"
set "LOGFILE=D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.log"
set "PYTHONW=C:\Users\Administrator\AppData\Local\Python\bin\pythonw.exe"
set "PYTHON=C:\Users\Administrator\AppData\Local\Python\bin\python.exe"

if exist "%PYTHONW%" (
    "%PYTHONW%" "%SCRIPT%" --config "%CONFIG%" --log-file "%LOGFILE%" --check-now
) else (
    "%PYTHON%" "%SCRIPT%" --config "%CONFIG%" --log-file "%LOGFILE%" --check-now
)

endlocal
exit /b %ERRORLEVEL%
