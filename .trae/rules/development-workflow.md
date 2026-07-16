# Development Workflow — v3.3 多 Agent 协作标准流程

> 状态: 活跃
> 适用范围: 所有开发智能体 (dev-agent) + e2e agent + 协调智能体
> 触发条件: 任何 BUG / 需求 / 改动
> 与本文件配套: `release-sync-workflow.md`, `INFRA_HANDOVER.md`

## 1. 角色与职责

| 角色 | 主要工作 | 不做 |
|---|---|---|
| **开发智能体** (dev-agent) | 写代码 + 单测 + commit | 不在主工作树 commit, 不动 main 服务, 不 push 到 release |
| **e2e agent** | 在 integration 3007 跑 e2e 测试 | 不动 main 服务, 不做产品决策 |
| **协调智能体** (coordinator) | cherry-pick + 基础设施 + 同步 integration | 不写业务代码, 不做产品验收 |
| **PM** (您) | 业务决策 + main 3006 人工验证 | 不直接改 git, 不直接重启服务 |

## 2. 开发智能体流程

### 2.1 创建独立 worktree

```powershell
pwsh -File D:\filework\scripts\agent_bootstrap.ps1 -BugId V044
```

系统自动:
- 创建 `D:\filework\worktree-V044` (独立目录)
- 创建分支 `fix/V044-import-cache` (从 integration HEAD 拉)
- 复制 .env / 锁文件机制 / L1-L4 合规检查

### 2.2 写代码 + 单测

```yaml
in-worktree: D:\filework\worktree-V044
branch: fix/V044-import-cache
base: integration/2026-07-04

rules:
  - 仅修改 L1-L4 合规白名单内的文件
  - 修改 spec.md 加 changelog (L4 铁律)
  - 跑单测: python test.py --single <test_name>
```

### 2.3 commit + push

```bash
git add src/components/common/ImportDialog/ImportDialog.vue spec.md
git commit -m "$(cat <<'EOF'
fix(fe): BUG-V044 importDataAsync 路径未清 list cache

根因: pollImportProgress completed 后未调用 clearCache, 关闭弹窗后
     父组件的 loadList() 仍读旧 cache, 显示过期数据
修法: 在 pollImportProgress 完成分支加 try/catch, 主动调用
     boService.clearCache(type) 让下次 query 触发新请求

L1-Worktree: yes (worktree-V044)
L2-NoMain: yes (在 fix/V044-import-cache 分支)
L3-Stash: no (未碰 stash)
L4-SpecMd: yes (已加 changelog)
EOF
)"

# 必须 push 到 origin (让协调智能体 fetch)
git push -u origin fix/V044-import-cache
```

### 2.4 通知协调智能体 + e2e agent

更新 `D:\filework\DEPLOY_HANDOVER_BUG_V044.md`:

```markdown
## 9. 通知状态

- [x] 开发智能体完成 commit (cd9d16d 在 fix/V044-import-cache 分支)
- [x] 已 push origin/fix/V044-import-cache
- [ ] e2e agent 已部署到 integration 3007/3018
- [ ] e2e agent 测试 PASS

→ 通知协调智能体: e2e PASS 后, 请按 release-sync-workflow.md
  执行 cherry-pick 到 release/pre-2026-06-29
```

## 3. e2e agent 流程

### 3.1 部署到 integration 3007/3018

```powershell
# 1. 确认 integration-worktree 包含 dev commit
pwsh -File D:\filework\scripts\check-sha-consistency.ps1 -Strict
# 预期: FAIL (因为 fix 在 origin, integration 还没拉)
# 但代码上 integration HEAD 应该是 fix/V044-import-cache 的祖先

# 2. 拉 fix 到 integration
cd D:\filework\integration-worktree
git fetch origin fix/V044-import-cache
git merge --no-ff origin/fix/V044-import-cache -m 'e2e: integrate fix/V044-import-cache'

# 3. sync DB (如改 schema)
pwsh -File D:\filework\scripts\sync-integration-db.ps1 -Force

# 4. restart integration 3007/3018
pwsh -File D:\filework\scripts\stop-integration.ps1 -Force
pwsh -File D:\filework\scripts\start-integration.ps1
```

