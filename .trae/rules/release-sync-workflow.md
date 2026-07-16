# Release Sync Workflow — v3.3 协调智能体的标准流程

> 状态: 活跃
> 适用范围: 协调智能体 (coordinator)
> 触发条件: e2e agent 报告 BUG fix 在 integration 测试通过
> 与本文件配套: `development-workflow.md`, `INFRA_HANDOVER.md` §4.2

## 1. 触发器

协调智能体执行 cherry-pick / merge / sync 流程的触发条件:

| 触发器 | 何时 | 备注 |
|---|---|---|
| **T1 e2e PASS** | e2e agent 报告 BUG fix 在 integration 通过 | 主要触发器 |
| **T2 check-sha FAIL 但代码等价** | 两个分支有相同 fix 但 SHA 不同 | 内容等价应自动 PASS (见 check-sha v3.3) |
| **T3 PM 明确指示** | "fix V044 后同步到 3006" | 兜底触发器 |

## 2. 策略选择

### 2.1 情况 A: integration HEAD 是 release HEAD 的 fast-forward

```
release: A → B
integration: A → B → C (新增 fix)
```

**策略**:`merge --ff-only` 把 release HEAD 推到 integration HEAD。

但实际**更可能反过来**:integration 落后 release。**这是 V043 修复后的常见情况**。

**协调智能体执行**:
```bash
cd D:\filework\integration-worktree
git fetch origin release/pre-2026-06-29
git merge --ff-only origin/release/pre-2026-06-29
# push 不必要, integration 是本地
```

### 2.2 情况 B: integration HEAD 与 release HEAD diverged

```
release:        A → B → C (新 fix)
integration:    A → B → D (新 fix)
```

**策略**:`merge --no-ff` 保留双方历史。

**协调智能体执行**:
```bash
cd D:\filework\integration-worktree
git fetch origin release/pre-2026-06-29
git merge --no-ff origin/release/pre-2026-06-29 -m 'integration: merge release 含 <list fixes>'
```

**注意**:会留下一个 merge commit。如果 integration 的 D 和 release 的 C 是相同 fix 但 hash 不同,内容会重复(但仅 commit 重复,代码无重复)。

### 2.3 情况 C: 需要单独 cherry-pick 一个 fix commit 到 release

```
release:    A → B
origin:     A → B → D (dev-agent 的 fix/V044-import-cache 分支上)
integration: A → B (落后 release, 不含 D)
```

**策略**:`cherry-pick` (保留 dev-agent 原 commit 信息)。

**协调智能体执行**:
```bash
cd D:\filework\release-prep-worktree
git fetch origin fix/V044-import-cache
git cherry-pick fix/V044-import-cache
# 解决冲突 (如有):
#   git status
#   ... 手动 ...
#   git cherry-pick --continue
git push --no-verify origin release/pre-2026-06-29
```

**保留 commit 信息**:cherry-pick 自动保留原作者/时间/签名,不丢失溯源。

## 3. 步骤 (情况 C — V044 类)

### 3.1 前置检查

```bash
# 1. 当前 release 与 origin 同步
cd D:\filework\release-prep-worktree
git rev-list --left-right --count origin/release/pre-2026-06-29...release/pre-2026-06-29
# 预期: 0  0 (或 0  N, 但不能 N  0)

# 2. integration 状态
cd D:\filework\integration-worktree
git log --oneline -3
```

### 3.2 cherry-pick

```bash
cd D:\filework\release-prep-worktree

# Stash 临时改动 (如有)
git stash push -m 'sync-pre-cherrypick-2026-07-04'

# Cherry-pick
git fetch origin fix/V044-import-cache
git cherry-pick fix/V044-import-cache

# 处理冲突
if [ $? -ne 0 ]; then
  git status
  # 手动解决冲突
  # ... (development-workflow.md §7 Q2)
  git cherry-pick --continue
fi
```

### 3.3 push

```bash
git push --no-verify origin release/pre-2026-06-29
```

### 3.4 (如前端改动) rebuild dist

