# 项目开发工作流 v4.0（备份版）

> ⚠️ **这是项目开发工作流的快照**。正式版在 `d:\filework\.trae\rules\development-workflow.md`
> 本文件作为项目知识库备份，定期同步。

详见：`d:\filework\.trae\rules\development-workflow.md`（v4.0 全文）

---

## v4.0 核心要点（摘要）

### 工作面选择决策树

| 任务画像 | 推荐工作面 | 寿命 |
|---|---|---|
| 小修小补（< 2h, < 5 文件） | **主仓 release/integrated-main** | 立即 commit |
| 典型 bugfix（半天, 5-20 文件） | **主仓** | 当天 commit |
| 跨模块 feature（> 1 天） | 新 worktree + 短分支 | ≤ 7 天 |
| 实验性 | 新 worktree + `exp/*` | ≤ 3 天 |

### v4.0 铁律总览

| # | 铁律 | 内容 |
|---|---|---|
| L1 | Worktree 选择 | 按任务画像，**不强制必须 worktree** |
| L2 | No Dirty Main | 主仓 commit 前必须有 0 dirty 文件 |
| L3 | No Stash Other | 禁止 stash 别人的工作 |
| L4 | Spec.md | modified_files 必须列在 spec.md |
| L5 | No Direct Push Release | dev-agent 不直接 push release |
| L6 | No Touch Main Service | 禁止动主服务 |
| **L7** | **Commit Frequency** | **主仓切出会话前必须 commit / stash，禁半成品** |
| **L8** | **Worktree Lifetime** | **≤ 7 天，超期自动巡检清理** |
| **L9** | **Two-End Alignment** | **merge 后必须两端对齐** |

### 2026-09-01 治理成果

- Worktree: 14 → **1**
- 分支: 14 → **1**
- Stash: 6 → **0**
- 本次 commit: **5** (3b76fe0/222c642/6f3820c/fd57fac/a82e415)

详见：`docs/git-governance/2026-09-01-worktree-cleanup.md`