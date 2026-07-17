@echo off
REM testrunshortcut - force-best-practice

if "%1"=="" goto smart
if "%1"=="--all" goto all
if "%1"=="--failed" goto failed
if "%1"=="--status" goto status
if "%1"=="--watch" goto watch
goto usage

:smart
echo smartrun-tests...
python d:\filework\test.py
goto end

:all
echo fullrun-tests...
python d:\filework\test.py --all
goto end

:failed
echo rerunfailtest...
python d:\filework\test.py --failed
goto end

:status
python d:\filework\test.py --status
goto end

:watch
python d:\filework\test.py --watch
goto end

:usage
echo.
echo testrunshortcut
echo.
echo usage: test.bat [option]
echo.
echo option:
echo   (no-arg)    smartrun(based-onstatusdecide)
echo   --all       fullrun
echo   --failed    onlyrunfailtest
echo   --status    viewstatus
echo   --watch     continuousmonitor
echo.

:end
