---
alwaysApply: false
description: "AI 检测到多 Agent 并行开发、端口隔离冲突、worktree 跨会话访问、沙箱状态机异常、Agent 心跳缺失或需要协调其他智能体时查阅此规则。13 条铁律 + 沙箱状态机 + Agent Status + L6 跨 wt 保护。"
---

# Multi-Agent 协作规范 (v4.0)

> **合并版本**：原 multi-agent-coordination.md (392) + multi-agent-infrastructure-v20260620.md (293) + v2.md (648) → 本文件
> **合并日期**：2026-09-02
> **触发条件**：多 agent 并行开发 / 端口隔离 / worktree 管理 / 沙箱检测

---

## 🚨 TL;DR - 30 秒必读

### 13 条铁律（5+7+1）

#### 修复完整性（V1 原 5 条）

| # | 铁律 | 触发 |
|---|------|------|
| 1 | **改类签名 → grep 所有调用方** | 修改 `__init__` / `class XXX` |
| 2 | **小步快跑 commit** | 类签名/helper/调用方/测试分开 commit |
| 3 | **修复 + 测试 + 通过 → 才 commit** | 写完代码立即跑测试 |
| 4 | **Working tree ≤ 5 个未提交文件** | `git status --short \| wc -l > 5` 必须先 commit |
| 5 | **明确 WIP 标记** | 未完成用 `# [WIP]` + `TODO` |

#### 沙箱 / 工具 / Agent Status（V2 新增 7 条）

| # | 铁律 | 触发 |
|---|------|------|
| 6 | **Read-First 工作流** | 沙箱隔离时**禁用 RunCommand**，必须用 Read/Write/Edit |
| 7 | **工具降级顺序** | 正常：RunCommand → Edit → Read；隔离：Read → Write → Edit |
| 8 | **Agent Status 强制心跳** | 启动写 `.trae/agents/<name>.json`，每 5 分钟更新 |
| 9 | **沙箱状态机感知** | 启动 + 每 10 分钟检测（见 `scripts/check_sandbox_status.py`）|
| 10 | **多 Agent 互相感知** | 启动前读 `.trae/agents/*.json` 了解其他 agent |
| 11 | **沙箱恢复自动检测** | 监控 `sbox_sdk_*.log` line 20 exit code |
| 12 | **修复完整性自动检查** | `scripts/check_fix_completeness.py` |

#### 元反馈（V2.1 新增 1 条）

| # | 铁律 | 触发 |
|---|------|------|
| 13 | **决策日志强制** | 任何规则边界判断前必须记录理由+替代方案 |

---

## 沙箱状态快速判断

```
[healthy]   exit 0 + stdout 正常 → 可用 RunCommand
[isolated]  exit 7 + stdout 空   → 立即切 Read-First
[deadlock]  ptyHost heartbeat 丢 → 重启 Trae IDE（仅此一态该重启）
[blocked]   执行前就失败 + exit -1 → 换 Shell 工具通道，重启无效
```

> **[!] 2026-10-22 补：第 4 态 `blocked`（终端通道故障）**
> 报错 `Toolhost terminal commands must be routed through the agent runtime`：
> 命令**执行前**即被拒（0–2ms，shell 从未创建），退出码 `-1`，与命令内容无关。
> 根因是 `RunCommand` 工具已退役、当前构建不再产生 agent runtime 路由，**不是沙箱问题**。
> **重启 IDE 无效**（已实测）。处置：查 `ALL_TOOLS` 找 `Shell` 工具并换通道。
> 完整诊断与处置 → [terminal-channel-failure.md](../8-meta-trae/terminal-channel-failure.md)

---

## 一、核心铁律（L1-L5 worktree + 多 agent 基础）

### L1: 必须独立 Worktree

> **在主工作树 commit 会导致其他 Agent 的未提交工作被 git stash 回滚！**
> **2026-06-15 事故：智能体 B commit 触发 git stash，导致智能体 A 的 399 个文件丢失。**

**唯一合法方式**：`scripts/agent_bootstrap.ps1`

