# [FIX 2026-06-29] 用 python.exe 替代 pythonw.exe 启动 waitress
# 根因: pythonw.exe (无控制台 Python) 在 Python 3.14 + waitress 下莫名崩溃
#       (无任何错误日志, faulthandler 也不触发, 进程直接消失)
# 验证: 用 python.exe 启动稳定运行, 处理请求后不崩溃

$env:FLASK_ENV = 'development'
$env:FLASK_DEBUG = 'false'
$env:TESTING = 'false'
$env:DEV_MODE = 'true'
$env:PYTHONUNBUFFERED = '1'

Remove-Item 'd:\filework\excel-to-diagram\meta\.architecture.lock' -Force -ErrorAction SilentlyContinue
Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$proc = Start-Process -FilePath 'C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe' `
    -ArgumentList 'd:\filework\excel-to-diagram\waitress_server.py' `
    -WorkingDirectory 'd:\filework\excel-to-diagram' `
    -WindowStyle Hidden `
    -RedirectStandardOutput 'd:\filework\excel-to-diagram\scripts\logs\backend.out' `
    -RedirectStandardError 'd:\filework\excel-to-diagram\scripts\logs\backend.err' `
    -PassThru

Write-Host "Backend started PID=$($proc.Id) (python.exe, stable mode)"
$proc.Id