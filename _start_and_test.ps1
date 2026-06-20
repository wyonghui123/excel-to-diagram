# d:\filework\excel-to-diagram\_start_and_test.ps1
cd d:\filework\excel-to-diagram
Remove-Item meta\.architecture.lock -Force -ErrorAction SilentlyContinue
$p = Start-Process python -ArgumentList 'waitress_server.py' `
    -RedirectStandardOutput d:\filework\excel-to-diagram\logs\backend_new.out `
    -RedirectStandardError d:\filework\excel-to-diagram\logs\backend_new.err `
    -PassThru -NoNewWindow
Write-Host "Started PID $($p.Id)"
Start-Sleep -Seconds 18
Write-Host '=== After 18s ==='
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id, StartTime
Write-Host '=== Test ==='
python d:\filework\agent-import-dialog-fixes\_test_v1216.py
Write-Host '=== Result ==='
Get-Content d:\filework\agent-import-dialog-fixes\_test_v1216_result.txt