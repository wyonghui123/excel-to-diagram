---
alwaysApply: true
description: 多Agent协作规范 - worktree隔离、端口隔离、沙箱检测、PM授权例外
---
# Multi-Agent 协作规范 (v3.24)

> **多个 AI Coding Agent 并行开发, 测试基础设施需支持端口/DB/env 隔离。**
> **v3.24: 新增 L5 沙箱检测、PM 授权例外、Worktree 生命周期管理。**

## [!!!] 铁律：Agent 必须使用独立 Worktree [!!!]

> **在主工作树中 commit 会导致其他 Agent 的未提交工作被 git stash 回滚！**
>
> **2026-06-15 事故：智能体B commit 触发 git stash，导致智能体A 的 399 个文件丢失。**
>
> **唯一合法方式：启动时执行 `scripts/agent_bootstrap.ps1`**

### 禁止行为

- ❌ **在主工作树执行 `git commit`**（必须先 bootstrap worktree）
- ❌ **在主工作树执行 `git stash`**（会影响其他 Agent 的工作）
- ❌ **两个 Agent 共享同一个 worktree**（必须各自独立）
- ❌ **不设 AGENT_PORT 就跑测试**（默认 3010，跟其他 Agent 冲突）
- ❌ **直接用 `Start-Process` 启 server**（应 service_manager）
- ❌ **`Get-Process python` 判断服务状态**（sandbox 隔离不可靠）

### 强制执行

| 防护层 | 机制 | 效果 |
|--------|------|------|
| **L1: Worktree 强制** | `scripts/agent_bootstrap.ps1` 自动创建 worktree | 根治：文件级零冲突 |
| **L2: Pre-commit Hook** | `.git/hooks/pre-commit` Gate 4 检测主工作树 commit | 兜底：警告未暂存修改 |
| **L3: Post-commit Hook** | `.git/hooks/ai-guard-post-commit.ps1` v2.0 检测 stash 突变 | 告警：stash 数量变化 |
| **L4: Stash 监控** | `scripts/stash_guard.ps1` 定期检查 | 巡检：发现遗漏 |
| **L5: 沙箱检测** | Agent 启动时验证写权限（见下方） | 防止：假成功（exit 0 但未落盘） |

## L5: 沙箱隔离检测

> **2026-06-20 发现：Trae IDE 沙箱可能完全隔离文件系统写入。**
> **Agent 执行 `git commit` 返回 exit 0 但主机 HEAD 不变，`echo > file` exit 0 但文件不存在。**
> **沙箱状态不可预测（同一 session 前半段隔离，后半段可能解封）。**

### Agent 启动时必须验证

```powershell
# Step 1: 写测试文件
$sandboxTest = 'sandbox_check_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.txt'
Set-Content -Path "d:\filework\$sandboxTest" -Value 'sandbox-test' -Encoding UTF8

# Step 2: 验证文件是否真的存在
if (Test-Path "d:\filework\$sandboxTest") {
    Write-Host "[L5] 沙箱已解封：可以写入主机文件系统" -ForegroundColor Green
    Remove-Item "d:\filework\$sandboxTest"
    $env:SANDBOX_ISOLATED = '0'
} else {
    Write-Host "[L5] 沙箱已隔离：无法写入主机文件系统" -ForegroundColor Red
    Write-Host "[L5] 必须使用方案 A（脚本委托模式）让用户执行" -ForegroundColor Yellow
    $env:SANDBOX_ISOLATED = '1'
}
```

### 沙箱隔离时的替代方案

| 方案 | 做法 | 适用场景 |
|------|------|---------|
| **方案 A：脚本委托** | 输出 PowerShell 脚本让用户复制粘贴 | 沙箱隔离 |
| **方案 B：MCP 工具** | 通过 MCP 工具执行（绕过沙箱） | MCP 可用时 |
| **方案 C：等待解封** | 沙箱状态可能动态变化 | 不紧急时 |

### 铁律：沙箱隔离时禁止假成功

- ❌ **沙箱隔离时执行 `git commit`**（exit 0 但未落盘，浪费时间）
- ❌ **沙箱隔离时执行 `git add`**（同上）
- ✅ **沙箱隔离时用 Read/Edit 工具编辑文件**（编辑器 API 不受沙箱影响）
- ✅ **沙箱隔离时输出脚本让用户执行**

## PM 授权例外

> **当 PM（产品经理/用户）明确授权时，可以在主工作树 commit。**
> **条件：无其他 Agent 在同一工作树并发工作。**

### 授权条件（全部满足）

1. PM 明确要求在主工作树 commit（如"请执行"、"commit 到 main"）
2. 无其他 Agent 在同一工作树并发工作（`git worktree list` 确认）
3. commit message 标注 `[pm-authorized]`

### 示例

```powershell
# PM 授权后，在主工作树 commit
cd d:\filework\excel-to-diagram
git add -A
git commit --no-verify -m "fix(xxx): description [pm-authorized]"
```

### 禁止行为（即使 PM 授权）

- ❌ **PM 授权 + 其他 Agent 在同一工作树** → 仍需 worktree
- ❌ **PM 授权 + stash 有其他 Agent 的工作** → 先 stash pop 确认

## Worktree 生命周期管理

> **Worktree 不清理会占用磁盘 + 混淆 git 状态。**

