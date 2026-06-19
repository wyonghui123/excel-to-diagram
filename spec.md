# T-guidelines-update-2026-06-19

> **Task ID**: T-guidelines-update-2026-06-19
> **Agent**: Smart Agent A
> **基于 commit**: 42ffb9f
> **风险等级**: low (仅文档更新)
> **开始时间**: 2026-06-19 12:00

## 1. 目标 (Goal)

升级 AGENT_GUIDELINES.md 从 v3.20 到 v3.21，加入 Bug Triage + Hotfix 工作流章节。
**配套**：创建 .coord/bugs.json 示例（用于 bug_triage.py 跟踪）

## 2. 改动文件 (modified_files 白名单)

- [x] `AGENT_GUIDELINES.md` - v3.20 → v3.21 (加 Bug Triage 章节)

## 3. 禁止改 (blacklist)

- ❌ `.agent-status.json`
- ❌ `.git/hooks/*`
- ❌ `d:\filework\.coord\ports.json`

## 4. 依赖

- 基于 commit: `42ffb9f`
- 不依赖其他 agent

## 5. 完成标准 (DoD)

- [x] AGENT_GUIDELINES.md 升级到 v3.21
- [x] 添加 Bug Triage 章节（决策树 + 5/3/1 步工作流）
- [x] 在 worktree 中 commit
- [ ] Merge 到 main

## 6. 风险评估

- **低风险**：仅文档改动，不影响代码
- 不影响其他 agent 的工作流

## 7. 沟通计划

- merge 后所有 agent 可看到 v3.21 规范
- 不需要主动通知（agent 启动时会自动读 AGENT_GUIDELINES.md）

## 8. Review 清单

- [x] 5 条铁律已包含在 commit message
- [x] spec.md 白名单包含所有改动文件
- [x] 在 worktree 中 commit
- [x] pre-commit hook 通过