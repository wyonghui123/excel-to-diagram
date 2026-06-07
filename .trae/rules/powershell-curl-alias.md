# PowerShell curl 问题规则

## 问题描述

PowerShell 的 `curl` 是 `Invoke-WebRequest` 的别名，不是真正的 curl 工具。

执行 `curl -s "http://..."` 在 PowerShell 中会变成 `Invoke-WebRequest -s`，**卡死在交互式等待 URI 输入**，永久占用终端槽位（总共只有 5 个）。

## 正确做法

```powershell
# [X] 绝对禁止 — 会卡死在交互式等待
curl -s http://localhost:3010/api/v1/...
curl http://localhost:3010/api/v1/...

# [OK] 四种正确方式任选其一

# 方式1：curl.exe（Windows 10+ 自带真实的 curl 8.x 二进制）
curl.exe -s http://localhost:3010/api/v1/auth/dev-login?username=admin

# 方式2：Python 单行（最可靠，跨平台一致）
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:3010/api/v1/auth/dev-login?username=admin').read().decode())"

# 方式3：Invoke-RestMethod（PowerShell 原生 REST 客户端）
Invoke-RestMethod -Uri "http://localhost:3010/api/v1/auth/dev-login?username=admin"

# 方式4：Invoke-WebRequest（给完整 URI，不省略）
(Invoke-WebRequest -Uri "http://localhost:3010/api/v1/auth/dev-login?username=admin").Content
```

## 诊断命令

```powershell
Get-Command curl
# 如果是 Alias -> Invoke-WebRequest，说明会被拦截
# 如果是 Application -> curl.exe，说明直接调用了真实 curl

# 验证 curl.exe 存在
Get-Command curl.exe
```

## Agent 必须遵守的规则

1. **禁止**在 PowerShell 中使用 `curl` 命令（会匹配 Invoke-WebRequest 别名）
2. **推荐**使用 `curl.exe`（注意 .exe 后缀）或 Python 
3. 若不确定命令是否会卡死，先用 Python 方式
