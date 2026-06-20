---
name: health
description: 前后端健康检查
---

对前后端服务进行健康检查，验证系统是否正常运行。

步骤：
1. 检查后端（port 3010）：
   - `curl.exe -s http://localhost:3010/api/v1/health` 或
   - `Invoke-RestMethod -Uri http://localhost:3010/api/v1/health`
2. 检查前端（port 3004）：
   - `curl.exe -s -o NUL -w "%{http_code}" http://localhost:3004/`
3. 检查 status.json：
   - `Get-Content d:\filework\excel-to-diagram\.service_status.json | ConvertFrom-Json`
4. 检查 watchdog：
   - `Get-Process -Name pythonw -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'watchdog' }`

如果后端不健康：
- 查看错误日志：`Get-Content d:\filework\excel-to-diagram\logs\backend.err -Tail 20`
- 重启：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart`

如果前端不健康：
- 查看错误日志：`Get-Content d:\filework\excel-to-diagram\logs\vite.err -Tail 20`
- 重启前端：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart`

注意：
- 禁止在 PowerShell 中用 `curl`（是 Invoke-WebRequest 别名，会卡死）
- 必须用 `curl.exe` 或 `Invoke-RestMethod`
