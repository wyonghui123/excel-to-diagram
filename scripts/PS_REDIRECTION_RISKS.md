# PowerShell 重定向风险速查 - V2.1 P2-4

> **目标**：列出所有已知危险的 PowerShell 重定向操作，让 AI Agent 在执行前避免假成功。
>
> **平均成本**：每次假成功 **60 分钟**（重跑 + 诊断 + 重新执行）

---

## 🚨 一页纸速查（AI Agent 必读）

### 3 大危险类别

| 类别 | 操作 | 沙箱假成功？| 替代 |
|------|------|------------|------|
| **PS 重定向操作符** | `> file`, `>> file`, `2>&1 > file` | 🔴 高 | **Write 工具** |
| **PS 文件 cmdlet** | `Out-File`, `Set-Content`, `Add-Content` | 🔴 高 | **Write 工具** |
| **Bash 风格（PS中）**| `echo > file`, `tee file` | 🔴 高 | **Write 工具** |

### 黄金规则

> **任何 PS 重定向 → 用 Write 工具替代**（不依赖沙箱状态）

---

## 详细风险表

### 类别 1：PS 重定向操作符

#### ❌ `command > file.txt`

**风险**：在 trae-sandbox 隔离状态下，`>` 操作符执行成功（exit 0），stdout 正常输出，但 **文件未创建**。

**事故案例**：
- 2026-06-20 多 Agent 报告 `git diff > fix.patch` 假成功，patch 28 bytes（实际空内容）
- 浪费 30-60 分钟排查为什么文件没内容

**✅ 替代**：
```python
# AI Agent 应该用 Write 工具
Write(file_path='fix.patch', content='<patch content>')
```

#### ❌ `command >> file.txt` (追加)

**风险**：跟 `>` 一样，假成功。

**✅ 替代**：
```python
# 1. Read 文件获取现有内容
# 2. Edit 工具修改（追加）
# 3. Read 反向验证
```

#### ❌ `command 2>&1 > file.txt`

**风险**：复合重定向在沙箱下不可靠，stdin/stdout/stderr 可能都丢失。

**✅ 替代**：
```python
# 用 Read 工具读日志文件（如果存在）
Read(file_path='logs/backend.out')
```

### 类别 2：PS 文件写入 cmdlet

#### ❌ `Out-File -Path file.txt`

**风险**：Out-File 在沙箱隔离时返回成功，但文件未写入。

**✅ 替代**：Write 工具

#### ❌ `Set-Content -Path file.txt -Value "content"`

**风险**：Set-Content 跟 Out-File 类似。

**✅ 替代**：Write 工具

#### ❌ `Add-Content -Path file.txt -Value "more"`

**风险**：追加写入场景同样假成功。

**✅ 替代**：Read + Edit（追加）

### 类别 3：Bash 风格（PowerShell 中）

#### ❌ `echo "hello" > file.txt`

**风险**：在 PS 中 `echo` 是别名，`>` 在沙箱下假成功。

**✅ 替代**：
```python
Write(file_path='file.txt', content='hello\n')
```

#### ❌ `command | tee file.txt`

**风险**：tee 在 PS 沙箱下假成功。

**✅ 替代**：
```python
# 1. RunCommand 跑命令（不让 tee 重定向）
result = RunCommand('command')
# 2. Write 工具写文件
Write(file_path='file.txt', content=result.stdout)
```

---

## AI Agent 工作流（避免假成功）

### 推荐工作流

```
1. 检查：python scripts/check_powershell_redirection.py detect "<你的命令>"
2. 如果危险：用 Write 工具替代
3. 验证：用 Read 工具反向确认文件已写入
```

### 错误工作流（容易踩坑）

```
1. RunCommand("echo > file")
2. exit 0 ✓
3. 不验证就继续 → 后续发现文件不存在 → 浪费 60 分钟
```

### 正确工作流

```
1. Write(file_path='file.txt', content='content')  # 直接用工具
2. Read(file_path='file.txt')  # 反向确认
3. 继续
```

---

## 自动检测工具

### `scripts/check_powershell_redirection.py`

```bash
# 检测单个命令
python scripts/check_powershell_redirection.py detect "git diff > fix.patch"

# 列出所有已知危险操作
python scripts/check_powershell_redirection.py list

# 显示安全替代方案
python scripts/check_powershell_redirection.py alternatives "echo > file.txt"

# 集成到 debug_backend.py（自动运行）
python scripts/debug_backend.py check
# → Step 0: PS 重定向风险检查（自动）
```