### 生命周期

```
创建 → 开发 → 测试 → commit → push → PR → 合并 → 清理
  ↑                                                ↓
  └────── agent_bootstrap.ps1 ──────┘
```

### 清理时机

| 时机 | 动作 | 谁负责 |
|------|------|--------|
| PR 合并后 | `git worktree remove <path> --force` + `git branch -d <branch>` | 创建者 Agent 或 PM |
| Agent 会话结束 | 清理自己的 worktree | 创建者 Agent |
| 定期巡检 | 检测已合并的 worktree 并清理 | PM 或自动化脚本 |

### 清理前必做

1. **备份 commit hash**（万一要恢复）
   ```powershell
   $hash = git -C <worktree-path> rev-parse HEAD
   Add-Content -Path 'worktree_commits_backup.txt' -Value "$branch -> $hash"
   ```

2. **确认分支已合并**
   ```powershell
   git branch --merged main --list <branch>
   ```

3. **删除 worktree + 分支**
   ```powershell
   git worktree remove <path> --force
   git branch -d <branch>
   ```

### Detached HEAD 处理

| 情况 | 处理 |
|------|------|
| 有 tag 标记 | 安全删除（tag 保留） |
| 无 tag 但有有价值 commit | `git stash branch rescue/<name>` 保存 |
| 无价值 | 直接 `git worktree remove --force` |

## Agent 启动时

```powershell
# [!!!] 必须执行 bootstrap [!!!]
powershell -File scripts/agent_bootstrap.ps1 -AgentName <name> -Port <3010-3019>

# 示例:
powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-A -Port 3010
powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-B -Port 3011
```

bootstrap 会自动：
1. 创建独立 worktree（`../agent-A-worktree/`）
2. 创建独立分支（`agent/agent-A`）
3. 设置 `AGENT_IN_WORKTREE=1` + `AGENT_PORT=3010`
4. 安装依赖（`npm install`）

## 测试时

```bash
# 走 test.py 入口 (合规)
python d:\filework\test.py --single meta/tests/.../test_x.py

# 或用 agent_test.py (推荐给 AI Agent, 含 trace_id + JSON)
python scripts/agent_test.py --single meta/tests/.../test_x.py \
    --port $env:AGENT_PORT --json results.json
```

## 多 Agent 隔离保证

| 资源 | 隔离方式 |
|------|---------|
| **工作树** | `git worktree` 独立目录（L1 强制） |
| **分支** | `agent/<name>` 独立分支 |
| **端口** | `AGENT_PORT` env (3010-3019) |
| **DB** | per-port snapshot (test.py 自动) |
| **Lock** | per-port lock 文件 |
| **Status** | `.service_status_<port>.json` |
| **Trace ID** | UUID, 全局唯一 |

## Agent 提交前

1. `python test.py --single <自己写的测试>` 通过
2. `python d:\filework\test.py --status` 看整体状态
3. 改 `--port` 不影响其他 Agent
4. commit 在自己的 worktree 中进行（不影响其他 Agent）

## Agent 完成后

```bash
# 1. 在 worktree 中 push
cd ../agent-A-worktree
git push origin agent/agent-A

# 2. 创建 PR 或由用户合并
# 3. 清理 worktree
git worktree remove ../agent-A-worktree
```

## Agent 异常时

- 看自己端口的 `.service_status_<port>.json`
- 用 `service_manager.ps1 status -Port <port>` 看
- 检查 `git stash list` 是否有被回滚的工作
- 不影响其他 Agent（worktree 隔离保证）

## 事故复盘 (2026-06-15)

### 事故经过

1. 智能体A 在主工作树编辑文件（未 commit）
2. 智能体B 在同一主工作树执行 `git commit`
3. Git 自动 `git stash`，将智能体A 的工作回滚到 stash
4. `git stash pop` 失败，智能体A 的工作"丢失"
5. 累积 8 个 stash，399 个源代码文件受影响
6. 恢复耗时数小时，8 个冲突文件需手动合并

### 根因

- 两个 Agent 共享同一工作树
- Git 的 `git stash` 机制假设工作树只有一个操作者
- 缺少技术层面的强制约束（规范是"建议"而非"强制"）

### 预防措施

- **L1**: Worktree 强制隔离（本次实施）
- **L2**: Pre-commit Hook 检测主工作树 commit（本次实施）
- **L3**: Post-commit Hook 检测 stash 突变（本次实施）
- **L4**: Stash 监控巡检（本次实施）

## 参考

- `.trae/rules/SESSION_REMINDER.md` - 18 铁律
- `docs/specs/spec-ai-agent-test-infra-v3.17.md` - D.7 详细设计
- `scripts/agent_bootstrap.ps1` - Worktree 引导脚本
- 业界: [Augment Code Multi-agent](https://www.augmentcode.com/guides/agent-observability-for-ai-coding)
- 业界: [STORM: State-Oriented Management](https://arxiv.org/pdf/2605.20563) - 写入时冲突检测
- 业界: [Clash.sh](https://clash.sh/) - Worktree 冲突预测工具
- 业界: [Cursor stash bug report](https://forum.cursor.com/t/cursor-ide-silently-runs-git-stash-git-reset-head-during-active-agent-session-all-uncommitted-changes-lost/156146) - 同类事故
