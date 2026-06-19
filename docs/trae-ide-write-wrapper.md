# Trae IDE Write Wrapper 配置指南

> **目标**：让 Trae IDE 在写文件前自动检查路径，避免 L2 违规

## 🎯 限制说明

**Trae IDE 是外部工具**，我无法直接修改。但可以通过以下方式实现"类似 wrapper"行为：

## 📋 方案 A：Trae IDE settings.json + task hook

### 1. 创建 wrapper task

`.trae/tasks/write-check.json`:
```json
{
  "name": "write-check",
  "trigger": "before-write",
  "command": "python d:/filework/excel-to-diagram/scripts/write_wrapper.py ${file}",
  "onViolation": "block",
  "exitCode": {
    "0": "allow",
    "2": "block-L2"
  }
}
```

### 2. 在 `.vscode/settings.json` 注册

```json
{
  "yaml.schemas": {
    ".trae/specs/**/business-flow.yaml": ".trae/specs/templates/business-flow.schema.json"
  },
  "files.watcherExclude": {
    "**/excel-to-diagram/.git/**": true
  },
  "trae.tasks.write-check.enabled": true,
  "trae.tasks.write-check.command": "python d:/filework/excel-to-diagram/scripts/write_wrapper.py",
  "trae.tasks.write-check.blockOnL2": true
}
```

## 📋 方案 B：File Watcher (Python script 后台跑)

### 启动 file watcher

```powershell
# 启动后台 watcher
Start-Process pythonw -ArgumentList @(
    'd:\filework\excel-to-diagram\scripts\file_watcher.py'
)
```

`scripts/file_watcher.py` (伪代码):
```python
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

MAIN_DIR = Path(r"d:\filework\excel-to-diagram")
ALLOWED = ["docs/violations/", ".agent-violations.json", "scripts/"]

class WriteHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            path = Path(event.src_path)
            if MAIN_DIR in path.parents:
                rel = path.relative_to(MAIN_DIR)
                # Check if allowed
                if not any(str(rel).startswith(a) for a in ALLOWED):
                    print(f"[L2 ALERT] Write to: {rel}")
                    # Record violation
                    record_violation(str(rel))

# Start watching
handler = WriteHandler()
observer = Observer()
observer.schedule(handler, str(MAIN_DIR), recursive=False)
observer.start()

while True:
    time.sleep(60)
```

## 📋 方案 C：Pre-commit Hook（已实施）

**已 merge 到 main**：`.githooks/pre-commit` v3.0.2

**作用**：
- 检查编码 (UTF-8)
- 检查 emoji
- 检查主工作树 commit
- **但只检查 commit，不检查 Write 工具调用**

## 📋 方案 D：Manual Discipline（现实方案）

既然工具层面难实现，**接受 AI agent 现实**：

```
每次回复开头：
  [WORKTREE] Current: xxx
  [TARGET]   写到: xxx
  [CHECK]    ✓ 或 ✗
```

## 🎯 推荐

| 方案 | 适用 | 工作量 |
|------|------|--------|
| **A (settings.json)** | Trae IDE 支持时 | 5 分钟 |
| **B (File Watcher)** | 想实时监控时 | 30 分钟 |
| **C (Pre-commit)** | commit 时检查 | ✅ 已做 |
| **D (Manual)** | 默认 | 0 分钟 |

## 🤝 当前状态

**Trae IDE wrapper 没真正实现**。原因是：
1. Trae IDE 没有暴露 file-write hook API
2. 我无法修改 Trae IDE 内部
3. 写本地替代工具（write_wrapper.py）只能手动调用

**最佳实践**：用本地 `write_wrapper.py` 写前手动跑：
```powershell
python scripts\write_wrapper.py <target_path>
```

## 💡 未来改进

如果 Trae IDE 增加 file-write hook 支持：
- 自动调用 `write_wrapper.py`
- L2 违规时阻止写入
- 显示警告

**TODO**：追踪 Trae IDE 更新日志，看是否支持 file-write hook。

## ✅ 已完成的"伪 wrapper"

1. **`scripts/write_wrapper.py`** - 手动调用版本
2. **`scripts/self_check.py`** - 每次回复前自检
3. **`scripts/violation_auto.py`** - 自动检测
4. **`scripts/monitor_v22.py`** - 持续监控 + 自动记录
5. **`.agent-violations.json`** - 违规跟踪
6. **`docs/violations/L2_*.md`** - 每次违规的反思

**这就是"在没有 IDE 工具支持下的妥协方案"**。