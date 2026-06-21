---
alwaysApply: true
description: "Sandbox-Safe 调试规范 V1 (v2026.06.21) - 应对 Trae IDE L5 sandbox 动态隔离导致 stdout/文件写入被吞的场景"
---

# Sandbox-Safe 调试规范 (V1)

> **背景**：2026-06-21 排查供应链系统关系列表问题时，SOLO Agent 遭遇严重 sandbox 故障：
> - PowerShell stdout 被吞 → Python stdout 被吞 → Python 文件写入被阻止 → MCP Filesystem 写入也被吞
> - Agent 在 6+ 种输出方式全部失败后放弃调试
> - **用户被迫重启 Trae IDE** 才能恢复
>
> **V1 规范**：建立 sandbox-safe I/O 体系，**永远不依赖 shell stdout 作为唯一输出通道**。

---

## 核心原则（铁律）

> **[!!!] AI Agent 调试时必须遵循以下原则，否则调试可能完全失效 [!!!]**

### 1. 永远不依赖 shell stdout
- shell 命令的 stdout 可能在 L5 sandbox 故障时被完全吞掉
- 即便 `Write-Host` 也可能被吞
- **必须用 Write 工具 / Read 工具**（不走 shell 路径）

### 2. 调试输出必须写入 `.trae/debug/queries/` 文件
- 文件路径：`D:\filework\excel-to-diagram\.trae\debug\queries\<prefix>_<timestamp>.json`
- 用 **Read 工具** 读取结果（不走 sandbox）
- 标准做法：在 `python ... --json` 后面加 `--safe-output`

### 3. 关键操作必须写状态标记
- 路径：`.trae/debug/markers/<name>.state.json`
- Agent 完成操作后写 `done`，失败时写 `failed: <error>`
- 如果 marker 卡在 `running` 超过预期时间 → sandbox 故障

### 4. 会话开始时检查 sandbox 健康
- 跑 `python scripts/debug/sandbox_health.py` 检测 L5 状态
- 检查结果写入 `.trae/debug/sandbox_health_report.json`
- **如果状态是 DEGRADED 或 BLOCKED** → 改用 Write/Read 工具

### 5. SessionStart hook 自动启动状态探测
- 每次新会话，hook 自动运行 `session_start_bootstrap.ps1`
- 状态文件：`.trae/debug/session_start_status.json`
- AI 用 Read 工具读取，无需依赖 shell

---

## 工具入口

### `python scripts/debug/sandbox_health.py`

L5 sandbox 健康检查工具。返回：
- `shell_stdout` - shell stdout 是否被吞
- `shell_write` - shell 文件写入是否生效
- `python_io` - Python I/O 是否正常（独立于 shell）
- `git_operations` - git 命令是否返回输出
- `overall_state` - `OK` / `DEGRADED` / `BLOCKED`

```bash
# 完整检查（输出到 .trae/debug/queries/sandbox_health_report_*.json）
python scripts/debug/sandbox_health.py

# 静默模式（只写文件，不输出到 stdout）
python scripts/debug/sandbox_health.py --no-stdout

# JSON 输出
python scripts/debug/sandbox_health.py --json

# 持续监控（每 30 秒）
python scripts/debug/sandbox_health.py --watch 30
```

### `python scripts/debug/utils/sandbox_safe.py`

Sandbox-safe I/O 工具库（Python 模块）。关键 API：

```python
from scripts.debug.utils.sandbox_safe import output, read_output, file_marker

# 写结构化数据到 .trae/debug/queries/
path = output({"key": "value"}, prefix="my_query")
# → 返回文件路径，用 Read 工具读取

# 读回数据
data = read_output("my_query_20260621_123456.json")

# 写状态标记
file_marker("my_task", "running")
# ... 干活 ...
file_marker("my_task", "done", extra={"count": 42})
```

### 修改后的调试脚本

以下调试脚本新增了 `--safe-output` 选项（V3.5 统一接口）：

| 脚本 | 用法 |
|------|------|
| `scripts/debug/inspect/user_context.py` | `python user_context.py TEST333 --json --safe-output` |
| `scripts/debug/inspect/table_schema.py` | `python table_schema.py <table> --json --safe-output` |
| `scripts/debug/env/diagnose.py` | `python diagnose.py --json --safe-output` |
| `scripts/debug/check_field_mapping.py` | `python check_field_mapping.py --json --safe-output` |
| `scripts/debug/check_log_files.py` | `python check_log_files.py --json --safe-output` |
| `scripts/debug/check_debug_script_in_root.py` | `python check_debug_script_in_root.py --json --safe-output` |
| `scripts/debug/dashboard.py` | `python dashboard.py --safe-output` |
| `scripts/debug/restart/restart_safe.py` | 自动写 `backend_restart` marker (无需手动) |

