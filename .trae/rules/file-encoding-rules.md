---
alwaysApply: false
description: "文件编码规范：UTF-8 强制、PowerShell 编码陷阱、mojibake 防护"
globs: "scripts/*.ps1,*.py"
---

# 文件编码与字符串语法规范 [NEW 2026-06-05]

> [!!!] 本文件是所有 Agent 写文件/读文件前必读的规范 [!!!]
> [!!!] 违反本规范 = 文件损坏 + 调试时间 +30 分钟（真实案例） [!!!]

---

## 一、真实踩坑案例（2026-06-05）

### 案例 1：docstring 闭合缺失

**症状**：Python 报 `IndentationError at line 42`，调试 30+ 分钟。

**根因**（多步因果链）：
1. 写文件时编码错误（GBK 或部分 UTF-8 写入）
2. 中文 `完整 schema（多跳需要完整体 hierarchy 层次）` 损坏成 `完整 schema（多跳需要完�?hierarchy�?`
3. 末尾 `"""` 闭合符变成 `""`（**差 1 个 `"`**）
4. Python 解析器把整个 docstring 延续到 line 41 的 `"""`
5. line 42 的 `        -- 用户/角色` 被当作 Python 代码
6. `--` 不是合法 Python token → `IndentationError`

**修复**：line 35 末尾补 1 个 `"`，重保存为 UTF-8 无 BOM。

**教训**：规范只规定"用 UTF-8"（SESSION_REMINDER.md 铁律 22）不够，必须**强制验证**。

### 案例 2：PowerShell Set-Content 导致编码损坏 [NEW]

**症状**：Agent 用 `Set-Content` 覆盖文件后，`ast.parse()` 报 `IndentationError`。

**根因链**：
```
Agent 用 Set-Content 覆盖文件（无 -Encoding 参数）
    ↓
PowerShell 默认编码（PS5 = UTF-16 LE，PS7 = UTF-8 无 BOM）
    ↓
中文被错误编码 → U+FFFD 替换字符
    ↓
docstring 末尾 """ 变成 ""（少 1 个 "）
    ↓
Python 解析器把 docstring 延续到下个 """
    ↓
中间所有代码被吞掉 → IndentationError
```

**关键教训**：
- **永远不要用 `Set-Content` 覆盖含中文的 .py 文件**
- **必须用 Python 写文件**（`open(..., encoding='utf-8')`）
- **或用 `Set-Content -Encoding UTF8`（但仍有 BOM 风险）**

**诊断方法**：
```powershell
# 检查文件末尾是否有 3 个 "
$line = (Get-Content 'file.py' -Encoding UTF8)[34]
$bytes = [System.Text.Encoding]::UTF8.GetBytes($line)
($bytes | Select-Object -Last 5 | ForEach-Object { $_.ToString('X2') }) -join ' '
# 期望: 22 22 22 (三个双引号)
# 实际: 22 22 (两个双引号) → docstring 损坏
```

---

## 二、7 条铁律（违反 = 文件可能损坏）

| # | 铁律 | 违规后果 | 正确做法 |
|---|------|---------|---------|
| 1 | **写文件前必须显式指定 `encoding='utf-8'`** | 默认编码可能丢失中文 | 所有 `open()` / `Write` / `Edit` 操作都要 utf-8 |
| 2 | **禁止用 `Write` 工具覆盖含中文的文件，除非 Read 验证过编码** | 覆盖后编码丢失 | 覆盖前先 Read 一次 |
| 3 | **docstring `"""` 必须严格 3 个 `"` 闭合** | docstring 跨多行 → 后续代码解析错乱 | 写完 `"""..."""` 后用 `ast.parse()` 验证 |
| 4 | **含中文 docstring 必须用 `# -*- coding: utf-8 -*-` 头** | 老 Python 解释器不认 | 第 1 行加 encoding 声明 |
| 5 | **写完 .py 文件必须 `python -c "import ast; ast.parse(open(f, encoding='utf-8').read())"` 验证** | 损坏的文件等到运行时才报 | 写完立即验证 |
| 6 | **PowerShell 读中文文件必须用 `Get-Content -Encoding UTF8`** | 默认 UTF-16 LE，BOM 错乱 | 显式 `-Encoding UTF8` |
| 7 | **禁止用 `Set-Content` 覆盖含中文的 .py 文件** [NEW] | PS5 默认 UTF-16 LE → 编码损坏 | 用 Python 写或 `Set-Content -Encoding UTF8` |

---

## 三、强制验证脚本

写完任何 `.py` 文件，**必须**跑：

```bash
python -c "import ast; ast.parse(open('FILE_PATH', encoding='utf-8').read())"
```