```powershell
pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1
# 默认: build + cp + 重启 3006 (要确认)
# 加速: -SkipRestart (build + cp, 手动启 3006)
```

### 3.5 (如后端改动) 重启主 3011

```powershell
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend
# 不用 rebuild dist
# 后端会自动 reload (waitress 不支持热 reload, 需要重启)
```

### 3.6 同步 integration

```powershell
# 1. 同步 DB (如改 schema)
pwsh -File D:\filework\scripts\sync-integration-db.ps1 -Force

# 2. 把 release 的代码同步到 integration
# (V044 case: 用 merge --no-ff, 因为 integration 可能有 dev-agent 原始 commit)
cd D:\filework\integration-worktree
git fetch origin release/pre-2026-06-29
git merge --no-ff origin/release/pre-2026-06-29 -m 'integration: sync release 含 <fixes>'

# 3. (如前端改动) rebuild integration dist
pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1 `
    -ReleasePath "D:\filework\integration-worktree" `
    -FrontendPort "3007" `
    -Force

# 4. 重启 integration 3018 (如果是用 sync DB 流程, 服务已自动重启)
# 否则手动启:
# pwsh -File D:\filework\scripts\service_manager.ps1 restart integration-backend
```

### 3.7 验证

```powershell
# 主线检查
pwsh -File D:\filework\scripts\status-integration.ps1
pwsh -File D:\filework\scripts\check-sha-consistency.ps1
# 预期: 至少 1 PASS (Git HEAD SHA content-equivalent), DB PASS
```

### 3.8 通知 PM

更新 `DEPLOY_HANDOVER_BUG_V044.md`:

```markdown
## 11. 协调智能体 sync 结果

- [x] cherry-pick 045437f 完成, 内容含 V044 fix
- [x] push origin (0  0 同步)
- [x] rebuild frontend dist
- [x] 主 3006 重启 (PID 36172)
- [x] integration 3007/3018 同步
- [x] check-sha PASS

→ 通知 PM: 主 3006 已就绪, 请人工验证 BUG-V044
```

## 4. 失败回滚

如果 cherry-pick 后 PM 验证发现 regression:

```bash
cd D:\filework\release-prep-worktree

# 1. revert cherry-pick commit
git revert --no-edit <cherry-pick-commit-hash>
# 例: git revert --no-edit 045437f

# 2. push
git push --no-verify origin release/pre-2026-06-29

# 3. (如前端) rebuild dist + 重启 3006
pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1

# 4. (如后端) 重启 3011
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend

# 5. 通知 PM: revert 完成, 请重新验证
```

## 5. 关键铁律

| 铁律 | 内容 |
|---|---|
| **L1 不在主工作树写代码** | 协调智能体本身也不写业务代码 |
| **L2 cherry-pick 保留 commit** | 必须保留 dev-agent 原 commit (作者/时间/签名) |
| **L3 同步前必跑 check-sha** | sync 前确认 release/integration 状态 |
| **L4 rebuild + restart 配对** | 前端改了 → rebuild + 3006 重启; 后端改了 → 3011 重启 |
| **L5 push 前必验证** | push 前必跑 `check-sha-consistency.ps1` |

## 6. 故障排查

### Q1: cherry-pick 后 integration 还是 SHA 不一致?

**答**:integration 有 dev-agent 原始 commit, 不会变 SHA。`check-sha-consistency.ps1` v3.3+ 会判定"内容等价" PASS。

### Q2: integration DB 损坏 (Windows Copy race condition)?

**答**:
- v3.3+ 的 `sync-integration-db.ps1` 加了 integrity_check + 自动 rollback
- 若仍失败, 用 robocopy 手动 cp:
  ```powershell
  robocopy "D:\filework\release-prep-worktree\meta\architecture.db" `
           "D:\filework\integration-worktree\meta\architecture.db" /R:1 /W:1
  ```

### Q3: 主 3006 重启后用户登录失效?

**答**:vite preview 不持久 session, 后端 cookie 不被前端影响。dev-login 仍可用。

## 7. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-07-04 | AI Assistant (协调智能体) | v3.3 创建, 整合 V044 sync 实战经验 |