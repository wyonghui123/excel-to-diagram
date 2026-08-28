# 启动后端到3010
$env:PORT = '3010'
Set-Location 'd:\filework\excel-to-diagram'
Start-Process pythonw -ArgumentList 'meta/server.py' -RedirectStandardOutput 'd:\filework\excel-to-diagram\logs\backend.log' -RedirectStandardError 'd:\filework\excel-to-diagram\logs\backend-err.log' -PassThru -WindowStyle Hidden