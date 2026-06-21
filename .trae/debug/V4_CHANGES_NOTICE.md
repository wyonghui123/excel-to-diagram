# V4.0 已应用通知 (2026-06-21)

**Cherry-pick commit**: 9212683 (基于 main d58512a)

## V4.0 关键变化（Agent 必读）

### 1. service_manager.py - 启动方式变了
- **Before (V3)**: `powershell → service_manager.ps1 → pythonw`（5层嵌套，8秒超时失败）
- **After (V4.0)**: 直接 `python -u waitress_server.py`（单层，60秒超时）

**操作影响**：用 `restart_safe.py restart` 现在能真正工作，不需要手动 `Start-Process python`。

### 2. dashboard.py - 加了 STARTING 状态
- **Before**: 端口未监听 → `FAIL (port not listening)`
- **After**: 启动中 < 90秒 → `[i] STARTING (启动中 30s,后端初始化需 30-60s)`

**操作影响**：看到 STARTING 不要慌，等 60 秒会自动变 OK。

### 3. hooks.json - PreToolUse 拦截根目录调试脚本
**禁止**在项目根目录写这些文件：
- `debug_*.py` `analyze_*.py` `query_*.py` `check_*.py` `test_*.py` `inspect_*.py` `tmp_*.py`

**正确位置**：
- `scripts/debug/test_<name>.py`
- `scripts/debug/check_<name>.py`
- `scripts/debug/analyze_<name>.py`
- `scripts/debug/tmp/<name>.py`（避免提交）

### 4. hooks.json - SessionStart 自动启动 watchdog
Trae 新会话启动时会自动检查 + 启动 watchdog + 检查后端。

## 操作建议

```bash
# 1. 验证当前后端
python scripts/debug/restart/restart_safe.py verify

# 2. 如需重启
python scripts/debug/restart/restart_safe.py restart

# 3. 看 dashboard
python scripts/debug/dashboard.py --brief
```

**绝对不要**：
- ❌ `python -c "import subprocess; subprocess.Popen(['powershell', ...])"`（手动启动 powershell 嵌套）
- ❌ 在根目录写 `debug_*.py` / `analyze_*.py` / `test_*.py`（会被 hook 拒绝）
- ❌ 看到 `[X] 后端: FAIL` 就立即调 `restart`（先看是不是 STARTING）