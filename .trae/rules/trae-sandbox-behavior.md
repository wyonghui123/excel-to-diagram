---
description: "Trae IDE trae-sandbox 工具的行为特征和应对方案。所有 AI 智能体必须了解沙箱不一致行为。"
globs: "**/*"
alwaysApply: true
---

# Trae IDE trae-sandbox 行为特征与应对

> **2026-06-20 重要发现：Trae IDE trae-sandbox 工具行为不一致，必须绕过或用 Read 工具验证。**

## trae-sandbox 是什么

Trae IDE 内部用来隔离命令执行的工具。所有 `RunCommand` 工具调用都会被它包装：

```
trae-sandbox.exe exec --storage-path <path> --config-name <name> --shell-path <path> --command-line "<cmd>"
```

## 行为不一致矩阵

| 操作类型 | 是否生效 | 说明 |
|---------|---------|------|
| `git commit` | ✅ 正常 | git 内部直接处理 |
| `git add` | ✅ 正常 | git 内部直接处理 |
| `git worktree add/remove` | ✅ 正常 | git 内部直接处理 |
| `git status/log/diff` | ✅ 正常（exit 0） | 但 **stdout 被吞** |
| `git branch` | ✅ 正常（exit 0） | 但 **stdout 被吞** |
| `echo hello` | ❌ 假成功 | stdout 被吞，无任何输出 |
| `echo > file` | ❌ **假成功** | 文件**不会**被创建 |
| `Out-File` | ❌ **假成功** | 文件**不会**被创建 |
| `Set-Content` | ⚠️ 可能成功 | trae-sandbox 版本而定 |
| 复杂 PowerShell `-match 'a=b'` | ❌ 参数解析失败 | `unexpected argument '=' found` |
| `powershell -File script.ps1` | ⚠️ 部分支持 | 取决于脚本复杂度 |

## 关键陷阱：3 类"假成功"

### 假成功 1：stdout 完全被吞

```powershell
echo hello
# → exit 0，但 AI 看不到任何输出
git log --oneline -5
# → exit 0，但 AI 看不到 git log 结果
```

**后果**：AI 以为命令失败需要重试，浪费时间

### 假成功 2：shell 重定向不生效

```powershell
echo test > d:\filework\_test.txt
# → exit 0，但文件**没有**被创建
Set-Content -Path file.txt -Value 'x' -Encoding UTF8
# → exit 0，但文件**没有**被创建
```

**后果**：AI 以为文件已写入，但实际不存在

### 假成功 3：复杂命令参数解析失败

```powershell
powershell -Command "if (\$cmd -match 'a=b') { ... }"
# → exit 0 + error: unexpected argument '=' found
```

**后果**：Hook 静默失败，规则不生效

## 解决方案（4 个）

### 方案 1：用 Read 工具读取 .git 目录（最可靠）

```python
# ❌ 错误：用 git 命令（输出被吞）
git worktree list
git log --oneline -5
git status --short

# ✅ 正确：用 Read 工具读取 .git 内部文件
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\HEAD
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\logs\HEAD
Read: d:\filework\excel-to-diagram\.git\refs\heads\<branch>
Read: d:\filework\excel-to-diagram\.git\logs\HEAD
```

**可读取的文件**：

| 文件 | 包含信息 |
|------|---------|
| `.git/worktrees/<name>/HEAD` | 当前分支 |
| `.git/worktrees/<name>/logs/HEAD` | commit 历史 |
| `.git/refs/heads/<branch>` | 分支 hash |
| `.git/HEAD` | 当前 HEAD |
| `.git/logs/HEAD` | HEAD 移动历史 |

### 方案 2：用 Write 工具创建文件（替代 echo > file）

```python
# ❌ 错误：echo 重定向假成功
echo test > d:\filework\_test.txt

# ✅ 正确：用 Write 工具
Write(file_path='d:\filework\_test.txt', content='test')

# 多行内容用 \n
Write(file_path='script.ps1', content="line1\nline2\nline3")
```

### 方案 3：用 Read 工具验证写入

