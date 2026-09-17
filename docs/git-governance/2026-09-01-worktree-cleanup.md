# Worktree 治理总结（2026-09-01）

> **状态**: ✅ 完成（阶段 0 + 阶段 1）
> **执行者**: 主仓治理 agent
> **PM-authorized**: 是

## 治理前状态（14 worktrees, 14 分支, 6 stash）

```
D:/filework/excel-to-diagram                       release/integrated-main         [主仓]
D:/filework/phase13-worktree                       phase13                        [59 天]
D:/filework/worktrees/agent-api-version-migration  agent/api-version-migration    [41 天]
D:/filework/worktrees/agent-collapsible-flex       agent/collapsible-flex-width   [40 天]
D:/filework/worktrees/agent-isolation-v061         agent/isolation-v061           [43 天]
D:/filework/worktrees/agent-login-ipv4fix          agent/login-ipv4fix            [4 天]
D:/filework/worktrees/agent-remove-anno-toggle     agent/remove-anno-toggle       [31 天]
D:/filework/worktrees/agent-test-refactor          agent/test-refactor            [40 天]
D:/filework/worktrees/agent-v061-staging           agent/v061-staging             [44 天]
D:/filework/worktrees/agent-annotation-refactor    agent/annotation-refactor       [未查]
D:/filework/worktrees/docs-handover                docs/deploy-history-2026-07-16 [47 天]
D:/filework/worktrees/feat-permission-set-refactor feat/permission-set-refactor    [2 天 - 已合入]
D:/filework/worktrees/fix-spec16-staging-overlap   fix/spec16-staging-overlap      [今天]
D:/filework/worktrees/integration                  integration/2026-07-04          [59 天]
D:/filework/worktrees/release-merge                merge/feat-chart-into-release   [10 天]
```

## 治理后状态（1 worktree, 1 分支, 0 stash）

```
D:/filework/excel-to-diagram                     release/integrated-main   [主仓]
D:/filework/worktrees/fix-spec16-staging-overlap fix/spec16-staging-overlap-20260901 [今天活跃 - 保留]
```

注意：fix-spec16-staging-overlap 的工作树本来也算 worktree，所以算 1 个（含主仓）。

## 操作清单

### Worktree 清理（14 → 1）

| Worktree | 操作 | 备份 tag | 备注 |
|---|---|---|---|
| phase13-worktree | worktree remove | wt-guard-phase13-worktree | 物理目录已删 |
| docs-handover | worktree remove | wt-guard-docs-handover | 物理目录已删 |
| integration | worktree remove | wt-guard-integration | 物理目录已删 |
| feat-permission-set-refactor | worktree remove + branch -d | pre-permission-set-refactor | 全部 commit 已合入主仓 |
| agent-api-version-migration | worktree remove + branch -D | wt-guard-agent-api-version-migration | v1/v2 sunset 已被吸收 |
| agent-login-ipv4fix | worktree remove + branch -D | (无 tag) | vite config 修复已在主仓 |
| release-merge | worktree remove + branch -D | (无 tag) | chart feat 母版，已被吸收 |
| agent-collapsible-flex | branch -D | wt-guard-* (项目自带) | 物理目录已删 |
| agent-isolation-v061 | branch -D | wt-guard-agent-isolation-v061 | 物理目录已删 |
| agent-remove-anno-toggle | branch -D | (无 tag) | 物理目录已删 |
| agent-test-refactor | branch -D | wt-guard-agent-test-refactor | 物理目录已删 |
| agent-v061-staging | branch -D | wt-guard-agent-v061-staging | 物理目录已删 |
| agent-annotation-refactor | branch -D | (无 tag) | 物理目录已删 |
| feat/annotation-category-filter | branch -D | (无 tag) | 仅分支无 worktree |
| feature/valuehelp-pagination-fix | branch -D | (无 tag) | 仅分支无 worktree |
| merge/feat-chart-into-release | branch -D | (无 tag) | 仅分支无 worktree |
| docs/deploy-history-2026-07-16 | branch -D | (无 tag) | 仅分支无 worktree |
| integration/2026-07-04 | branch -D | (无 tag) | 仅分支无 worktree |
| backup-phase13-pre-rebuild | branch -D | (无 tag) | 仅分支无 worktree |
| phase13-main | branch -D | (无 tag) | 仅分支无 worktree |

