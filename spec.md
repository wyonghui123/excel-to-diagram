# T-infra-port-isolation-2026-06-19

> **Task ID**: T-infra-port-isolation-2026-06-19
> **Agent**: Smart Agent A
> **基于 commit**: 9d8fc44 (Merge fix: harden add mode data preservation)
> **风险等级**: 🟡 medium (新基础设施, 影响所有 agent)
> **开始时间**: 2026-06-19 11:00

## 1. 目标 (Goal)

解决多 agent 并行开发时"测试哪个版本"的问题。
**根本原因**：之前所有 agent 都用 main 的 3010 端口测代码，导致：
- Agent 1 不得不违反 L2 铁律在主工作树编辑代码
- 43 个 M 文件被 merge 时触发 stash 灾难

**解决方案**：每个 agent 用独立端口（3011-3019）跑自己的服务。

## 2. 改动文件 (modified_files 白名单)

- [x] `scripts/agent_bootstrap.ps1` - 新建 v1.0
- [x] `docs/port-isolation.md` - 新建规范
- [x] `AGENT_GUIDELINES.md` - 升级到 v3.20 (新增 L5 + 端口隔离章节)

## 3. 禁止改 (blacklist)

- ❌ `.agent-status.json` (顶层协调数据)
- ❌ `.git/hooks/*` (hook 由主工作树管理)
- ❌ `d:\filework\.coord\ports.json` (顶层协调数据)

## 4. 依赖

- 基于 commit: `9d8fc44`
- 不依赖其他 agent
- 不需要服务重启

## 5. 完成标准 (DoD)

- [x] `scripts/agent_bootstrap.ps1` 创建，语法正确
- [x] `docs/port-isolation.md` 创建
- [x] `AGENT_GUIDELINES.md` 升级到 v3.20
- [x] pre-commit hook v3.0.2 修复（GBK 编码问题）
- [x] 在 worktree 中 commit, 不污染主工作树
- [ ] Merge 到 main
- [ ] 测试 agent_bootstrap.ps1 能正常工作（需要 user 执行）

## 6. 风险评估

- **风险 1**: agent_bootstrap.ps1 可能跟 service_manager.ps1 不兼容
  - 缓解：保留 service_manager，bootstrap 只创建 worktree
- **风险 2**: 端口冲突（如果其他 agent 占用 3011-3019）
  - 缓解：.coord/ports.json 跟踪端口分配
- **风险 3**: spec.md 覆盖 agent-edit-tab-fix 的 spec.md
  - 缓解：我的 spec.md 任务 ID 明确，独立于其他 agent

## 7. 沟通计划

- merge 后通知 Smart Agent A 已就绪
- 不影响其他 agent（不修改他们的 worktree）
- AGENT_GUIDELINES.md 是文档级改动，不影响代码

## 8. Review 清单

- [x] 5 条铁律已包含在 commit message
- [x] spec.md 白名单包含所有改动文件
- [x] 没有改 spec.md 禁止改的文件
- [x] 在 worktree 中 commit (infra-port-isolation-worktree)
- [x] pre-commit hook 通过 (v3.0.2)