```python
# 写入后立即验证（避免假成功陷阱）
Write(file_path='d:\filework\_test.txt', content='test')
Read(file_path='d:\filework\_test.txt')
# → 不存在？说明 Write 也被拦截了
```

### 方案 4：用 MCP 工具绕过沙箱（如果可用）

| MCP 工具 | 用途 |
|---------|------|
| `mcp__git_github` | GitHub 操作 |
| `mcp__filesystem` | 文件读写（直接访问） |
| `mcp__playwright` | 浏览器自动化 |

这些工具通过 MCP 协议调用，不经过 trae-sandbox。

## Stage 2 副作用验证（更新版）

由于 trae-sandbox 行为不一致，副作用验证必须改用 Read 工具：

### 验证 `git commit` 是否成功

```python
# ❌ 旧：用 git log 看（输出被吞）
git log --oneline -1

# ✅ 新：读取 .git/logs/HEAD 验证
Read: d:\filework\excel-to-diagram\.git\logs\HEAD
# → 检查最后一行是否包含你的 commit message
```

### 验证 `git worktree add` 是否成功

```python
# ✅ 新：列出 .git/worktrees/ 目录
LS: d:\filework\excel-to-diagram\.git\worktrees
# → 看是否有新条目
```

### 验证 `git branch -d` 是否成功

```python
# ✅ 新：读取 .git/refs/heads/ 目录
LS: d:\filework\excel-to-diagram\.git\refs\heads
# → 看分支是否还在
```

### 验证文件写入是否成功

```python
# ✅ 新：用 Read 工具检查文件
Read: d:\filework\<file_path>
# → 文件存在？读取到内容？说明写入成功
```

## 实际案例：Worktree 状态查询

**问题**：`git worktree list` 输出被吞，AI 看不到结果

**解决方案**：用 LS + Read 工具：

```python
# Step 1: 列出所有 worktree 目录
LS: d:\filework\excel-to-diagram\.git\worktrees
# → ["agent-help-entry-worktree", "agent-import-dialog-fixes", ...]

# Step 2: 读取每个 worktree 的 HEAD
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\HEAD
# → "ref: refs/heads/<branch>"

# Step 3: 读取 commit 历史
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\logs\HEAD
# → 多行 commit 记录
```

## 实际案例：Worktree 清理

**问题**：`git worktree remove` 后无法验证是否成功

**解决方案**：分两步

```python
# Step 1: 删除 worktree（git 内部处理，应该生效）
RunCommand: git worktree remove d:\filework\<path> --force

# Step 2: 用 LS 验证目录是否被删除
LS: d:\filework\excel-to-diagram\.git\worktrees
# → 没有 <name> 条目 = 删除成功

# Step 3: 删除分支
RunCommand: git branch -D <branch>

# Step 4: 验证分支删除
LS: d:\filework\excel-to-diagram\.git\refs\heads
# → 没有 <branch> 条目 = 删除成功
```

## 不要做的事

- ❌ **不要相信 stdout 输出**（被 trae-sandbox 吞了）
- ❌ **不要用 echo > file 创建文件**（假成功）
- ❌ **不要用 Out-File/Set-Content 创建文件**（假成功）
- ❌ **不要在 Hook 用 `-match 'a=b'` 复杂表达式**（参数解析失败）
- ❌ **不要连续重试同一个失败的命令**（浪费时间）
- ❌ **不要用 `git log` / `git status` 验证结果**（输出被吞）

## 必须做的事

- ✅ **用 Read 工具读取 .git 内部文件**（最可靠）
- ✅ **用 Write 工具创建文件**（替代 echo > file）
- ✅ **写入后用 Read 验证**（避免假成功）
- ✅ **用 LS 工具列出目录**（验证文件存在）
- ✅ **用 MCP 工具绕过沙箱**（如果可用）

## 参考

- 2026-06-20 trae-sandbox 行为发现
- `.trae/rules/multi-agent-coordination.md` - L5 沙箱检测（动态适配策略）
- `.trae/rules/SESSION_REMINDER.md` - 18 铁律
- 业界：[Trae IDE 官方文档](https://docs.trae.cn/ide_what-is-trae)
