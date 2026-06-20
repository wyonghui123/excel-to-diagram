@echo off
cd /d d:\filework\excel-to-diagram
del /f meta\.architecture.lock 2>nul
echo Starting backend...
start /b python waitress_server.py > d:\filework\excel-to-diagram\logs\backend_new.out 2>&1
echo Started, waiting 12s...
timeout /t 12 /nobreak >nul
echo Running test...
python d:\filework\agent-import-dialog-fixes\_test_v1216.py
echo Done.
type d:\filework\agent-import-dialog-fixes\_test_v1216_result.txt
echo.
echo Backend log tail:
powershell -Command "Get-Content d:\filework\excel-to-diagram\logs\backend_new.out -Tail 30"