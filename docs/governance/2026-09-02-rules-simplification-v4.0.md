# 规则简化总结 v4.0（2026-09-02）

> **正式版在 `d:\filework\.trae\rules\`**（全局 IDE 配置，立即生效）
> 本文件是项目知识库备份

## 简化成果

| 指标 | v3.x | v4.0 | 变化 |
|---|---|---|---|
| 顶层规范数 | 41 个 | **43 个**（+START_HERE/IRON-RULES）| +2 |
| 必读 5 个文件 | 不明确 | **明确 5 个**（见下）| ✅ |
| RULES_INDEX 行数 | 340 | **131** | -61% |
| SESSION_REMINDER 行数 | 212 | **105** | -50% |
| 顶层入口决策树 | 无 | **START_HERE.md**（30 秒决策）| ✅ |
| L1-L9 铁律卡片 | 散落各文件 | **IRON-RULES-CHEATSHEET.md**（1 页）| ✅ |

## 新增文件（4 个）

| 文件 | 行 | 用途 |
|---|---|---|
| `START_HERE.md` | ~80 | AI Agent 第一个读，30 秒决策树 |
| `IRON-RULES-CHEATSHEET.md` | ~60 | 9 条铁律卡片 |
| `SESSION_REMINDER.md` | ~105 | 4 大铁律 + 调试工具集（精简）|
| `RULES_INDEX.md` | ~131 | 目录（不复述内容）|

## 必读 5 个文件（AI Agent 启动时按序读）

1. **START_HERE.md** — 入口决策树
2. **IRON-RULES-CHEATSHEET.md** — 9 条铁律
3. **SESSION_REMINDER.md** — 4 大铁律 + 调试工具集
4. **development-workflow.md** — 工作流 v4.0
5. **worktree-governance.md** — Worktree 治理 v4.0

## Phase B/C（待后续）

### Phase B — 合并重复
- multi-agent-infrastructure 三件套 (1333 行) → 1 个文件
- ai-coding-standards.md 移 deprecated

### Phase C — 拆分超大文件
- test-case-standards.md (687) → 拆 4 个
- AI_AGENT_COMPONENT_GUIDE.md (593) → 拆 3 个
- component-governance.md (646) → 拆 3 个
- frontend-testing-standards.md (583) → 拆 3 个
- multi-agent-infrastructure-v20260620-v2.md (648) → 拆 4 个

> **用户决策 2026-09-02**：Phase B/C 留待后续，本次只交付 Phase A

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | Phase A | 顶层导航精简（4 文件改动）|
| 2026-09-01 | v4.0 创建 | development-workflow + worktree-governance |