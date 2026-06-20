# 脚本开发规范

## 技术栈
- PowerShell 5.1 (Windows 默认)
- Python 3.11 (辅助脚本)

## PowerShell 铁律

### 禁止使用的命令
- `curl` → 用 `curl.exe` 或 `Invoke-RestMethod`
- `head` → 用 `Select-Object -First N`
- `tail` → 用 `Select-Object -Last N`
- `cat` → 用 `Get-Content`
- `grep` → 用 `Select-String`

### Git 兼容性
- `stash@{0}` → 必须用变量 `$stashRef = 'stash@{0}'`
- `stash@{0}:path` → 必须用变量 `$refWithPath = 'stash@{0}:path'`
- `head -100` → `Select-Object -First 100`

### 文件编码
- 读取: `Get-Content -Path <file> -Raw -Encoding UTF8`
- 写入: `Set-Content -Path <file> -Value <content> -Encoding UTF8`
- 替换: 优先用 `.Replace()` 而非 `-replace`（避免正则误匹配）

### 路径
- 统一用正斜杠 `/`（PowerShell 两边都支持）
- 避免混用反斜杠 `\`

## 服务管理
- 启停服务: `powershell -File scripts/service_manager.ps1 start/stop/restart/status`
- 禁止直接 `npm run dev` 或 `python dev.py`
- 禁止 `Get-Process python` 判断状态（sandbox 隔离不可靠）
- 禁止 `taskkill /F /IM python.exe` 野蛮杀进程