**禁止**：
- ❌ 在主工作树执行 `git commit`
- ❌ 在主工作树执行 `git stash`
- ❌ 两个 Agent 共享同一个 worktree
- ❌ 不设 `AGENT_PORT` 就跑测试（默认 3010）
- ❌ 直接用 `Start-Process` 启 server（应 service_manager）
- ❌ `Get-Process python` 判断服务状态（sandbox 不可靠）

### L2-L4: 防护层

| 防护层 | 机制 | 效果 |
|--------|------|------|
| **L1** | `agent_bootstrap.ps1` 自动创建 worktree | 文件级零冲突 |
| **L2** | Pre-commit Hook 检测主工作树 commit | 兜底警告 |
| **L3** | Post-commit Hook 检测 stash 突变 | 告警 |
| **L4** | Stash 监控巡检 | 巡检遗漏 |

### L6: 跨 Worktree 分支保护（v3.26 紧急修复）

> **2026-07-22 phase13-worktree 被未知操作 reset 到 release-prep commit**
> 协调/部署智能体的 `git reset / git checkout` **只能作用于自己的 wt**

**防护层**：
| 防护层 | 机制 | 工具 |
|--------|------|------|
| L6.1 | immutable tag `wt-guard-<wt-name>` 记录安全 HEAD | `_wt_branch_guard.py snapshot` |
| L6.2 | 启动前自动检查 HEAD 是否匹配快照 | `_wt_branch_guard.py check <wt>` |
| L6.3 | Drift 检测告警 + 一键 restore | `_wt_branch_guard.py check + restore` |
| L6.4 | 操作前强制验证 wt 归属 | `_wt_branch_guard.py list` |

**强制流程**：
```bash
# Agent 启动后
python scripts/_wt_branch_guard.py snapshot
python scripts/_wt_branch_guard.py check <wt-name>

# 协调/部署智能体操作前
python scripts/_wt_branch_guard.py list | grep <wt-name>

# Drift 恢复
python scripts/_wt_branch_guard.py restore <wt-name>
```

---

## 二、沙箱铁律（L6-L12，沙箱 + 工具 + Agent Status）

### 铁律 6: Read-First 工作流（沙箱隔离时）

```
Step 1: Read 工具定位文件（绝对路径）
Step 2: Read 工具读取内容
Step 3: Edit 工具修改
Step 4: Read 工具反向确认
Step 5: （必须时）输出 PowerShell 脚本给用户
```

**禁止**：❌ RunCommand / Glob / LS / `echo > file`

### 铁律 7: 工具降级顺序

```python
# scripts/check_sandbox_status.py 检测结果
if status == 'isolated':
    tool_priority = ['Read', 'Write', 'Edit', 'Grep', 'TodoWrite']
elif status == 'deadlock':
    tool_priority = ['Read', 'Edit', 'TodoWrite']
else:  # healthy
    tool_priority = ['RunCommand', 'Edit', 'Read', 'Grep', 'Write', 'TodoWrite']
```

### 工具能力分级矩阵

| 工具 | 沙箱正常 | 沙箱隔离 | 备注 |
|------|---------|---------|------|
| **Read** | ✅ | ✅ | **最稳定**，沙箱坏时优先 |
| **Write** | ✅ | ✅ | 替代 `echo > file` |
| **Edit** | ✅ | ✅ | 替代 `sed -i` |
| **Grep** | ✅ | ⚠️ | 受沙箱间接影响 |
| **TodoWrite** | ✅ | ✅ | 完全独立 |
| **Glob/LS** | ✅ | ❌ | 沙箱坏时可能 ENOENT |
| **RunCommand** | ✅ | ❌ 假成功 | exit 0 但无效 |
| **Shell** | ✅ | ✅ | **2026-10-22 起当前构建实际挂载的终端工具**，走 toolhost 原生通道；RunCommand 失效时用它兜底 |

### 铁律 8: Agent Status 强制心跳

**文件位置**：`.trae/agents/<agent-name>.json`