**集成到 `check_v2_compliance.py`** — `e2e/scripts/check_v2_compliance.py` 已扩展此检查。

---

## 四、常见错误模式与预防

### 4.1 U+FFFD 替换字符（最常见）

**症状**：中文显示为 `?` 或 `�?`（U+FFFD）

**根因**：源文件编码非 UTF-8（可能是 GBK/Big5/UTF-16）

**预防**：
```bash
# 检查文件实际编码
$bytes = [System.IO.File]::ReadAllBytes('file.py')
# 查找 EF BF BD (UTF-8 编码的 U+FFFD)
$bytes | Select-String -Pattern "EF BF BD" -CaseSensitive:$false
```

**修复**：
1. 找到源文件
2. 用正确编码重新读取
3. 用 UTF-8 写回

### 4.2 docstring 闭合缺失

**症状**：`IndentationError` 在非 docstring 行

**根因**：开 `"""` 3 个但闭 `"""` 2 个（中间被破坏）

**预防**：
```python
# 写 docstring 时显式分两行
"""开头内容"""  # ← 一次写完，不要拼接
```

**验证**：
```bash
python -c "import ast; ast.parse(open('file.py', encoding='utf-8').read())"
```

### 4.3 SQL comment `--` 在 Python 字符串中

**症状**：看到 `--` 就怀疑是 Python 注释

**真相**：在 `"""` 内的 `--` 是 SQL 注释，不是 Python 注释

**正确诊断步骤**：
1. **不要**直接看 `--` 报 `IndentationError`
2. **先**看 `"""` 配对是否平衡
3. 用 `ast.parse()` 验证整个文件

---

## 五、PowerShell 编码规范

```powershell
# [X] 错误：默认 Get-Content 在 PS5 是 UTF-16 LE
$content = Get-Content 'file.py'

# [OK] 正确：显式指定 UTF-8
$content = Get-Content 'file.py' -Encoding UTF8

# [OK] 正确：读取字节再转
$bytes = [System.IO.File]::ReadAllBytes('file.py')
$text = [System.Text.Encoding]::UTF8.GetString($bytes)
```

---

## 六、写入文件规范

### 6.1 用 `Write` 工具

**前提**：目标文件**不存在**或**不包含中文**

如果目标文件已存在且含中文：
1. 先用 `Read` 读取（IDE 会显示真实内容）
2. 验证 Read 结果无 `�?`
3. 再用 `Edit` 修改（不要用 Write 覆盖）

### 6.2 用 Python 写文件

```python
# [OK] 正确
with open('file.py', 'w', encoding='utf-8') as f:
    f.write(content)

# [X] 错误（Python 3 在 Windows 默认系统编码）
with open('file.py', 'w') as f:
    f.write(content)  # 可能丢失中文
```

### 6.3 用 Edit 工具

**前置检查**：
1. `old_string` 必须**唯一**
2. `old_string` 含中文时，IDE 必须能正常显示（无 `�?`）
3. `new_string` 也必须 UTF-8

---

## 七、Agent 工作流检查清单

写完任何文件，**自查**：

```
[ ] 写文件时显式 encoding='utf-8'？
[ ] 读文件时显式 -Encoding UTF8？
[ ] 文件第 1 行是 `# -*- coding: utf-8 -*-`（含中文的 .py）？
[ ] docstring 严格 3 个 """ 闭合？
[ ] 跑过 `python -c "import ast; ast.parse(open(f, encoding='utf-8').read())"`？
[ ] 跑过 `e2e/scripts/check_v2_compliance.py`（如果是 .spec.js）？
[ ] 没有 `?` 或 `�?` 字符出现？
```

**全部打钩 = 文件安全** [OK]

---

## 八、调试指南：遇到 `IndentationError` 时

**不要**直接看报错行。

**正确诊断步骤**：

```bash
# 1. 验证整个文件是否能 parse
python -c "import ast; ast.parse(open('FILE', encoding='utf-8').read())"

# 2. 失败时，看具体错误位置
python -c "import ast; ast.parse(open('FILE', encoding='utf-8').read())"
# IndentationError: unexpected indent at line 42

# 3. 实际错误往往在 line 42 之前的字符串未闭合
#    检查 line 42 之前所有 """ ''' ( [ {
```

**真实案例诊断**：
- 报错 line 42 → 实际根因在 line 35（docstring 末尾 `""` 而非 `"""`）
- **永远先验证 `"""` 平衡，再看报错行**

---

## 九、修改日志

| 日期 | 修改 | 作者 |
|------|------|------|
| 2026-06-05 | 创建本文档（基于真实踩坑案例） | Test Simplifier Agent |

---

_本文件是所有 Agent 读写文件前的必读规范，违反 = 文件损坏 + 调试 +30 分钟_