### 3.2 跑 e2e 测试

```yaml
# Playwright / MCP 浏览器测试覆盖:
cases:
  - 用户报告路径 (用户说的复现步骤)
  - 边缘场景 1: 多对象批量导入
  - 边缘场景 2: 同一对象重复导入
  - 边缘场景 3: 导入中途取消
```

### 3.3 结果通知

更新 `DEPLOY_HANDOVER_BUG_V044.md`:

```markdown
## 10. e2e 测试结果

| 测试用例 | 期望 | 实际 | 结果 |
|---|---|---|---|
| V044 用户报告路径 | 关闭弹窗后 list 立即刷新 | ✓ | PASS |
| 边缘场景 1 | 多对象批量导入不串数据 | ✓ | PASS |
| 边缘场景 2 | 同对象重复导入正常 | ✓ | PASS |
| 边缘场景 3 | 导入中途取消不卡死 | ✓ | PASS |

→ [PASS] 所有 e2e 用例通过, 通知协调智能体 cherry-pick
```

或失败:

```markdown
→ [FAIL] 边缘场景 2 失败 (导入后 list 仍有旧数据)
   反馈开发智能体: 需要在 ImportDialog.vue:1350 加 await loadList()
```

## 4. 协调智能体 cherry-pick 流程

详见 [release-sync-workflow.md](./release-sync-workflow.md)。

简要:
1. 收到 "e2e PASS" 通知
2. fetch origin, cherry-pick fix/V044-import-cache → release/pre-2026-06-29
3. push release origin
4. rebuild frontend dist (如前端改动): `rebuild-frontend-dist.ps1`
5. 重启主 3011 (如后端改动): `service_manager.ps1 restart main-backend`
6. 跑 `check-sha-consistency.ps1` 验证
7. 通知 PM: 主 3006 已就绪

## 5. PM 验证流程

```yaml
# 在 3006 浏览器上手动验证
steps:
  1. http://localhost:3006 登录
  2. 触发 dev-login (如需要)
  3. 复现 BUG 路径 (用户报告的步骤)
  4. 验证修复生效
  5. 验证无 regression (周边功能仍正常)

# 通过 → 通知部署智能体
notify: "BUG-V044 在 main 3006 验证通过, 可以部署远程"

# 失败 → 反馈协调智能体 revert
notify: "BUG-V044 在 main 3006 验证失败, 描述: <现象>. 协调智能体请 revert"
```

## 6. 铁律 (硬约束)

| 铁律 | 内容 |
|---|---|
| **L1 Worktree** | 任何代码改动必须在独立 worktree |
| **L2 No Main** | 禁止在主工作树 commit |
| **L3 No Stash** | 禁止 stash 别人的工作 |
| **L4 Spec.md** | modified_files 必须列在 spec.md |
| **L5 No Direct Push Release** | 开发智能体不直接 push release 分支 |
| **L6 No Touch Main Service** | 禁止动主 3006/3011 (只有协调智能体能动) |

## 7. 故障排查

### Q1: dev commit 在 integration HEAD 上但 origin release 还没, 怎么办?

**答**:e2e agent 流程正常推进。协调智能体最终 cherry-pick 时会用 merge-base,不会丢。

### Q2: cherry-pick 冲突了怎么办?

**答**:
```bash
git cherry-pick <commit>  # 失败时
git status  # 看冲突
# 手动解决冲突
git add <resolved files>
git cherry-pick --continue
```

### Q3: e2e agent 怎么知道 dev commit 完成了?

**答**:看 `DEPLOY_HANDOVER_BUG_<ID>.md` §9 的 checkbox。
e2e agent 应在每次 commit 后 5-10 分钟主动检查(轮询)。

## 8. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-07-04 | AI Assistant (协调智能体) | v3.3 创建, 整合 PM 视角的工作流定义 |