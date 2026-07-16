# [FIX 2026-06-29] 用 python.exe 替代 pythonw.exe 启动 waitress
# 根因: pythonw.exe (无控制台 Python) 在 Python 3.14 + waitress 下莫名崩溃
#       (无任何错误日志, faulthandler 也不触发, 进程直接消失)
# 验证: 用 python.exe 启动稳定运行, 处理请求后不崩溃
#
# 配置与 service_manager.ps1 (4df4293) 一致:
#   - FLASK_ENV=production (Q2 决策: 回滚 dev 配置)
#   - FLASK_DEBUG=false
#   - 不设 DEV_MODE (生产不应启用 YAML 热加载)
#   - 如需 dev_login, 临时覆盖: $env:FLASK_ENV='development'; $env:DEV_MODE='true'
#
# 这是 start_backend.ps1 的稳定版本 (python.exe 替代 pythonw.exe)
# 配合 scripts/restart_backend.py + scripts/watchdog_v30.ps1 (5862f9e + 5e87523)

$env:FLASK_ENV = 'production'
$env:FLASK_DEBUG = 'false'
$env:TESTING = 'false'
$env:PYTHONUNBUFFERED = '1'

Remove-Item 'd:\filework\excel-to-diagram\meta\.architecture.lock' -Force -ErrorAction SilentlyContinue
Stop-Process -Name pythonw -Force -ErrorAction SilentlyContinue
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# [FIX 2026-06-29] 默认用 py -3 (Windows Python Launcher), 也可覆盖: $env:PYTHON_EXE = '...'
if (-not $env:PYTHON_EXE) {
    $env:PYTHON_EXE = 'py'
}

$proc = Start-Process -FilePath $env:PYTHON_EXE `
    -ArgumentList '-3', 'd:\filework\excel-to-diagram\waitress_server.py' `
    -WorkingDirectory 'd:\filework\excel-to-diagram' `
    -WindowStyle Hidden `
    -RedirectStandardOutput 'd:\filework\excel-to-diagram\scripts\logs\backend.out' `
    -RedirectStandardError 'd:\filework\excel-to-diagram\scripts\logs\backend.err' `
    -PassThru

Write-Host "Backend started PID=$($proc.Id) (python.exe, stable mode, FLASK_ENV=production)"
$proc.Id