**Schema**：
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
  "last_action": "Implementing _extract_business_key",
  "blocked_reason": null
}
```

**强制**：启动时创建 / 每 5 分钟心跳 / 状态变更更新

### 铁律 9: 沙箱状态机感知

`scripts/check_sandbox_status.py` 三重检测：
1. 写测试 + Read 反向验证
2. RunCommand 退出码 + stdout
3. sbox_sdk 日志 line 20 exit code

### 铁律 10: 多 Agent 互相感知

```python
for status_file in glob('.trae/agents/*.json'):
    other_agent = read_json(status_file)
    if other_agent.locked_files & my_locked_files:
        raise ConflictError(f"文件被 {other_agent.agent_name} 锁定")
```

### 铁律 11: 沙箱恢复自动检测

每 10 分钟监控 `sbox_sdk_*.log`：
- `exit code 0` 持续 3 次 → 沙箱恢复
- `exit code 7` → 隔离

### 铁律 12: 修复完整性自动检查

`scripts/check_fix_completeness.py` 检测：
1. raise site 调用的方法都已实现
2. 类签名新参数在所有调用方都已更新
3. helper 方法有完整实现（不是 stub）
4. 相关测试都已更新

### 铁律 13: 决策日志强制

```bash
python scripts/decision_log.py violate \
    --agent agent-X --rule "L1 Worktree" --rule-id iron-1 \
    --reason "单文件小修改" --alternatives "使用 worktree" \
    --risk low --pm-authorized
```

3 大原则：
1. 理由必须充分（"风险低"不算理由）
2. 替代方案必须列出
3. PM 授权阈值：5+ 次触发规则体检

---

## 三、强化版 Agent 启动流程（6 步）

```
Step 0: 沙箱检测（check_sandbox_status.py）         ← V2 新增
Step 1: Agent Status 初始化（.trae/agents/X.json）  ← V2 新增
Step 1.5: 多 Agent 感知（读其他 agent status）        ← V2 新增
Step 2: Worktree 创建（agent_bootstrap.ps1）         ← 已有
Step 3: 端口分配（AGENT_PORT=3010-3019）
Step 4: 声明任务范围（locked_files + task）
```

**bootstrap 自动完成**：
1. 创建独立 worktree（`../<agent>-worktree/`）
2. 创建独立分支（`agent/<name>`）
3. 设置 `AGENT_IN_WORKTREE=1` + `AGENT_PORT=3010`
4. 安装依赖（`npm install`）
5. v3.3.6 新增：必须跑 `_sync_precommit.py <wt-name>` 安装 pre-commit 钩子

```powershell
powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-A -Port 3010
python scripts/_sync_precommit.py agent-A-worktree  # v3.3.6 必跑
```

---

## 四、Worktree 生命周期管理

> **完整规范见 `worktree-governance.md`**（v4.0）

```
创建 → 开发 → 测试 → commit → push → PR → 合并 → 清理
```

### 清理时机

| 时机 | 动作 | 谁负责 |
|------|------|--------|
| PR 合并后 | `git worktree remove` + `git branch -d` | 创建者 Agent / PM |
| Agent 会话结束 | 清理自己的 worktree | 创建者 Agent |
| 定期巡检 | 检测已合并的 worktree 并清理 | PM / 自动化 |

### 清理前必做

1. **备份 commit hash**：`git rev-parse HEAD`
2. **打 wt-guard tag**：`git tag wt-guard-<name> <commit>`
3. **确认分支已合并**：`git branch --merged main`
4. **删除 worktree + 分支**

---

## 五、多 Agent 隔离保证

| 资源 | 隔离方式 |
|------|---------|
| **工作树** | `git worktree` 独立目录（L1 强制） |
| **分支** | `agent/<name>` 独立分支 |
| **端口** | `AGENT_PORT` env (3010-3019) |
| **DB** | per-port snapshot (test.py 自动) |
| **Lock** | per-port lock 文件 |
| **Status** | `.service_status_<port>.json` |
| **Trace ID** | UUID，全局唯一 |

---

## 六、Agent 提交前

1. `python test.py --single <自己写的测试>` 通过
2. `python d:\filework\test.py --status` 看整体状态
3. 改 `--port` 不影响其他 Agent
4. commit 在自己的 worktree 中进行

### v3.3 自验证（BUG 修复必做）

```bash
python scripts/self_verify.py run <wt-name>

