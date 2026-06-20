# PowerShell 语法规范 (v3.18)

> **PowerShell 是 Windows 主力 shell，但有大量坑需要规避。本规则让 AI Coding Agent 避免常见陷阱。**

## 核心问题：MojiBake 乱码陷阱

### 问题现象

PowerShell 操作文件时，中文/特殊字符变成 `�?`、`锟斤拷`、乱码，代码注释被意外破坏：

```
# [X] 错误示例
// 清除 directNodes �?containers，避免后续生成子�?
const centerMark = allNodesCenter ? '�?' : ''
```

### 根本原因

| 原因类型 | 说明 | 案例 |
|---------|------|------|
| **编码不一致** | 文件 UTF-8，控制台 GBK | 中文变 `�` |
| **-replace 正则误匹配** | `-replace` 默认正则，`<>` 有特殊含义 | 注释被破坏 |
| **混合编码读取** | 部分读取时编码转换 | `◆` 变 `�?` |

## [!!!] 铁律：禁止直接 -replace 字符串替换 [!!!]

> **`-replace` 使用正则表达式，容易误匹配注释中的内容！**

### 错误做法（会破坏代码）

```powershell
# [X] 绝对禁止 - 正则可能误匹配注释
$content -replace '<br/>', '·'
$content -replace 'BR', 'XX'
$content -replace '<.*?>', ''  # 匹配所有 HTML 标签，包括注释中的

# [X] 绝对禁止 - 不指定编码读取
Get-Content file.js
Get-Content file.js -Raw

# [X] 绝对禁止 - 编码不匹配
Get-Content file.js | ForEach-Object { ... }
```

### 正确做法

```powershell
# [OK] 使用 -SimpleMatch 进行字面量替换
$content -replace '<br/>', '·'  # 如果确认是正则意图才用

# [OK] 读取文件时指定 UTF-8 编码
$content = Get-Content -Path file.js -Raw -Encoding UTF8

# [OK] 写入文件时指定 UTF-8 编码
Set-Content -Path file.js -Value $content -Encoding UTF8

# [OK] 批量替换前先备份
Copy-Item file.js file.js.bak
$content = Get-Content -Path file.js -Raw -Encoding UTF8
$newContent = $content -replace '<br/>', '·'
Set-Content -Path file.js -Value $newContent -Encoding UTF8
```

## 正则表达式 vs 字面量替换

### PowerShell -replace 行为

| 语法 | 行为 | 危险程度 |
|------|------|---------|
| `$str -replace 'pattern', 'repl'` | **正则表达式** | 高危 |
| `$str -ireplace 'pattern', 'repl'` | 正则（不区分大小写） | 高危 |
| `$str -replace 'literal', 'repl'` | 字面量（需确认 pattern 无正则元字符） | 中 |
| `[regex]::Replace($str, 'pattern', 'repl')` | 正则（显式） | 高危 |

### 危险元字符

```
. ^ $ * + ? { } [ ] \ | ( )
< >                          # < 是单词边界，> 是量词
```

### 安全的字面量替换

```powershell
# [OK] 如果确定 <br/> 是字面量（无正则元字符冲突），可以用
# 但最好用 [System.Text.RegularExpressions.Regex]::Escape() 转义

# [OK] 显式转义
$pattern = [System.Text.RegularExpressions.Regex]::Escape('<br/>')
$content -replace $pattern, '·'

# [OK] 或使用 .NET 的 String.Replace (非正则)
$content.Replace('<br/>', '·')
```

## 文件编码规范

### 强制使用 UTF-8 BOM

```powershell
# [OK] 读取 UTF-8 文件
$content = Get-Content -Path file.js -Raw -Encoding UTF8

# [OK] 写入 UTF-8 文件
Set-Content -Path file.js -Value $content -Encoding UTF8

# [OK] 使用 [System.IO.File] 类（推荐）
[System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
```

### 检测文件编码

```powershell
# [OK] 检测文件编码
function Get-FileEncoding {
    param([string]$Path)
    $bytes = [byte[]](Get-Content -Path $Path -Raw -Encoding Byte)
    if ($bytes.Count -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return 'UTF8-BOM'
    }
    return 'Unknown'
}
```

## 注释保护规则

### 禁止在注释附近使用 -replace

```powershell
# [X] 危险 - 如果文件包含 "BR" 的注释，会被误匹配
$content -replace 'BR', 'XX'

# [OK] 如果必须替换，先检查文件中是否有危险模式
if ($content -match '//.*BR|/\*.*BR') {
    Write-Error "文件包含含 BR 的注释，替换可能导致问题"
}
```

### JavaScript/TypeScript 注释特征

```
// 单行注释
/* 多行
   注释 */
// TODO: 包含 BR 的注释
const centerMark = '◆';  // 中心节点标记
```

## PowerShell → Bash 语法速查

| PowerShell | Bash | 说明 |
|------------|------|------|
| `$var` | `$var` | 变量 |
| `$content = Get-Content file` | `content=$(cat file)` | 读取文件 |
| `Get-ChildItem` | `ls` | 列出文件 |
| `Copy-Item src dst` | `cp src dst` | 复制 |
| `-replace 'a', 'b'` | `sed 's/a/b/g'` | 替换（注意：sed 也需转义） |
| `ForEach-Object { $_ }` | `xargs` 或 `while read` | 循环 |

