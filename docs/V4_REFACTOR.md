# V4.0 根因重构 - 一站式修复调试基础设施

**提交**: pending
**日期**: 2026-06-21
**目的**: 一次性修复 V3 系列遗留的所有补丁问题，提供真正的根因解决方案。

---

## 为什么需要 V4.0？

V3 系列（V3.5 → V3.7.2）做了 7 个版本，每次都是"修补补丁"：

| 版本 | 问题 | 解决方案 | 副作用 |
|------|------|---------|--------|
| V3.5 | caller 不检查返回值 | 加 `check_unused_return.py` | ✅ |
| V3.6 | auto-discovery 只找 1 个 db | 递归查找 | ✅ |
| V3.6 | PROJECT_ROOT 多 1 层 | 改 parent.parent.parent.parent | ✅ |
| V3.6 | dashboard 编码 GBK | 设 PYTHONIOENCODING=utf-8 | ✅ |
| V3.7 | 后端日志假健康 | 加 `check_backend_log_freshness.py` | ⚠️ 检测器不能阻止 |
| V3.7.1 | restart_safe.py + service_manager 启动 bug | 改 PROJECT_ROOT | ⚠️ 还是 8 秒超时 |
| V3.7.2 | dashboard 误报 + import re | 修复 dashboard | ⚠️ 还是没区分"启动中" |

**核心问题**：service_manager.py 启动后端用 `subprocess.Popen(powershell -File service_manager.ps1)`，
Popen 不等待 powershell 完成，等 8 秒就退出。但 powershell 自己又要 30+ 秒启动后端。
**结果：service_manager.py 永远报"port 3010 not responding"，但其实后端后来能起来**。

V4.0 一次性修复：

---

## V4.0 修复清单

### 修复 1：service_manager.py 直接启动 python（根因）

**Before** (V3.7.1):
```python
"start_cmd": ["powershell", "-File", "scripts/service_manager.ps1", "start-be"],
"wait_seconds": 8,
```

**After** (V4.0):
```python
"start_cmd": ["python", "-u", "waitress_server.py"],
"wait_seconds": 60,
```

**为什么是根因**：
- 5 层嵌套：Popen → powershell → service_manager.ps1 → pythonw → waitress
- 每层独立超时：8s + 30s + 0 + 启动 + 0 = 不可预测
- V4.0 单层直接启动，超时 60s 足够

### 修复 2：startup_state.json 跟踪启动状态

新文件：`.startup_state.json`

```json
{
  "backend": {
    "state": "starting" | "ready" | "failed" | "stale",
    "pid": 1234,
    "port": 3010,
    "started_at": "2026-06-21T...",
    "error": "port not listening within timeout"
  }
}
```

**作用**：dashboard 能区分"启动中 30s"和"启动失败"和"未启动"。

### 修复 3：dashboard.py 显示 STARTING 状态

**Before** (V3.7.2):
```
[X] 后端: FAIL (port not listening)
```

**After** (V4.0):
```
[i] 后端: STARTING (启动中 30s,后端初始化需 30-60s)
```

90 秒内显示 STARTING，超过 90s 显示 STALE。

### 修复 4：hooks.json PreToolUse 拦截根目录调试脚本

**Before**: Agent 写 `debug_*.py` 到根目录 → V3 dashboard 检测但不能阻止

**After**: Trae hook 在 Write 工具调用前拦截，拒绝并提示正确路径

```json
{
  "PreToolUse": [{
    "matcher": "Write",
    "hooks": [{
      "command": "powershell -File scripts/debug/hooks_pre_tool_use.ps1",
      "timeout": 10
    }]
  }]
}
```

拦截模式：`debug_*.py`, `analyze_*.py`, `query_*.py`, `check_*.py`, `test_*.py`, ...

### 修复 5：SessionStart 自动启动 watchdog

**Before**: 重启 Trae 后 watchdog 进程丢失

**After**: SessionStart hook 自动检查并启动 watchdog

```json
{
  "SessionStart": [{
    "hooks": [{
      "command": "powershell -File scripts/debug/session_start_bootstrap.ps1",
      "timeout": 60
    }]
  }]
}
```

输出到模型上下文：`[OK] watchdog 已在跑 (PID=12345)` 或 `[!] 后端端口未监听 (重启 IDE 后被杀,可用 restart_safe.py start 启动)`

---

## V4.0 新增/修改文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `scripts/service_manager.py` | 修改 | 直接 python 启动，60s 超时 |
| `scripts/debug/dashboard.py` | 修改 | 显示 STARTING 状态 |
| `.trae/hooks.json` | 修改 | 加 PreToolUse + SessionStart |
| `scripts/debug/hooks_pre_tool_use.ps1` | 新增 | PreToolUse 实现 |
| `scripts/debug/session_start_bootstrap.ps1` | 新增 | SessionStart 实现 |
| `docs/V4_REFACTOR.md` | 新增 | 本文档 |

---

## 验证步骤

```powershell
# 1. 重启后端（应该 60s 内完成，不再报 WARNING）
python scripts/debug/restart/restart_safe.py restart

# 2. Dashboard 应该显示 OK（不再误报）
python scripts/debug/dashboard.py --brief

# 3. 启动中状态测试（杀后端后立即启动，dashboard 应显示 STARTING）
python scripts/service_manager.py stop
python scripts/service_manager.py start-be &
python scripts/debug/dashboard.py --brief

# 4. PreToolUse 拦截测试（下次 Agent 写 debug_*.py 到根目录应被拒绝）
```

---

## 影响范围

- **excel-to-diagram**: ✅ 已应用 V4.0
- **fix-import-msg-worktree**: ⚠️ 需要 cherry-pick
- **biz-msg-ux-v2**: ⚠️ 需要 cherry-pick
- **agent-help-entry**: ⚠️ 需要 cherry-pick

V4.0 修改只影响 `scripts/service_manager.py`, `scripts/debug/dashboard.py`, `.trae/hooks.json` 三个文件，其他项目可以安全 cherry-pick。

---

## 向后兼容

- `restart_safe.py restart/stop/start/verify` 接口不变
- `dashboard.py --brief/monitor/export` 接口不变
- `service_manager.py status/start/stop/restart` 接口不变
- 新增 `.startup_state.json` 是只读缓存，删除不影响功能

---

## 下一步

- [ ] cherry-pick V4.0 到其他 worktree
- [ ] 监控 hook 拦截率（应该减少根目录违规 90%）
- [ ] 验证 Trae IDE 重启后 watchdog 自动启动