# 或分步
python scripts/_wt_service.py start-be <wt-name>
python scripts/_wt_service.py start-fe <wt-name>  # 如有前端改动
python scripts/self_verify.py smoke <wt-name>
python scripts/_wt_service.py stop <wt-name>
```

**铁律**：HANDOVER 无 SELF_VERIFY_RESULTS = 无效，协调 reject
详见 `docs/AGENT_INFRA.md` §0.10

---

## 七、Agent 角色分工（5 角色）

| 角色 | 职责 | 工具 |
|------|------|------|
| **Fixer** | 实现修复 | Edit / Write |
| **Tester** | 写测试 + 跑测试 | pytest / test.py |
| **Reviewer** | 验证修复完整性 | git diff + grep |
| **PM** | 合并 worktree → main | git merge |
| **Cleanup** | 清理 stash / worktree | git stash drop / worktree remove |

**工作流**：
```
Fixer → Tester → Reviewer → PM → Cleanup
 ↑                              ↓
 └──── 测试失败 ────────────────┘
```

---

## 八、Agent 启动时 / 完成时 / 异常时

### 启动时
- 见 §三 6 步强制流程

### 完成时
```bash
cd ../agent-A-worktree
git push origin agent/agent-A
# PR 或 PM 合并
git worktree remove ../agent-A-worktree
```

**PM 验证门控**：v3.3 强制 PM 在 release-prep (3006/3011) 签字确认

### 异常时
- 看 `.service_status_<port>.json`
- 用 `service_manager.ps1 status -Port <port>` / `_wt_service.py status <wt>`
- 检查 `git stash list`
- **不影响其他 Agent**（worktree 隔离保证）

---

## 九、PM 授权例外

> **当 PM 明确授权时，可以在主工作树 commit。**

### 授权条件（全部满足）
1. PM 明确要求（"请执行"、"commit 到 main"）
2. 无其他 Agent 并发工作（`git worktree list` 确认）
3. commit message 标注 `[pm-authorized]`

### 禁止（即使 PM 授权）
- ❌ PM 授权 + 其他 Agent 同一工作树 → 仍需 worktree
- ❌ PM 授权 + stash 有其他 Agent 工作 → 先 stash pop 确认

---

## 十、调试事故双链（2026-06-21）

### 事故 A：调试旧代码 3 小时
- Agent 不知道后端跑旧代码，反复调试 3+ 小时
- **解决**：`scripts/debug_backend.py` Step 3 检测代码版本 vs 后端启动时间

### 事故 B：旧 python.exe 进程残留 1+ 小时
- `restart_backend.py` 只杀 `pythonw.exe`，不杀 `python.exe`
- **解决**：`service_manager.py` 新增 `_kill_all_backend_processes()`

---

## 十一、参考

- **Worktree 治理 v4.0**：`worktree-governance.md`（寿命 + commit 频率）
- **开发工作流 v4.0**：`development-workflow.md`
- **SESSION_REMINDER**：4 大铁律 + 调试工具集
- **脚本**：`.trae/scripts/`（11 个 v3.3 脚本）

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-10-22 | v4.1 | **沙箱状态机补第 4 态 `blocked`（终端通道故障）**：RunCommand 已退役 / 重启 IDE 无效 / 改用 `Shell` 通道；工具能力矩阵补 `Shell` 行 |
| 2026-09-02 | v4.0 | **合并 V1+V2+coordination → 本文件（1333 → 550 行）** |
| 2026-08 | v3.26 | L6 跨 wt 保护（phase13-worktree reset 事故） |
| 2026-07-18 | v3.3 | 自验证 + PM Gate + Integration 按需 |
| 2026-06-21 | v3.25 | 沙箱状态机 + Agent Status + Read-First |
| 2026-06-20 | v3.24 | 5 层防护 L1-L4 + 沙箱检测 + Worktree 生命周期 |
| 2026-06-15 | v3.23 | 399 文件丢失事故 → L1 Worktree 强制 |