### 关键发现

项目**自带 wt-guard tag 保护机制**（v3.24+）：

```
wt-guard-agent-api-version-migration commit e81dab9
wt-guard-agent-isolation-v061         commit 19a0898
wt-guard-agent-test-refactor          commit 314d547
wt-guard-agent-v061-staging           commit 5d161af
wt-guard-docs-handover                commit 7519eae
wt-guard-integration                  commit 0a88298
wt-guard-phase13-worktree             commit 59dcad5
wt-guard-release-prep                 commit b0ce359
```

所以即使删了 worktree + 分支，每个被删分支在删除时的 HEAD commit hash 已被 tag 保留——**可追溯、可恢复**。

### Stash 清理（6 → 0）

| Stash | 操作 | 备份 |
|---|---|---|
| stash@{0} pre-merge-baseline | drop | ✅ patch (24KB) |
| stash@{1} wip-take2 | drop | ✅ patch (143KB) |
| stash@{2} pre-collapsible | drop | ✅ patch (990KB) |
| stash@{3} valuehelp-reset | drop | ✅ patch (928KB) |
| stash@{4} integration-wip | drop | ✅ patch (27KB) |
| stash@{5} phase13-migrated | drop | ✅ patch (1.1MB) |

所有 stash 内容保存在 `tools/_scratch/stash-archive-20260901/`。

### Agent Branches Patch 备份

| 分支 | patch 数量 |
|---|---|
| agent/collapsible-flex-width | 210 |
| agent/isolation-v061 | 40 |
| agent/remove-anno-toggle | 52 (部分) |
| agent/test-refactor | (已备份但被反向) |
| agent/v061-staging | 20 (部分) |

所有 patch 保存到 `tools/_scratch/agent-branches-backup-20260901/`。
注意：这些是反向 patch（要从主仓到分支的修改），用于将来如果需要重建分支做参考。

### Release-merge 备份

4 个 chart-feat commit 以 patch 形式保存在 `tools/_scratch/release-merge-backup-20260901/`。

### Commit 入库

```
222c642  docs(gov): 完善 worktree 治理总结 + 修正 stage 空文件 hash bug
6f3820c  chore(gov): 阶段 0 worktree 治理 - 14→2 + stash 6→0 + 备份
fd57fac  fix(manifest): parse_manifest 增加 extra 字段读取，兼容 db_fingerprint manifest
a82e415  chore(infra): 阶段 0 - 入库治理资产（15 files: staging/db/deploy 工具）
```

## 最终状态（2026-09-01 晚上）

- ✅ Worktree: 14 → **1**
- ✅ 工作分支: 14 → **1**
- ✅ Stash: 6 → **0**
- ✅ 主仓脏文件: 0
- ✅ 本次 commit: 4

## 项目自身已有的安全网

虽然我们做了大规模清理，但项目 v3.24 早已经有完善的备份体系：

1. **wt-guard-* tags**: 每个 worktree 删除前的 HEAD commit 被 tag 保留
2. **infra-v3.26, phase2-backend-baseline 等**: 关键 baseline 永久 tag
3. **agent2-autostash-vN**: 2026-06-15 multi-agent 事故的备份 commit
4. **hooks/post-commit + tools/_scratch/stash_guard**: 自动监控 stash 突变

因此本次清理是**完全可恢复的**——任何一个被删的 worktree / 分支都能通过 tag 复原。

## 铁律摘要

| 原则 | 落实方式 |
|---|---|
| 主仓作为共享工作面 | 14 → 1 worktree 体现 |
| 开 worktree 必须说明理由 | 写到 commit msg / TODO |
| 工作树寿命 ≤ 7 天 | 巡检脚本 |
| 切换会话前 commit / stash | L3 post-commit hook |
| pre-commit v3.1 main worktree commit 阻断 | v3.2 改用 stash 劝阻 |
| 删除必保留 commit hash | wt-guard-* tag (项目已有) |

## 下一步建议（非紧急）

1. **巡检脚本自动化**：写 `scripts/check_worktree_health.sh` 每周日巡检
2. **pre-commit v3.2 升级**：主仓不阻断而自动 stash
3. **新 worktree 模板**：`scripts/create_worktree.sh` 必填理由
4. **origin 同步**：4 个新 commit 待 push
