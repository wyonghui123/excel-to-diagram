---
alwaysApply: false
title: Development Workflow — v4.0 主仓工作流
last_updated: 2026-09-01
status: 活跃
version: v4.0
based_on: 09-01 治理经验
---

# Development Workflow — v4.0 主仓工作流（基于 09-01 治理经验）

> 状态: 活跃
> 适用范围: 所有开发智能体 (dev-agent) + e2e agent + 协调智能体
> 触发条件: 任何 BUG / 需求 / 改动
> 与本文件配套: `worktree-governance.md`, `release-sync-workflow.md`, `multi-agent-coordination.md`

> **v4.0 重要变更（2026-09-01 治理后）**
> - 🟢 主仓作为**共享工作面**而非禁地
> - 🟢 pre-commit 主仓 commit 从"硬阻断"改为"劝用 stash"
> - 🟢 worktree 寿命强制 ≤ 7 天
> - 🟢 新增 commit 频率铁律（**禁止半成品 worktree 切换**）
> - 🟢 新增"两端对齐"步骤（merge 后必须核对祖先链）

---

## 1. 角色与职责

| 角色 | 主要工作 | 不做 |
|---|---|---|
| **开发智能体** (dev-agent) | 写代码 + 单测 + commit | 不在主工作树脏 commit，不动 main 服务，不 push 到 release |
| **e2e agent** | 在 integration 跑 e2e 测试 | 不动 main 服务，不做产品决策 |
| **协调智能体** (coordinator) | cherry-pick + 基础设施 + 同步 integration | 不写业务代码，不做产品验收 |
| **PM** (您) | 业务决策 + main 人工验证 | 不直接改 git，不直接重启服务 |

---

## 2. [v4.0 核心] 工作面选择决策树

> **这是 v4.0 与 v3.x 的最大区别**——根据任务复杂度选工作面，不再默认"必须独立 worktree"。

```
任务来了，先问 3 个问题：
1. 这个任务多久能完成？   (< 2 小时 / 半天 / > 1 天)
2. 涉及几个文件？         (< 5 / 5-20 / > 20)
3. 是否跟其他 agent 工作交叉？ (是 / 否)
```

| 任务画像 | 推荐工作面 | 寿命 |
|---|---|---|
| **小修小补**（< 2h, < 5 文件, 不交叉） | **主仓 release/integrated-main** | 立即 commit |
| **典型 bugfix**（半天, 5-20 文件） | **主仓**（共享工作面） | 当天 commit |
| **跨模块 feature**（> 1 天, > 20 文件） | **新 worktree** + 短分支 | ≤ 7 天 |
| **大型重构**（多 agent 协作） | **多 worktree**（每个 agent 1 个） | ≤ 14 天 |
| **实验性**（可能丢弃） | **新 worktree** + `exp/*` 分支 | ≤ 3 天 |

> **关键变化**：v3.x 的"L1 Worktree"铁律在 v4.0 改为 **"按任务画像选择工作面"**。简单 bug 在主仓就地修，避免不必要的 worktree 漂移。

---

## 3. 主仓作为共享工作面（v4.0 新设计）

### 3.1 主仓的定位

```
主仓 release/integrated-main = 项目真相之源（single source of truth）
- 90% 的小修小补在这里发生
- 立即 commit, 不留尾巴
- 永远脏 commit 是禁止的（铁律 L2-NoDirtyMain）
```

### 3.2 何时 *不* 用主仓

- 多 agent 同时改同一个文件（必须 worktree 隔离）
- 实验性改动（避免污染主仓 history）
- 超过 1 天无法收尾（避免 worktree 寿命超标）

### 3.3 主仓 commit 铁律

| 铁律 | 内容 |
|---|---|
| **L1-L4** | 项目原有 4 层防护（worktree/stash/post-commit/沙箱检测）继续生效 |
| **L2-NoDirtyMain（v4.0 升级）** | 主仓**禁止** commit 时有 untracked 文件 + 未暂存 modified |
| **L7-CommitFrequency（v4.0 新增）** | 主仓切出会话前必须 commit / stash，**禁止留半成品** |