**统一 API** (`scripts/debug/utils/safe_io.py`):
```python
from scripts.debug.utils.safe_io import emit_safe_output

# 写文件
emit_safe_output(data, prefix="my_query", output_dir=None)
```

---

## 调试 SOP（V1 强制 6 步）

```
[1] python scripts/debug/sandbox_health.py
    → 检测 L5 状态，如果 BLOCKED 立即提醒用户重启 IDE

[2] Read .trae/debug/session_start_status.json
    → 后端/前端/Git/Worktree 状态

[3] python scripts/debug/inspect/user_context.py <user> --json --safe-output
    → 用户上下文，Read 工具读结果

[4] Read .trae/debug/queries/user_context_<user>_*.json
    → 实际权限数据

[5] python scripts/debug/inspect/table_schema.py <table> --check-code-fields --json --safe-output
    → 表结构 + 字段映射错误检测

[6] Read .trae/debug/queries/table_schema_*.json
    → 字段映射数据
```

---

## 禁止行为（铁律 2）

- ❌ **禁止只依赖 `print()` 输出**调试结果（sandbox 可能吞掉）
- ❌ **禁止 `python -c "print(...)"` 作为调试手段**
- ❌ **禁止用 `>` 重定向写入 `.trae/debug/`** （sandbox 可能阻止）
- ❌ **禁止反复 Read `backend.out` 整个文件**（用 log extractor）
- ❌ **禁止在 sandbox BLOCKED 时继续调试**（先解决 sandbox 问题）

---

## 推荐行为（铁律 3）

- ✅ **调试输出默认用 `--safe-output`**
- ✅ **关键操作前后写 file_marker**
- ✅ **Read 工具是首选输出获取方式**
- ✅ **SessionStart 时检查 `.trae/debug/session_start_status.json`**
- ✅ **批量操作前先跑 `sandbox_health.py`**

---

## 检测 sandbox 故障的快捷方法

如果遇到"命令不返回输出"或"文件没创建"，用以下 Python 命令快速判断：

```python
# 写入 .trae/debug/queries/_sandbox_diag_<ts>.txt
# 路径不依赖 stdout，可通过 Read 工具验证

import sys
from pathlib import Path
ts = __import__('time').time()
f = Path(f".trae/debug/queries/_sandbox_diag_{int(ts*1000)}.txt")
f.parent.mkdir(parents=True, exist_ok=True)
f.write_text(f"python={sys.version}\nstdout_ok=unknown\ncwd={Path.cwd()}\n", encoding="utf-8")
print(f"WROTE: {f.resolve()}")
```

如果用 Read 工具读不到这个文件 → sandbox 完全阻断 IO → 重启 IDE。

---

## 文件清单

| 文件 | 作用 |
|------|------|
| `scripts/debug/utils/sandbox_safe.py` | Sandbox-safe I/O 核心库 (output/file_marker/safe_print) |
| `scripts/debug/utils/safe_io.py` | 统一 `--safe-output` 接口 |
| `scripts/debug/sandbox_health.py` | L5 sandbox 健康检查工具 |
| `scripts/debug/session_start_bootstrap.ps1` | SessionStart 状态探测脚本 |
| `.trae/hooks.json` | SessionStart hook 配置 |
| `.trae/debug/queries/` | sandbox-safe 输出目录 |
| `.trae/debug/markers/` | 状态标记目录 |
| `.trae/debug/sandbox_logs/` | sandbox 事件日志 |
| `scripts/debug/inspect/user_context.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/inspect/table_schema.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/env/diagnose.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/check_field_mapping.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/check_log_files.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/check_debug_script_in_root.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/dashboard.py` | V3.5: 新增 `--safe-output` |
| `scripts/debug/restart/restart_safe.py` | V3.5: 自动写 `backend_restart` marker |

---

## 相关文档

- [debug-infrastructure-v20260621.md](./debug-infrastructure-v20260621.md) - 调试基础设施 V1
- [powershell-execution-guide.md](./powershell-execution-guide.md) - PowerShell 执行规范
- [SESSION_REMINDER.md](./SESSION_REMINDER.md) - 会话开始提醒

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-21 | AI Assistant | V1 初版，基于 SOLO Agent 关系列表调试事故复盘 |
| 2026-06-21 | AI Assistant | V3.5 扩展：safe_io helper + 12 个脚本支持 --safe-output + session_status reader |
