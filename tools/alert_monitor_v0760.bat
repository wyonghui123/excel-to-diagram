@echo off
REM alert_monitor_v0760.bat - V007.62 layered monitor wrapper
REM V007.86e fix: hide cmd window (use create_no_window via PowerShell Start-Process -WindowStyle Hidden)
REM
REM V007.62 change history:
REM   - Absolute paths, no cd /d "%~dp0" dependency
REM   - pythonw.exe (no-console) instead of python.exe
REM   - --log-file for Python to write log itself
REM
REM V007.86c change:
REM   - ASCII only (no Chinese in comments, avoid GBK decode failure)
REM
REM V007.86e change:
REM   - Wrap in PowerShell Start-Process -WindowStyle Hidden (NO cmd window popup)
REM   - Was: bare pythonw.exe invocation -> cmd window flashes briefly
REM   - Fix: use PowerShell to spawn pythonw.exe in hidden window
REM
REM This .bat itself runs with no cmd window because:
REM   1. PowerShell -WindowStyle Hidden is set
REM   2. pythonw.exe is the actual Python runtime (no console)
REM
REM Usage:
REM   - Manual:    no need to use this .bat (use --check-now directly)
REM   - Scheduled: schtasks /Create /XML <generated XML> /F

setlocal

set "SCRIPT=D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.py"
set "CONFIG=D:\filework\worktrees\release-prep\tools\alert_monitor_config.json"
set "LOGFILE=D:\filework\worktrees\release-prep\tools\alert_monitor_v0760.log"
set "PYTHONW=C:\Users\Administrator\AppData\Local\Python\bin\pythonw.exe"
set "PYTHON=C:\Users\Administrator\AppData\Local\Python\bin\python.exe"

if exist "%PYTHONW%" (
    set "PY_EXE=%PYTHONW%"
) else (
    set "PY_EXE=%PYTHON%"
)

REM V007.86e fix: spawn via PowerShell with -WindowStyle Hidden
REM This prevents ANY cmd window from appearing during scheduled task runs.
REM Without this, the .bat file itself pops a cmd window briefly.
powershell -NoProfile -Command "Start-Process -FilePath '%PY_EXE%' -ArgumentList @('%SCRIPT%', '--config', '%CONFIG%', '--log-file', '%LOGFILE%', '--check-now') -WindowStyle Hidden -Wait"

endlocal
exit /b %ERRORLEVEL%
