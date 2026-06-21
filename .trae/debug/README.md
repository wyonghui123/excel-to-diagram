# Debug Sessions & Snapshots

> **V1 调试基础设施**（v2026.06.21）

## 目录用途

| 目录 | 用途 |
|------|------|
| `sessions/` | 调试会话记录（手动 YAML）|
| `snapshots/` | 用户上下文快照（脚本生成）|

## Sessions

每个调试会话一个 YAML 文件，命名：`session-YYYYMMDD-NNN.yaml`

模板：[`sessions/template.yaml`](./sessions/template.yaml)

## Snapshots

由 `scripts/debug/inspect/user_context.py --save` 自动生成。

格式：`{username}-{timestamp}.json`

## 使用方式

### 1. 调试开始时创建会话

```bash
cp .trae/debug/sessions/template.yaml .trae/debug/sessions/session-$(date +%Y%m%d-%H%M%S).yaml
```

### 2. 收集用户快照

```bash
python scripts/debug/inspect/user_context.py TEST333 --save
```

### 3. 调试完成后填写会话记录

```yaml
# 编辑 sessions/session-20260621-001.yaml
session_id: session-20260621-001
started_at: 2026-06-21T02:00:00Z
# ... 详见 template.yaml
```

## 自动化（待实施）

- `scripts/debug/sessions/auto_record.py` - 自动从 Agent 上下文生成会话
- 集成到 debug_backend.py / debug 启动流程

---

_本目录由 V1 调试基础设施建立（2026-06-21）_