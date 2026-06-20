---
name: sandbox-aware-execution
description: "执行 shell 命令前加载 trae-sandbox 行为规范，避免假成功陷阱。当 AI 需要使用 RunCommand 工具时自动触发。"
version: 1.0.0
---

# Sandbox-Aware Execution Skill

> **触发时机**：AI 需要执行任何 shell 命令（git、echo、PowerShell、python 等）时
> **核心价值**：避免 trae-sandbox 假成功陷阱，用 Read/Write 工具绕过沙箱

## 何时调用本 Skill

✅ **必须调用**：
- AI 即将执行任何 `RunCommand` 工具调用
- 需要验证 git 操作是否成功（commit/add/worktree/branch）
- 需要创建临时文件（脚本、日志、测试数据）
- 需要读取命令输出（git log / git status / service status）

❌ **不需要调用**：
- 使用 `Read` / `Write` / `Edit` / `LS` / `Glob` / `Grep` 工具（这些不受沙箱影响）

## trae-sandbox 行为速查

| 操作 | 是否生效 | 替代方案 |
|------|---------|---------|
| `git commit` | ✅ | - |
| `git worktree add/remove` | ✅ | - |
| `git log/status/diff` | ⚠️ 输出被吞 | 用 Read 读 `.git/logs/HEAD` |
| `git worktree list` | ⚠️ 输出被吞 | 用 LS 读 `.git/worktrees/` |
| `echo hello` | ❌ | - |
| `echo > file` | ❌ 假成功 | 用 Write 工具 |
| `Out-File` | ❌ 假成功 | 用 Write 工具 |
| 复杂 PowerShell `-match 'a=b'` | ❌ | 改用 Write 工具创建脚本 |

## 4 个解决方案

### 方案 1：Read 工具读取 .git 目录（最可靠）

```python
# 查询 worktree 状态
LS: d:\filework\excel-to-diagram\.git\worktrees
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\HEAD
Read: d:\filework\excel-to-diagram\.git\worktrees\<name>\logs\HEAD

# 查询 main HEAD
Read: d:\filework\excel-to-diagram\.git\HEAD
Read: d:\filework\excel-to-diagram\.git\logs\HEAD

# 查询分支列表
LS: d:\filework\excel-to-diagram\.git\refs\heads
Read: d:\filework\excel-to-diagram\.git\refs\heads\<branch>
```

### 方案 2：Write 工具创建文件（替代 echo）

```python
# ❌ 错误：echo 重定向假成功
echo test > d:\filework\_test.txt

# ✅ 正确：用 Write 工具
Write(file_path='d:\filework\_test.txt', content='test')
```

### 方案 3：Read 验证写入

```python
# 写入后立即验证
Write(file_path='d:\filework\_test.txt', content='test')
Read(file_path='d:\filework\_test.txt')
# → 不存在？说明 Write 也被拦截了
```

### 方案 4：MCP 工具（如果可用）

- `mcp__filesystem` - 直接文件访问
- `mcp__git_github` - GitHub API

## 实际案例

### 案例 1：查询 worktree 状态（不依赖 git 命令）

```python
# Step 1: 列出所有 worktree
LS: d:\filework\excel-to-diagram\.git\worktrees

# Step 2: 读取每个 worktree 的 HEAD
for wt in os.listdir('.git/worktrees'):
    Read: d:\filework\excel-to-diagram\.git\worktrees\<wt>\HEAD
    Read: d:\filework\excel-to-diagram\.git\worktrees\<wt>\logs\HEAD
```

### 案例 2：清理 worktree + 验证

```python
# Step 1: 删除 worktree
RunCommand: git worktree remove d:\filework\<path> --force

# Step 2: 验证删除成功
LS: d:\filework\excel-to-diagram\.git\worktrees
# → 没有 <name> 条目 = 删除成功
```

### 案例 3：删除分支 + 验证

```python
# Step 1: 删除分支
RunCommand: git branch -D <branch>

# Step 2: 验证删除成功
LS: d:\filework\excel-to-diagram\.git\refs\heads
# → 没有 <branch> 条目 = 删除成功
```

### 案例 4：查询 main HEAD commit

```python
# ❌ 错误：git log 输出被吞
git log --oneline -1

# ✅ 正确：读取 .git/logs/HEAD
Read: d:\filework\excel-to-diagram\.git\logs\HEAD
# → 最后一行是最新 commit 信息
```

### 案例 5：创建 PowerShell 脚本

```python
# ❌ 错误：echo 多行被截断
echo "line1" > script.ps1
echo "line2" >> script.ps1

# ✅ 正确：用 Write 工具
Write(
    file_path='d:\filework\script.ps1',
    content="line1\nline2\nline3\n"
)
```

## 反模式（禁止）

### ❌ 错误：用 git 命令查状态

```python
git worktree list
git log --oneline -5
git status --short
```

→ 输出被吞，AI 看不到结果

### ❌ 错误：用 shell 重定向创建文件

```python
echo test > file.txt
echo "x" | Out-File file.txt
Set-Content -Path file.txt -Value 'x'
```

→ 假成功，文件没创建

### ❌ 错误：在 Hook 用复杂 PowerShell

```powershell
powershell -Command "if (\$cmd -match 'a=b') { ... }"
```

→ `unexpected argument '=' found`

### ❌ 错误：连续重试失败的命令

```python
git status   # 假成功 1
git status   # 假成功 2
git status   # 假成功 3
```

→ 浪费时间，不如直接用 Read 工具

## 必做

✅ 用 Read 工具验证 git 操作
✅ 用 Write 工具创建文件
✅ 写入后用 Read 验证
✅ 用 LS 验证目录结构
✅ 用 MCP 工具绕过沙箱

## 参考

- 规则文件：`powershell-execution-guide.md`（整合 trae-sandbox + powershell 规则）
- 2026-06-20 trae-sandbox 行为发现
- `.trae/rules/multi-agent-coordination.md` - L5 动态适配策略