### 3.4 主仓 commit 流程

```bash
# 主仓脏文件必须 100% 处理后才能 commit
git status --short
# 必须看到 0 行输出（或者全部 staged）

# 1) 文件分类
git add <可入库的文件>      # 真实代码/文档/工具
# 探针文件：移入 tools/_scratch/ 后 git add
# 临时文件：直接删除
# 真正的工具脚本：git add 入库

# 2) commit
git commit -m "..."

# 3) 验证
git log --oneline -1   # 或 Read .git/logs/HEAD
```

---

## 4. [v4.0 新增] Worktree 治理与寿命铁律

> 完整规范见 [worktree-governance.md](./worktree-governance.md)

### 4.1 寿命红线

| 级别 | 寿命上限 | 处置 |
|---|---|---|
| **L1 短期分支** | 48 小时 | 不开 worktree，直接 in-place |
| **L2 feature branch** | 7 天 | 必须 worktree，到期必须收尾 |
| **L3 实验** | 3 天 | `exp/*` 命名，必须带 expiry reason |
| **L4 多 agent 协作** | 14 天 | 必须有合并时间表 |

### 4.2 切换会话前必做

| 选择 | 何时 | 怎么用 |
|---|---|---|
| ✅ commit | 改动稳定 | `git commit` 后关闭 |
| ✅ stash | 短期保留 | `git stash push -m "wip-XXX"` 记录原因 |
| ✅ revert | 改动错误 | `git checkout -- <files>` |
| ❌ **半成品** | 留有 dirty 但没 commit/stash | **禁止！** |

### 4.3 清理 worktree 必做

```
清理前必须保留 commit hash（防丢）：
1. 备份 commit: git rev-parse HEAD > worktree_commits_backup.txt
2. 确认已合并: git branch --merged main --list <branch>
3. 删除 worktree: git worktree remove <path> --force
4. 删除分支: git branch -D <branch>
5. 验证: Read .git/refs/heads/<branch> 应不存在
```

---

## 5. 开发智能体流程（v4.0 修订）

### 5.1 工作面选择

```
Step 1: 评估任务画像（用 §2 决策树）
Step 2: 选定工作面
   - 小修小补 → 主仓
   - 大型 feature → worktree (pwsh -File scripts/agent_bootstrap.ps1 -BugId <ID>)
```

### 5.2 主仓模式（小修小补）

```yaml
in-worktree: D:\filework\excel-to-diagram  (主仓)
branch: release/integrated-main
base: release/integrated-main

rules:
  - 修改 spec.md 加 changelog
  - 跑单测: python test.py --single <test_name>
  - 跑 typecheck: pnpm typecheck
  - 不留 untracked 文件
```

### 5.3 Worktree 模式（大型 feature）

```yaml
in-worktree: D:\filework\worktree-<ID>
branch: fix/<ID>-<short-name>   # 或 feat/<feature-name>
base: release/integrated-main

rules:
  - 寿命 ≤ 7 天
  - 每 1 天 rebase 一次主仓
  - 收尾必须 merge / discard 二选一
```

### 5.4 commit 信息（v4.0 强制格式）

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

根因: ...
修法: ...

L1-Worktree: yes/no (是否在独立 worktree)
L2-NoMain: yes (在 <branch> 分支)
L3-Stash: no (未碰 stash)
L4-SpecMd: yes (已加 changelog)
L7-CommitFrequency: ok (本次 commit 频率合规)
EOF
)"
```

### 5.5 push 与通知

```bash
# push 到 origin (让协调智能体 fetch)
git push -u origin fix/<ID>-<short-name>

