# Agent Status 文件目录

> **V2 新增**：基于 2026-06-20 多 Agent 通信缺失事故。

## 用途

每个 AI Agent 启动时必须创建 `<agent-name>.json`，用于：
1. **多 Agent 互相感知** —— 知道其他 Agent 在做什么
2. **冲突检测** —— 避免两个 Agent 改同一文件
3. **状态监控** —— PM 知道哪个 Agent 卡死/阻塞
4. **故障排查** —— 知道哪个 Agent 出了什么问题

## Schema

```json
{
  "agent_name": "agent-X",
  "task": "fix(v1.2.30) write_scope_interceptor",
  "worktree": "../agent-X-worktree",
  "port": 3010,
  "locked_files": ["meta/core/interceptors/write_scope_interceptor.py"],
  "sandbox_status": "healthy | isolated | deadlock",
  "status": "starting | working | testing | completed | failed",
  "started_at": "2026-06-20T23:30:00Z",
  "last_heartbeat": "2026-06-20T23:35:00Z",
  "last_action": "Implementing _extract_business_key method",
  "blocked_reason": null
}
```

## 使用

```bash
# 1. 初始化
python scripts/agent_heartbeat.py init \
    --agent agent-X \
    --task "fix(v1.2.30)" \
    --port 3010 \
    --lock meta/core/interceptors/write_scope_interceptor.py

# 2. 心跳（每 5 分钟）
python scripts/agent_heartbeat.py heartbeat \
    --agent agent-X \
    --action "Implementing _extract_business_key"

# 3. 状态变更
python scripts/agent_heartbeat.py update \
    --agent agent-X \
    --status testing

# 4. 列出所有 agent
python scripts/agent_heartbeat.py list

# 5. 检查超时
python scripts/agent_heartbeat.py check

# 6. 检测冲突
python scripts/agent_heartbeat.py detect-conflicts \
    --agent agent-X \
    --lock meta/core/foo.py
```

## 心跳超时

- 默认阈值：5 分钟
- 检查方式：`python scripts/agent_heartbeat.py check`
- 超时表示 Agent 卡死或忘记更新心跳

## 沙箱状态

| 状态 | 含义 | 触发 |
|------|------|------|
| `healthy` | 正常 | exit 0 + stdout 正常 |
| `isolated` | 隔离 | exit 7 / stdout 空 / 文件不创建 |
| `deadlock` | 死锁 | ptyHost heartbeat 丢失 |

Agent 必须更新 `sandbox_status` 字段，让 PM 知道是否需要介入。