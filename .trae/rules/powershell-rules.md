# PowerShell 语法规范

> **PowerShell 是 Windows 默认 shell，语法与 bash/shell 不同。必须使用 PowerShell 原生命令。**

## Bash → PowerShell 速查表

| Bash 语法 | PowerShell 等价 | 说明 |
|-----------|---------------|------|
| `cmd1 && cmd2` | `cmd1; if ($LASTEXITCODE -eq 0) { cmd2 }` | AND 逻辑 |
| `cmd1 \|\| cmd2` | `cmd1; if ($LASTEXITCODE -ne 0) { cmd2 }` | OR 逻辑 |
| `cmd1; cmd2` | `cmd1; cmd2` | 分号分隔（两者一致） |
| `cmd > file 2>&1` | `cmd *> file` | 重定向 |
| `cmd \| head -n 10` | `cmd \| Select-Object -First 10` | 获取前 N 行 |
| `cmd \| tail -n 10` | `cmd \| Select-Object -Last 10` | 获取后 N 行 |
| `cmd \| grep "..."` | `cmd \| Where-Object { $_ -like "..." }` | 文本过滤 |
| `cat file` | `Get-Content file` | 读取文件 |
| `head -c 200` | 无等价命令 | 用 `Get-Content -TotalCount` |
| `$(cmd)` | `$(cmd)` | 命令替换（两者一致） |
| `$?` | `$LASTEXITCODE` | 上一条命令退出码 |
| `echo "text"` | `Write-Host "text"` | 输出文本 |
| `node -e "..."` | `node -e "..."` | Node.js 一致，但引号处理不同 |
| `'text'` | `'text'` | 单引号不展开变量（两者一致） |
| `"text"` | `"text"` | 双引号展开变量（两者一致） |

## 常见错误示例

```powershell
# [X] 错误：PowerShell 中 || 是管道操作符，不是 OR 逻辑
npm run build || echo "failed"

# [OK] 正确：使用 if 语句检查退出码
npm run build
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed" }

# [X] 错误：head 不是 PowerShell 命令
Get-Content log.txt | head -n 10

# [OK] 正确：使用 Select-Object
Get-Content log.txt | Select-Object -First 10

# [X] 错误：grep 不是 Windows 原生命令
Get-Process | grep "node"

# [OK] 正确：使用 Where-Object
Get-Process | Where-Object { $_.ProcessName -like "*node*" }

# [X] 错误：curl 可能被 PowerShell 别名覆盖
curl http://localhost:3000

# [OK] 正确：使用 curl.exe 或 Invoke-WebRequest
curl.exe http://localhost:3000
```

## Node.js -e 参数处理

```powershell
# [X] 错误：PowerShell 中引号转义复杂
node -e "console.log(require('./a.js').foo('bar'))"

# [OK] 正确：写一个临时 .js 文件
# test_foo.js
# const { foo } = require('./a.js');
# console.log(foo('bar'));

# [OK] 正确：在 PowerShell 中使用单引号包裹
node -e 'console.log("hello")'
```

## 重定向操作符

```powershell
# [X] 错误：2>&1 1>file 在 PowerShell 中行为不确定
cmd 2>&1 1>d:\filework\e2e_run.log

# [OK] 正确：使用 *> 重定向所有输出
cmd *> d:\filework\e2e_run.log

# [OK] 正确：分别重定向 stdout 和 stderr
cmd 1>d:\filework\e2e_out.log 2>d:\filework\e2e_err.log

# [OK] 正确：追加模式
cmd >> output.txt 2>&1

# [OK] 正确：丢弃所有输出
cmd *> $null

# [OK] 正确：PowerShell 中 2>&1 仍可用
cmd 2>&1 | Out-String
```

## 路径分隔符

```powershell
# [X] 错误：混用反斜杠和正斜杠
cd d:\filework\excel-to-diagram
python tests\e2e\e2e_relation_scope_tree.py

# [OK] 正确：统一使用正斜杠
cd d:/filework/excel-to-diagram
python tests/e2e/e2e_relation_scope_tree.py

# [OK] 正确：PowerShell 兼容正斜杠
cd "d:\filework\excel-to-diagram"
python "d:/filework/excel-to-diagram/tests/e2e/e2e_relation_scope_tree.py"
```

## 运行测试脚本的正确方式