# 通知 PM / 协调智能体
# 1. 更新 DEPLOY_HANDOVER_BUG_<ID>.md §9
# 2. 通知协调智能体（如果有 e2e 阶段）
```

---

## 6. e2e agent 流程

> 与 v3.x 相同，保持不变

详见原 §3。

---

## 7. 协调智能体 cherry-pick 流程

> 与 v3.x 相同

详见 [release-sync-workflow.md](./release-sync-workflow.md)

### 7.1 [v4.0 新增] 两端对齐铁律

> **2026-09-01 事故根因**：merge 时手工挑拣丢了 CSS / useDiagramData

```
merge / cherry-pick 后必须做两端对齐：
1. git log --oneline release/integrated-main..<merged_branch> -n 20
   → 列出被合入的 commits，确认每条都已落库
2. 对每个关键功能，找一个特征字符串，grep 主仓确认存在
3. 用 git log -S<特征字符串> 确认历史 commit 含这个改动
4. 如果发现 "should be in main but isn't" → 立刻补 commit，不要 merge forward
```

---

## 8. PM 验证流程

> 与 v3.x 相同

---

## 9. [v4.0 铁律总览] 硬约束

| # | 铁律 | v4.0 内容 |
|---|---|---|
| **L1** | Worktree 选择 | 按任务画像（§2），不强制必须 worktree |
| **L2** | No Dirty Main | 主仓 commit 前必须有 0 dirty 文件 |
| **L3** | No Stash Other | 禁止 stash 别人的工作（原有） |
| **L4** | Spec.md | modified_files 必须列在 spec.md（原有） |
| **L5** | No Direct Push Release | 开发智能体不直接 push release（原有） |
| **L6** | No Touch Main Service | 禁止动主服务（原有） |
| **L7** | Commit Frequency | 主仓切出会话前必须 commit / stash，**禁止半成品** |
| **L8** | Worktree Lifetime | worktree 寿命 ≤ 7 天，超期自动巡检清理 |
| **L9** | Two-End Alignment | merge 后必须两端对齐（§7.1） |

---

## 10. 故障排查（v4.0 新增）

### Q1: 主仓脏文件太多不知道怎么分类？

```
按三类处理：
- 真实代码/文档/工具 → git add
- 探针文件 → mv 到 tools/_scratch/ (不入库但保留备份)
- 临时文件 (.log/.tmp/.bak) → 直接删除

如果还有疑问，写一行 description 到 .git/main_commit_reason 说明本次 commit 的依据
```

### Q2: worktree 寿命超 7 天怎么办？

```
立即评估：
- 已完成 → 收尾 merge/rebase/discard
- 未完成 → 写理由到 worktree 目录的 TODO.md, 申请 PM 延期
- 已废弃 → 删除 worktree + 分支, hash 用 wt-guard tag 保护
```

### Q3: merge 后发现内容丢失？

```
按 §7.1 两端对齐排查：
1. 用 git log -S<特征字符串> 找历史上谁引入
2. 检查那个 commit 是否在主仓祖先链上
3. 如果不在 → 立刻 cherry-pick 补回
4. 写 P0 事故复盘文档
```

### Q4: 主仓 commit 被 pre-commit 阻断？

```
v4.0 设计：pre-commit 不再 hard-fail, 而是劝用 stash：
- 有脏文件 → pre-commit 自动 git stash + 提示
- 没有脏文件 → 正常 commit

如果被阻断（非 v4.0 版本）：
1. 检查 .git/main_commit_reason 是否已写
2. 确认没有其他 agent 在并发工作（git worktree list）
3. PM 明确授权后用 --no-verify 绕过
4. commit 信息必须标注 [pm-authorized]
```

---

## 11. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-09-01 | AI Assistant (治理 agent) | **v4.0**: 主仓作为共享工作面 / worktree 寿命 7 天 / commit 频率铁律 / 两端对齐 / 删 12 个僵尸 worktree + 6 stash |
| 2026-07-04 | AI Assistant (协调智能体) | v3.3 创建, 整合 PM 视角的工作流定义 |