# Debug 调试基础设施

> **V3.5 sandbox-safe 调试体系**（v2026.06.22）
> 上一版：V1 调试基础设施（v2026.06.21）

## 📋 目录结构

| 目录/文件 | 用途 | 写入工具 | 读取工具 |
|----------|------|---------|---------|
| `queries/` | 调试输出 (V3.5 safe-output) | `safe_query.py` / `safe_io.emit_safe_output()` | **Read 工具** |
| `markers/` | 异步操作状态 | `restart_safe.py` 自动 | **Read 工具** |
| `sessions/` | 调试会话记录 (V1 YAML) | 手动 | **Read 工具** |
| `snapshots/` | 用户上下文快照 (V1) | `inspect/user_context.py --save` | **Read 工具** |
| `sandbox_logs/` | Sandbox 事件日志 | PreToolUse hook | **Read 工具** |
| `watchdog/` | 主动监控 + 趋势检测 | `sandbox_watchdog.py` 自动 | **Read 工具** |

## 🚨 V3.5 核心原则

### 铁律 1: 永远不依赖 shell stdout

```bash
# ❌ 旧方式 (sandbox 故障时失效)
python scripts/debug/check_log_files.py --json

# ✅ V3.5 方式 (sandbox-safe)
python scripts/debug/check_log_files.py --json --safe-output
# → 写入 .trae/debug/queries/check_log_files_<timestamp>.json
# → AI 用 Read 工具读结果
```

### 铁律 2: 调试输出文件名规则

```
queries/<prefix>_<YYYYMMDD_HHMMSS_mmm>.json
markers/<name>.state.json
```

### 铁律 3: 健康检查先行

```bash
# 调试任何问题前先检测 sandbox
python scripts/debug/sandbox_health.py

# 返回值：
#   OK        - 一切正常
#   DEGRADED  - 部分功能受影响，safe-output 仍可用
#   BLOCKED   - 必须重启 IDE
```

## 🛠️ 已支持 safe-output 的 14 个调试脚本

| # | 脚本 | 用途 |
|---|------|------|
| 1 | `inspect/user_context.py` | 用户上下文 |
| 2 | `inspect/table_schema.py` | 表结构 |
| 3 | `inspect/code_map.py` | 代码映射 |
| 4 | `env/diagnose.py` | 环境诊断 |
| 5 | `check_field_mapping.py` | 字段映射 |
| 6 | `check_log_files.py` | 日志文件 |
| 7 | `check_debug_script_in_root.py` | 根目录检测 |
| 8 | `check_unused_return.py` | 未使用返回值 |
| 9 | `check_silent_exceptions.py` | 静默异常 |
| 10 | `check_class_consistency.py` | 类一致性 |
| 11 | `check_backend_log_freshness.py` | 后端日志新鲜度 |
| 12 | `dashboard.py` | 调试仪表板 |
| 13 | `log/extractor.py` | 日志提取器 |
| 14 | `restart/restart_safe.py` | 后端重启（自动 marker） |

## 🎯 统一入口 (P3 新增)

```bash
# 所有调试操作的统一入口
python scripts/debug/safe_query.py query <script-name> [--args ...]
python scripts/debug/safe_query.py health              # sandbox 健康
python scripts/debug/safe_query.py restart [backend|frontend|all]  # 服务管理
python scripts/debug/safe_query.py status             # session 状态
```

## 📊 Markers 自动追踪

`restart_safe.py restart` 自动写：
- `markers/backend_restart.state.json` - 状态: running/done/failed
- 包含 5 个步骤的进度

如果 marker 卡在 `running` → sandbox 故障或后端真没起来。

## 🔍 完整规范文档

| 规范 | 文件 |
|------|------|
| V3.5 sandbox-safe 调试 | `.trae/rules/sandbox-safe-debugging.md` |
| Terminal 交互式 Prompt | `.trae/rules/terminal-interactive-prompt.md` |
| 多 Agent 协调 | `.trae/rules/multi-agent-coordination.md` |
| 调试基础设施 (V1) | `.trae/rules/debug-infrastructure-v20260621.md` |
| 规则索引 | `.trae/rules/RULES_INDEX.md` |

## 📝 自动化（V3.5 已实施）

- ✅ `scripts/debug/safe_query.py` - 统一入口 (P3)
- ✅ `scripts/debug/utils/sandbox_safe.py` - 输出 helper
- ✅ `scripts/debug/utils/safe_io.py` - emit_safe_output()
- ✅ `scripts/debug/utils/session_status.py` - 状态读取
- ✅ `scripts/debug/restart/restart_safe.py` - 自动 marker (P3)
- ✅ `scripts/debug/sandbox_health.py` - 健康检查
- ✅ `scripts/debug/sandbox_watchdog.py` - 主动监控 + 趋势检测 (P5)
- ✅ `scripts/debug/session_start_bootstrap.ps1` - SessionStart hook
- ⏳ `.trae/hooks.json` PreToolUse hook - 已配置提示

## 🐕 Sandbox Watchdog (P5 新增)

`scripts/debug/sandbox_watchdog.py` 是 `sandbox_health.py` 的主动版本，
周期性检查 + 趋势检测 + 早期预警，避免静默恶化到 BLOCKED。

### 快速使用

```bash
# 单次检查 + 更新状态
python scripts/debug/sandbox_watchdog.py check

# 启动后台监控（每 30s 检查一次）
python scripts/debug/sandbox_watchdog.py start --interval 30

# 停止后台监控
python scripts/debug/sandbox_watchdog.py stop

# 查看当前状态
python scripts/debug/sandbox_watchdog.py status

# 查看历史
python scripts/debug/sandbox_watchdog.py history --limit 20

# 查看报警
python scripts/debug/sandbox_watchdog.py alarms --limit 10
```

### 关键特性

| 特性 | 说明 |
|------|------|
| 趋势检测 | 连续 2 次 DEGRADED 触发 WARNING |
| 早期预警 | 在进入 BLOCKED 前主动提醒 |
| 状态机 | OK → DEGRADED → BLOCKED 转换追踪 |
| 文件持久化 | 状态写入 `.trae/debug/watchdog/state.json` |
| 历史日志 | `.trae/debug/watchdog/history.jsonl` |
| 报警日志 | `.trae/debug/watchdog/alarms.jsonl` |
| 后台模式 | Windows 下用 `taskkill /F /T /PID` 兜底 |
| 跨进程 | 其他工具可读 state.json 判断当前状态 |

## 🔄 V1 → V3.5 迁移指南

**V1 (2026.06.21)**：手动会话记录 + user_context.py --save
**V3.5 (2026.06.22)**：sandbox-safe 自动输出 + Read 工具读取 + 统一入口

### 迁移步骤

1. **替换输出方式**：
   - `print(...)` → `emit_safe_output(data, prefix=...)`
   - `>` 重定向 → `--safe-output` 参数
   - `Get-Content x.json` → Read 工具

2. **替换查询入口**：
   - 直接 `python scripts/debug/xxx.py` → `python scripts/debug/safe_query.py query xxx`

3. **添加启动检查**：
   - 调试前先跑 `safe_query.py health`

---

_本目录由 V3.5 sandbox-safe 调试体系升级（2026-06-22）_
_基于 V1 调试基础设施（2026-06-21）演进_