```powershell
# [X] 错误：直接运行测试脚本
cd d:\filework\excel-to-diagram
python tests/e2e/e2e_relation_scope_tree.py

# [OK] 正确：通过 test.py 入口运行
python d:\filework\test.py --file tests/e2e/e2e_relation_scope_tree.py

# [OK] 正确：查看测试状态
python d:\filework\test.py --status

# [OK] 正确：运行失败的测试
python d:\filework\test.py --failed
```

## 铁律：禁止使用 curl

> **在 PowerShell 中，`curl` 是 `Invoke-WebRequest` 的别名，不是真正的 curl！**
>
> `curl -s http://...` 会变成 `Invoke-WebRequest -s http://...`，**卡死在交互式等待**，永久占用终端。

**正确做法：**
```powershell
# [X] 绝对禁止 — 会卡死在交互式等待
curl -s http://localhost:3010/api/v1/...
curl http://localhost:3010/api/v1/...

# [OK] 三种正确方式任选其一
curl.exe -s http://localhost:3010/api/v1/...                           # 方式1：用 curl.exe（真实二进制）
python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:3010/api/v1/...').read().decode())"  # 方式2：Python
Invoke-RestMethod -Uri http://localhost:3010/api/v1/...                # 方式3：PowerShell 原生
```

## 中文输出乱码问题（必须解决）

> **PowerShell 5 默认使用 GBK 编码，遇到 UTF-8 输出时中文会显示为乱码。**

### 乱码示例

```
实际内容:  业务对象导出与导入验证
终端显示:  涓氬姟瀵硅薄瀵煎嚮涓庡鍏ラ獙璇?
```

### 解决方案（必须按顺序设置）

#### 1. 切换 PowerShell 代码页为 UTF-8

```powershell
# [X] 错误：PowerShell 5 默认代码页 936（GBK）
# 输出 UTF-8 字符会乱码

# [OK] 正确：切换到 UTF-8（代码页 65001）
chcp 65001 | Out-Null
```

#### 2. 设置 Python IO 编码

```powershell
# [OK] 正确：Python 强制 UTF-8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

# 或在命令中
python -X utf8 script.py
```

#### 3. 设置 Node.js 输出编码

```powershell
# [OK] 正确：Node.js 强制 UTF-8
$env:NODE_OPTIONS = "--max-old-space-size=4096"
$env:LC_ALL = "C.UTF-8"

# 或在命令中
node -e "process.stdout.setEncoding('utf-8'); ..."
```

#### 4. Tee-Object 编码

```powershell
# [X] 错误：Tee-Object 用系统默认编码（GBK）
npx playwright test | Tee-Object log.txt   # 中文会乱码

# [OK] 正确：用 Out-File 显式指定 UTF-8
npx playwright test | Out-File -FilePath log.txt -Encoding utf8

# [OK] 正确：写入时用 utf8NoBOM
npx playwright test | Out-File -FilePath log.txt -Encoding utf8NoBOM
```

### 完整的多步骤 UTF-8 模板

```powershell
# [OK] 完美：完整的 UTF-8 输出命令
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:LC_ALL = "C.UTF-8"
$env:PYTHONUTF8 = "1"

# Playwright 测试（用 Out-File 而非 Tee-Object）
npx playwright test e2e/features/ --reporter=line `
    2>&1 `
    | Out-File -FilePath d:\filework\e2e_run.log -Encoding utf8
```

### 用 PowerShell 7 替代 PowerShell 5

```powershell
# [OK] 推荐：PowerShell 7 默认 UTF-8
# 下载：https://aka.ms/powershell-release
pwsh

# 在 pwsh 中：
# 1. 默认 $OutputEncoding = [System.Text.Encoding]::UTF8
# 2. chcp 命令可选
# 3. 中文输出正常
```

### 查看当前编码

```powershell
# 查看 PowerShell 进程编码
$OutputEncoding.EncodingName

# 查看控制台代码页
chcp

# 查看文件编码
Get-Content -Path file.txt -Encoding Byte | Select-Object -First 4
```

### 转换已有日志文件编码

```powershell
# GBK → UTF-8
Get-Content d:\filework\e2e_run.log -Encoding GBK `
    | Out-File d:\filework\e2e_run_utf8.log -Encoding utf8

# UTF-8 → GBK（如果需要兼容老系统）
Get-Content d:\filework\e2e_run.log -Encoding UTF8 `
    | Out-File d:\filework\e2e_run_gbk.log -Encoding GBK
```

