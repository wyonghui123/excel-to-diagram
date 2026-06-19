# AGENT_GUIDELINES v3.21 (2026-06-19 升级)

> **多 Agent 并行开发铁律**
> **v3.21 新增**：Bug Triage + Hotfix 工作流（发现 bug 怎么办）
> **v3.20 新增**：端口隔离规范（解决"测试哪个版本"问题）

## ⚠️ 你必须知道的 6 件事

1. **必须使用 worktree**（用 `agent_bootstrap.ps1`）
2. **不要碰主工作树**（违反 L2 铁律）
3. **不要碰 stash@{0}**（违反 L3 铁律）
4. **测试用你的端口**（3011-3019，不用 3010）
5. **commit 前必看 spec.md**
6. **发现 bug 立即 triage**（P1/P2/P3/P4）

## 🚀 启动流程（30 秒）

```powershell
# 1. Bootstrap (新 Agent 第一步)
powershell -File scripts/agent_bootstrap.ps1 -AgentName <name> -Port <3011-3019>

# 2. 进入 worktree
cd ../<name>-worktree

# 3. 写 spec.md
cp d:\filework\spec_template.md .\spec.md
# 编辑: 目标/白名单/黑名单/完成标准

# 4. 开发 + commit
```

## 🛡️ 5 条铁律

| 铁律 | 描述 | 违反后果 |
|------|------|---------|
| **L1: Worktree** | 必须用 `agent_bootstrap.ps1` 创建独立 worktree | L1 阻断 |
| **L2: NoMain** | 不要在主工作树 commit/stash/改文件 | L2 阻断 |
| **L3: NoStash0** | 不要碰 stash@{0} | L3 阻断 |
| **L4: Status** | commit 前必看 `.agent-status.json` | L4 阻断 |
| **L5: Port** | 测试用你的端口（3011-3019），不用 3010 | L5 软约束 |

## 🔌 端口隔离（v3.20 新增）

### 核心问题
多 agent 并行开发时，**服务只跑一个版本**（main HEAD），
agent 改的代码在 worktree 里**没办法被测试**（除非违反 L2 在主工作树编辑）。

### 解决方案
每个 agent 用**独立端口**跑自己的服务：

| 端口 | 角色 |
|------|------|
| **3010** | main（生产 / 用户访问） |
| **3011-3019** | agent 工作区（每个 agent 独立） |

### 端口注册
文件：`d:\filework\.coord\ports.json`

### Agent 启动流程
```powershell
# Bootstrap 自动完成:
# 1. 创建 worktree (../<name>-worktree/)
# 2. 创建分支 (<name>-main)
# 3. 分配端口 (3011-3019)
# 4. 创建 .env.agent
# 5. 注册到 .coord/ports.json
```

### 测试时
```powershell
# 用你的端口，不用 main 的 3010
python test.py --port 3011 --single <test_path>
# 浏览器: http://localhost:3005/  (3004 + (port - 3010))
```

