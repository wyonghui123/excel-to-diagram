# 端口隔离规范 (v1.0, 2026-06-19)

> **目的**：解决多 agent 并行开发时"测试哪个版本"的问题。
> **核心原则**：每个 agent 用独立端口跑自己的服务，互不干扰。

## 端口分配表

| 端口范围 | 角色 | 用途 | 数量 |
|---------|------|------|------|
| **3010** | main (生产) | 用户访问的稳定版本 | 1 个 |
| **3011-3019** | agent 工作区 | 每个 agent 独立测试 | 最多 9 个 |

### 完整分配

| 端口 | 角色 | 用途 |
|------|------|------|
| 3004 | Vite main | main 前端 |
| 3010 | Waitress main | main 后端 |
| 3011 | agent-A | agent-A wt 服务 |
| 3012 | agent-B | agent-B wt 服务 |
| 3013 | agent-C | agent-C wt 服务 |
| 3014 | agent-D | agent-D wt 服务 |
| 3015 | agent-E | agent-E wt 服务 |
| 3016 | agent-F | agent-F wt 服务 |
| 3017 | agent-G | agent-G wt 服务 |
| 3018 | agent-H | agent-H wt 服务 |
| 3019 | agent-I | agent-I wt 服务 |

## 前端端口 = 3004 + (后端端口 - 3010)

例如：
- 后端 3011 → 前端 3005
- 后端 3012 → 前端 3006

## Agent 启动流程

```powershell
# 1. Bootstrap (创建 worktree + 分配端口 + 创建 .env.agent)
powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-A -Port 3011

# 2. 进入 worktree
cd ../agent-A-worktree

# 3. 安装依赖
npm install

# 4. 写 spec.md
cp d:\filework\spec_template.md .\spec.md
# 编辑 spec.md (目标/白名单/完成标准)

# 5. 开发
# ... 在 worktree 中改代码 + commit ...

# 6. 测试 (用你的端口!)
python test.py --port 3011 --single <your_test>
# 浏览器: http://localhost:3005/

# 7. 完成后通知协调者 merge
```

## 端口注册机制

文件：`d:\filework\.coord\ports.json`

格式：
```json
{
  "allocated": {
    "3011": {
      "owner": "agent-A",
      "role": "agent-worktree",
      "status": "active",
      "worktree": "D:/filework/agent-A-worktree",
      "branch": "agent-A-main",
      "allocated_at": "2026-06-19T11:00:00+08:00"
    }
  },
  "reserved": {
    "3010": {
      "owner": "main",
      "role": "production",
      "status": "running"
    }
  }
}
```

## 铁律（端口相关）

| 铁律 | 描述 |
|------|------|
| **L5** | 服务跑在主工作树 (3010)；Agent 测试必须用自己端口 (3011-3019) |
| **禁止** | 在 main 工作树编辑代码（即使"为了让后端加载新代码"）|
| **禁止** | Agent 测试时占用 main 的 3010 端口 |
| **必须** | 用 `agent_bootstrap.ps1` 启动，禁止手动创建 worktree |

## 监控

`monitor.py` 自动检测：
- 端口冲突（多个 agent 试图占用同一端口）
- agent 端口无服务（agent 启动后没启动服务）
- main 端口被非 main 进程占用

## 故障排查

### Q: Agent 改了代码，但测试还是 main HEAD 的代码
A: 检查是否在 worktree 中启动服务（端口 3011+），不要用 main 的 3010。

### Q: 端口被占用
A: 检查 `.coord/ports.json`，找空闲端口（3011-3019）。

### Q: Agent 完成了，怎么通知 merge
A: 更新 `.agent-status.json` 中自己的 status = "ready_to_merge"。

## 历史教训

**2026-06-18 事故**：Agent 1 因为"当前运行的 backend 读取主工作树代码"，违反 L2 铁律在主工作树编辑了 3 个核心文件，导致后续 merge 时 43 个 M 文件污染。

**根本原因**：没有端口隔离，agent 只能通过主工作树测自己的代码。

**本规范的目的**：消除这个根本原因。