## PowerShell 5 + 中文 = 灾难（必须知道）

> **PowerShell 5 解析器对中文字符串中的 `[XXX]` 标记有严重解析问题，会把整个块当语法错误。**

### 问题示例

```powershell
# [X] 错误：PowerShell 5 解析错误
$verdict = "[OK] 资源充足"   # 报错：Unexpected token 'OK] 资源充足'
$verdict = '[' + 'OK' + '] 资源充足'   # 仍报错
$verdict = "【OK】资源充足"   # 中文书名号可以，但 ASCII [] 不行
```

### 根本原因

PowerShell 5 解析器在解析字符串时遇到 `[...]` 会试图解释为：
1. **类型访问**：`[OK]` 试图查找 `OK` 类型
2. **数组索引**：`$array[0]` 这种语法

当中文出现在 `[...]` 后面时，解析器会失败并报语法错误。

### 解决方案

#### 方案 1：用中文圆括号（推荐）

```powershell
# [OK] 正确：用中文【】
$verdict = "【OK】资源充足"
$verdict = "【BLOCKED】资源紧张"
$verdict = "【WARN】资源一般"
```

#### 方案 2：用 ascii 字符替代

```powershell
# [OK] 正确：用纯英文
$verdict = "[OK] resources sufficient"
$verdict = "[BLOCKED] resources tight"
$verdict = "[WARN] resources normal"
```

#### 方案 3：用 format-string

```powershell
# [OK] 正确：用 -f 格式化
$verdict = "[{0}] {1}" -f "OK", "资源充足"
```

### 完整测试案例

```powershell
# [X] 错误：失败
$verdict = "[OK] 资源充足"
Write-Host "  $verdict"

# [OK] 正确 1：用中文【】
$verdict = "【OK】资源充足"
Write-Host "  $verdict"

# [OK] 正确 2：用纯英文
$verdict = "[OK] resources sufficient"
Write-Host "  $verdict"

# [OK] 正确 3：用 format-string
$verdict = "[{0}] {1}" -f "OK", "资源充足"
Write-Host "  $verdict"
```

### 根本解决方案：升级 PowerShell 7

```powershell
# [OK] 推荐：升级到 PowerShell 7
# 下载：https://aka.ms/powershell-release
# PowerShell 7 默认 UTF-8 + 改进的字符串解析器
pwsh
```

### 写 PS1 文件的最佳实践

1. **避免中文 + ASCII 方括号混用**
2. **优先用中文圆括号 `【】` 包裹标记**
3. **如果要写中文，文件保存为 UTF-8（不要 GBK）**
4. **运行前先 `chcp 65001`**
5. **考虑升级到 PowerShell 7**

## PowerShell 5 中文乱码终极解决方案

> **真正的根本原因：PowerShell 5 默认控制台编码是系统编码（GBK），与子进程（Node/Python）的 UTF-8 输出冲突。**

### 100% 解决乱码的 5 行命令

```powershell
# [X] 错误：以下任何方式都会乱码
node -e "console.log('中文')" | Out-String           # Out-String 用系统编码解码
node -e "console.log('中文')" *> file.log             # *> 写 UTF-16 LE
node -e "console.log('中文')" > file.log              # > 写 UTF-16 LE
node -e "console.log('中文')" | Out-File -Encoding utf8 file.log  # 仍可能乱码！

# [OK] 正确：完整 5 行配置
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:LC_ALL = "C.UTF-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8   # 关键！第 5 行

# 然后运行命令
node -e "console.log('中文')" | Out-File -Encoding utf8 file.log
```

### 5 个关键设置详解

| 行 | 设置 | 作用 | 为什么需要 |
|---|------|------|----------|
| 1 | `chcp 65001` | 切换 Windows 控制台代码页为 UTF-8 | 控制台窗口正确显示 |
| 2 | `$env:PYTHONIOENCODING` | Python stdout/stderr 用 UTF-8 | Python 输出不乱码 |
| 3 | `$env:PYTHONUTF8` | Python UTF-8 模式 | 强制 Python UTF-8 |
| 4 | `$env:LC_ALL` | C 库 locale | Node.js 调用的 C 库 |
| 5 | **`[Console]::OutputEncoding`** | **PowerShell 控制台输出编码** | **关键！让管道接收 UTF-8** |