## [!!!] PowerShell + Git 兼容性坑 [!!!]

> **PowerShell 会解析 Git 特殊语法，导致命令静默失败！**

### 坑 1：`stash@{0}` 被 PowerShell 拆分

```powershell
# [X] PowerShell 把 @{0} 当 script block，拆成多个参数
git stash show -p stash@{0}
# 错误: Too many revisions specified: 'stash@' 'MAA=' 'xml' 'xml'

# [OK] 用变量 + 单引号
$stashRef = 'stash@{0}'
git stash show -p $stashRef
```

### 坑 2：`stash@{0}:path` 路径被吃掉

```powershell
# [X] PowerShell 把 : 当 scope qualifier，路径前缀被吞
git show stash@{0}:meta/core/file.py
# 错误: ambiguous argument '/core/file.py'

# [OK] 把整段 ref+path 包成单引号字符串
$refWithPath = 'stash@{0}:meta/core/file.py'
git show $refWithPath
```

### 坑 3：`head -N` 不存在

```powershell
# [X] head 是 bash 命令，PowerShell 没有
git log | head -20
# 错误: 无法将"head"项识别为 cmdlet

# [OK] 用 Select-Object -First
git log | Select-Object -First 20
```

### PowerShell → Git 命令速查

| Bash 写法 | PowerShell 写法 | 说明 |
|-----------|----------------|------|
| `git stash show stash@{0}` | `$r='stash@{0}'; git stash show $r` | `@{}` 是 PS script block |
| `git show stash@{0}:path` | `$r='stash@{0}:path'; git show $r` | `:` 是 PS scope qualifier |
| `git log \| head -20` | `git log \| Select-Object -First 20` | 无 `head` 命令 |
| `git log \| tail -20` | `git log \| Select-Object -Last 20` | 无 `tail` 命令 |
| `git diff \| grep "xxx"` | `git diff \| Select-String "xxx"` | 无 `grep` 命令 |
| `git log \| wc -l` | `(git log).Count` | 无 `wc` 命令 |

### 铁律：Git 命令中带 `@{}` 或 `:` 必须用变量

```powershell
# [!!!] 任何 git ref 语法带 @{...} 或 : 都必须先存变量 [!!!]
$stashRef = 'stash@{0}'
$refPath = 'stash@{0}:path/to/file'

# 然后用变量传参
git stash show $stashRef
git show $refPath
```

## 常见踩坑

### 1. curl 是 Invoke-WebRequest 别名

```powershell
# [X] 绝对禁止 - curl 是别名，会卡死在交互式等待
curl http://localhost:3000/api

# [OK] 用 curl.exe（真实二进制）
curl.exe http://localhost:3000/api

# [OK] 或用 Invoke-RestMethod
Invoke-RestMethod -Uri http://localhost:3000/api
```

### 2. 路径分隔符

```powershell
# [OK] 统一用正斜杠 /（PowerShell 两边都支持）
$path = "d:/filework/project/file.js"
Get-Content "d:/filework/project/file.js"

# [X] 避免混用反斜杠 \
$path = "d:\filework\project\file.js"  # 需要转义
```

### 3. 管道重定向

```powershell
# [X] 错误语法
command 2>&1 1>file  # 行为不确定

# [OK] 正确语法
command *> file           # 所有输出到文件
command 2>&1 | Out-File  # PowerShell 原生
```

### 4. 变量展开

```powershell
# [X] 在单引号中 $ 不会展开
$path = 'C:\Users\$env:USERNAME'  # $env:USERNAME 不会展开

# [OK] 用双引号
$path = "C:\Users\$env:USERNAME"  # 会展开
```

## AI Coding Agent 行为准则

### 做文件替换前必须

1. **确认是字面量替换还是正则替换**
   - 如果包含 `<`、`>`、`$`、`*` 等元字符，必须转义
   - 优先使用 `String.Replace()` 而非 `-replace`

2. **指定编码**
   - 读取：`Get-Content -Encoding UTF8`
   - 写入：`Set-Content -Encoding UTF8`

3. **备份原文件**
   - 替换前 `Copy-Item file.js file.js.bak`

4. **验证结果**
   - 检查注释是否完整
   - 检查特殊字符（`◆`、`●`、`■`）是否正确

### 如果发生 mojibake

1. **立即停止操作**
2. **用备份恢复**：`Copy-Item file.js.bak file.js`
3. **使用正确编码重试**

## 参考

- [PowerShell -replace operator](https://docs.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_comparison_operators#replacement-operator)
- [File encoding in PowerShell](https://stackoverflow.com/questions/40098914/read-write-files-with-utf-8-encoding-in-powershell)
- 业界: [PowerShell pitfalls](https://docs.microsoft.com/en-us/powershell/scripting/learn/deep-dives/everything-you-wanted-to-know-about-about)

---

_本规则防止 PowerShell 编码/正则陷阱导致代码损坏_