### 检测模式

工具会扫描以下危险模式：

| 模式 | 说明 |
|------|------|
| `>` / `>>` 重定向到 .txt/.md/.json/.log | PS 重定向 |
| `2>&1 >` 复合重定向 | 不可靠 |
| `Out-File` / `Set-Content` / `Add-Content` | PS cmdlet |
| `echo > file` / `tee file` | Bash 风格 |
| `git diff > file` / `git show > file` | 已知高发场景 |

---

## 集成方案

### 集成到 `debug_backend.py`

新增 **Step 0**：PS 重定向风险检查（自动）

```python
# debug_backend.py
def check_powershell_redirection_safe():
    """V2.1 P2-4: 扫描 AI 最近命令历史（如果有）"""
    result = _run(["python", "scripts/check_powershell_redirection.py", "check"])
    # 显示警告
    if has_risk:
        _log("检测到 PS 重定向操作，可能假成功", "FAIL")
        _log("建议: 用 Write 工具替代", "WARN")
```

### 集成到 `agent_bootstrap.ps1`

```powershell
# agent_bootstrap.ps1
Write-Host "[0/5] PowerShell 重定向风险检查..."
python scripts/check_powershell_redirection.py check
```

### **不集成**到 `hooks.json`

**原因**：2026-06-21 用户报告 "昨天的 hook 问题" → 所有 hooks 已关闭
加新 hook 可能再次触发问题，所以**改用主动检测**（AI Agent 启动时自动调用）

---

## 与 V2/V2.1 铁律的关系

| 铁律 | 关联 |
|------|------|
| **铁律 6** (Read-First 工作流) | 沙箱隔离时优先用 Write/Read 工具（不依赖 PS 重定向）|
| **铁律 7** (工具降级顺序) | 沙箱隔离时禁用 RunCommand → 用 Write 工具替代 |
| **铁律 12** (修复完整性) | 提交前跑 `check_fix_completeness.py` |
| **铁律 13** (决策日志) | 使用 PS 重定向是违规决策，必须记录 |

---

## 事故案例库

### 案例 1：`git diff > fix.patch` 假成功（2026-06-20）

```powershell
PS> git diff > fix.patch
PS> ls -l fix.patch  # 28 bytes
PS> cat fix.patch   # ... 但实际是空内容
```

**浪费**：30-60 分钟排查为什么 patch 没内容

**正确做法**：
```python
diff = RunCommand('git diff')
Write(file_path='fix.patch', content=diff.stdout)
Read(file_path='fix.patch')  # 验证
```

### 案例 2：`echo > file` 在调试循环中反复失败

```powershell
PS> for ($i=0; $i -lt 5; $i++) { echo "data $i" > log.txt }
PS> cat log.txt   # "data 4"（只有最后一次，echo > 是覆盖不是追加）
```

**浪费**：5 分钟 + 后续调试困惑

**正确做法**：
```python
content = '\n'.join([f"data {i}" for i in range(5)])
Write(file_path='log.txt', content=content)
```

---

## FAQ

### Q1: 沙箱正常时能用 `>` 吗？

**A**: 理论上可以，但**不推荐**。理由：
1. 沙箱状态随时可能切换到"隔离"
2. AI Agent 不知道当前沙箱状态（必须跑 check_sandbox_status.py）
3. 用 Write 工具无差别可用，最安全

### Q2: Write 工具 vs PS 重定向 的性能差异？

**A**: Write 工具更快（直接文件 I/O，不经过 PS）。对于大文件也更快。

### Q3: 如果非要批量写文件呢？

**A**: 用 Python 脚本（不要用 PS 循环 + 重定向）：
```python
# scripts/batch_write.py
from pathlib import Path
files = [
    ('file1.txt', 'content1'),
    ('file2.txt', 'content2'),
]
for path, content in files:
    Path(path).write_text(content, encoding='utf-8')
```

### Q4: `curl | tee` 这种流水线怎么办？

**A**: 分两步：
```python
# Step 1: RunCommand 跑 curl（不带 tee）
result = RunCommand('curl.exe https://...')
# Step 2: Write 工具保存
Write(file_path='downloaded.html', content=result.stdout)
```

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-21 | v1.0 | 初版：基于 2026-06-20 多 Agent 反馈 |

_本文档由 V2.1 P2-4 实施（2026-06-21）_