### 各命令输出方式对比

| 命令 | 编码 | 正确性 |
|------|------|-------|
| `node ...`（无管道） | 取决于控制台 | 设置 #5 后正确 |
| `node ... | Out-String` | 系统编码（GBK） | [X] 乱码 |
| `node ... *> file` | **UTF-16 LE** | [X] 乱码 |
| `node ... > file` | **UTF-16 LE** | [X] 乱码 |
| `node ... | Out-File -Encoding utf8 file` | UTF-8（设置 #5 后） | [OK] 正确 |
| `node ... | Set-Content -Encoding UTF8 file` | UTF-8（设置 #5 后） | [OK] 正确 |
| `node ... | Tee-Object -FilePath file` | 系统编码 | [X] 乱码 |

### 真实测试结果

```powershell
# [X] 错误 1：Out-String
PS> node -e "console.log('[截图验证] OK')" | Out-String
[鎴浘楠岃瘉] OK              # 乱码！

# [X] 错误 2：*>
PS> node -e "console.log('[截图验证] OK')" *> test.log
PS> Get-Content test.log -Encoding Byte -TotalCount 5
255 254 91 0 180                # UTF-16 LE BOM！内容是乱码
PS> Get-Content test.log
[鎴浘楠岃瘉] OK              # 乱码！

# [X] 错误 3：Out-File -Encoding utf8（无 Console 设置）
PS> node -e "console.log('[截图验证] OK')" | Out-File test.log -Encoding utf8
PS> Get-Content test.log
[鎴浘楠岃瘉] OK              # 仍乱码！

# [OK] 正确：5 行配置 + Out-File -Encoding utf8
PS> [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
PS> node -e "console.log('[截图验证] OK')" | Out-File test.log -Encoding utf8
PS> Get-Content test.log
[截图验证] OK                  # 正确！
```

### Playwright E2E 测试的正确命令

```powershell
# [X] 错误：直接 npx + Out-String（用户的命令）
npx playwright test e2e/features/ --reporter=line 2>&1 | Out-String
# → 乱码：[鎴浘楠岃瘉] [OK] 鐢ㄦ埛缁?tab 鍒囨崲鎴愬姛

# [OK] 正确 1：5 行配置 + 直接输出（推荐）
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:LC_ALL = "C.UTF-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
npx playwright test e2e/features/ --reporter=line 2>&1
# → 正确：[截图验证] [OK] 用户组 tab 切换成功

# [OK] 正确 2：5 行配置 + Out-File 保存
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:LC_ALL = "C.UTF-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
npx playwright test e2e/features/ --reporter=line 2>&1 `
    | Out-File -FilePath d:\filework\e2e_run.log -Encoding utf8
# → 日志文件 UTF-8 编码，可读

# [OK] 正确 3：5 行配置 + Set-Content
chcp 65001 | Out-Null
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:LC_ALL = "C.UTF-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
npx playwright test e2e/features/ --reporter=line 2>&1 `
    | Set-Content -Path d:\filework\e2e_run.log -Encoding UTF8
```

### 一键配置函数（放到 profile.ps1）

```powershell
# 添加到 $PROFILE
function Set-Utf8Environment {
    chcp 65001 | Out-Null
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"
    $env:LC_ALL = "C.UTF-8"
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Host "[OK] UTF-8 environment configured" -ForegroundColor Green
}

# 使用
Set-Utf8Environment
```

### PowerShell 7 终极方案（推荐）

```powershell
# [OK] 根本解决：升级到 PowerShell 7
# 下载：https://aka.ms/powershell-release
# 默认 UTF-8，无需任何配置

# 验证
pwsh
$OutputEncoding.EncodingName
# → Unicode (UTF-8)

# 任意命令直接用
npx playwright test e2e/features/ --reporter=line 2>&1
# → 终端显示正确，日志也正确
```

### 验证方法

```powershell
# 验证编码设置
[Console]::OutputEncoding.EncodingName        # 应为 Unicode (UTF-8)
$OutputEncoding.EncodingName                   # 应为 Unicode (UTF-8)
chcp                                           # 应为 65001
$env:PYTHONIOENCODING                          # 应为 utf-8

# 验证管道
node -e "console.log('[截图验证] OK')" | Out-File test.log -Encoding utf8
Get-Content test.log
# 应输出：[截图验证] OK
```