### 详细规范
见 [docs/port-isolation.md](file:///d:/filework/excel-to-diagram/docs/port-isolation.md)

## 🐛 Bug Triage（v3.21 新增）

### 核心问题
多 agent 并行开发时，如果发现 bug 影响 main，**不能简单切换分支**：
- 切换分支 = AI 上下文清零 = 重新解释代码库
- 必须在独立 worktree 中做 hotfix

### 决策树（30 秒评估）

```
发现 bug 影响 main
       ↓
   服务挂 / 数据丢失 / 安全问题？
       ├─ YES → P1 Critical → 立即 hotfix（暂停 F1）
       └─ NO ↓
   主流程阻塞？
       ├─ YES → P2 High → Parallel hotfix（不阻塞 F1）
       └─ NO ↓
   仅边缘场景？
       ├─ YES → P3 Medium → Backlog
       └─ NO → P4 Low → Backlog
```

### 工作流速查

| 等级 | 响应时间 | 工作流 |
|------|---------|--------|
| **P1 Critical** | < 15 分钟 | 5 步 hotfix（暂停 F1）|
| **P2 High** | < 1 小时 | 3 步并行 hotfix |
| **P3 Medium** | < 1 天 | 1 步 backlog |
| **P4 Low** | < 1 周 | 1 步 backlog |

### P1 Critical（5 步）

```powershell
# 1. Stash F1 工作
cd <F1-worktree>
git stash push -u -m "F1-WIP"

# 2. 创建 hotfix wt (基于 main)
cd d:\filework\excel-to-diagram
git worktree add -b hotfix/bug-X-2026-06-19 ..\hotfix-bug-X-worktree main

# 3. Fix + test + commit (用端口 3011-3019)
cd ..\hotfix-bug-X-worktree
# ... 写 spec.md, 改代码, 测 ...

# 4. Merge 到 main
cd d:\filework\excel-to-diagram
git merge --no-ff --autostash hotfix/bug-X-2026-06-19

# 5. Rebase F1 + 恢复 stash
cd <F1-worktree>
git rebase main
git stash pop
```

### P2 High（3 步并行）

```powershell
# 1. 创建 hotfix wt (不暂停 F1)
cd d:\filework\excel-to-diagram
git worktree add -b hotfix/bug-X-2026-06-19 ..\hotfix-bug-X-worktree main

# 2. Fix + test + commit (与 F1 并行)
cd ..\hotfix-bug-X-worktree

# 3. F1 完成后: rebase
cd <F1-worktree>
git rebase main
```

### 自动 triage 工具

```powershell
# 交互式 triage (5 个问题, 自动判定 P1-P4)
python scripts/bug_triage.py --interactive

# 查看特定等级的 workflow
python scripts/bug_triage.py --workflow P1

# 列出当前所有 bug
python scripts/bug_triage.py --list
```

### 详细规范
见 [docs/hotfix-workflow.md](file:///d:/filework/excel-to-diagram/docs/hotfix-workflow.md)

### 关键教训

| 错误做法 | 正确做法 |
|---------|---------|
| 在 F1 wt 切换分支 | 创建独立 hotfix wt |
| hotfix 基于 F1 分支 | 基于 main 创建 |
| F1 + bug fix 混在一个 commit | 分离 commit, 分离 wt |
| 用 main 端口 (3010) 测 hotfix | 用 agent 端口 (3011-3019) |
| 跳过 spec.md 直接 hotfix | 始终写 spec.md (即使 hotfix) |

## 📋 启动检查清单

- [ ] 读过本文件（AGENT_GUIDELINES.md）
- [ ] 读过 `.agent-status.json`
- [ ] 读过 `multi-agent-coordination.md` v3.19
- [ ] 读过 `INCIDENT_2026-06-17.md`
- [ ] 执行 `agent_bootstrap.ps1 -AgentName <name> -Port <port>`
- [ ] 创建 `spec.md`（在 worktree 根目录）
- [ ] 在 worktree 中工作（不在主工作树）
- [ ] 用自己的端口测试（不用 3010）

## 🚫 10 条 DO NOT

| # | DO NOT |
|---|--------|
| 1 | ❌ 在主工作树 commit |
| 2 | ❌ 在主工作树 stash |
| 3 | ❌ 碰 stash@{0} |
| 4 | ❌ 不设端口就跑测试 |
| 5 | ❌ 用 main 的 3010 测自己代码 |
| 6 | ❌ 直接用 Start-Process 启 server（用 service_manager）|
| 7 | ❌ Get-Process python 判断服务（sandbox 隔离不可靠）|
| 8 | ❌ 跳过 agent_bootstrap 直接 git worktree add |
| 9 | ❌ 不写 spec.md 就开始开发 |
| 10 | ❌ 不更新 .agent-status.json 就完成 |

## 📚 关键参考

| 文档 | 路径 |
|------|------|
| **本文件** | `AGENT_GUIDELINES.md` (worktree 根目录) |
| 多 Agent 协调规范 v3.19 | `.trae/rules/multi-agent-coordination.md` |
| 18 铁律 | `.trae/rules/SESSION_REMINDER.md` |
| 6/17 事故复盘 | `.trae/rules/INCIDENT_2026-06-17.md` |
| Spec 模板 | `d:\filework\spec_template.md` |
| **端口隔离规范** | `docs/port-isolation.md` |
| **Agent Bootstrap** | `scripts/agent_bootstrap.ps1` |
| 健康基线 tag | `healthy-baseline-2026-06-17` |

## 📊 当前状态（2026-06-19 11:00）

| 资源 | 状态 |
|------|------|
| main HEAD | `9d8fc44` |
| Worktree | 8 个 |
| 健康基线 | `healthy-baseline-2026-06-17` |
| 后端服务 | PID 3996 (3010) |
| 前端服务 | (3004) |
| 监控 | monitor.py v2.1 运行中 |
| 已 merge agents | Agent 1, B, Edit-Tab, Import-Dialog |

## 🆘 出错时

### Agent 启动失败
1. 检查端口冲突：查看 `.coord/ports.json`
2. 检查 worktree 已存在：删除旧 wt 或换名字
3. 检查磁盘空间

### 端口被占用
1. `netstat -ano | findstr :3010` 看占用进程
2. 用 `-Port` 选其他端口

### pre-commit hook 拒绝
1. 看错误信息（Gate 1-7）
2. Gate 5 = 缺 spec.md → `cp spec_template.md ./spec.md`
3. Gate 6 = commit message 缺铁律 → 加 L1/L2/L3/L4/L5
4. Gate 7 = 改动文件不在白名单 → 编辑 spec.md 白名单

### 服务挂了
1. **不要**直接重启！可能其他 agent 在用
2. 检查 `.service_status_<port>.json`
3. 用 `service_manager.ps1 status -Port <port>`

---

**v3.20 升级日期**：2026-06-19
**关键变化**：端口隔离规范（解决"测试哪个版本"问题）