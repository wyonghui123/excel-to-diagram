# T-bug-triage-workflow-2026-06-19

> **Task ID**: T-bug-triage-workflow-2026-06-19
> **Agent**: Smart Agent A
> **基于 commit**: f7c7d95
> **风险等级**: medium (新流程, 影响所有 agent)
> **开始时间**: 2026-06-19 11:30

## 1. 目标 (Goal)

解决多 agent 并行开发中**发现 bug 影响主线时的处理流程**问题。

**背景**：基于行业最佳实践研究（sgryt.com, Claude Code, Augment Code），
业界标准做法是：
- P1 Critical → 立即 hotfix（暂停 F1）
- P2 High → Parallel hotfix（不阻塞 F1）
- P3/P4 → Backlog

## 2. 改动文件 (modified_files 白名单)

- [x] `docs/hotfix-workflow.md` - 新建（5 步 hotfix 流程）
- [x] `scripts/bug_triage.py` - 新建（P1/P2/P3/P4 评估工具）

## 3. 禁止改 (blacklist)

- ❌ `.agent-status.json`
- ❌ `.git/hooks/*`
- ❌ `d:\filework\.coord\ports.json`

## 4. 依赖

- 基于 commit: `f7c7d95`
- 依赖现有工具：`agent_bootstrap.ps1` (v1.1), `monitor.py` (v2.1)

## 5. 完成标准 (DoD)

- [x] `docs/hotfix-workflow.md` 创建
- [x] `scripts/bug_triage.py` 创建
- [x] bug_triage.py 语法正确
- [x] bug_triage.py 支持 interactive 和 CLI 模式
- [x] 在 worktree 中 commit
- [ ] Merge 到 main
- [ ] 测试 bug_triage.py (--interactive, --workflow P1/P2)

## 6. 风险评估

- **风险 1**: hotfix-workflow.md 可能跟未来流程变化脱节
  - 缓解：版本号 v1.0 + 文档头部明确创建日期
- **风险 2**: bug_triage.py 自动判定可能误判
  - 缓解：保留 interactive mode，user 可以手动 override

## 7. 沟通计划

- merge 后通知所有 agent 流程升级
- 更新 AGENT_GUIDELINES.md（后续 PR）

## 8. Review 清单

- [x] 5 条铁律已包含在 commit message
- [x] spec.md 白名单包含所有改动文件
- [x] 没有改 spec.md 禁止改的文件
- [x] 在 worktree 中 commit (bug-triage-worktree)
- [x] pre-commit hook 通过