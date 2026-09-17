---
title: 规范二次质量审查报告（Round 2）
date: 2026-09-02
status: 完成
author: AI Assistant
related: 2026-09-02-rules-simplification-v4.0.md, 2026-09-02-rules-phase-C-splitting.md
---

# 规范二次质量审查报告（Round 2）

> **背景**：用户请求"再二次检查下规范文档的质量"，在前次 v4.0 简化 + Phase B 合并 + Phase C 拆分后，再次审查文档质量。

---

## 1. 审查范围

| 范围 | 数量 |
|------|------|
| `.trae/rules/*.md` 文件 | 59 |
| 总行数 | 12,107 |
| 总大小 | 376.8 KB |

## 2. 审查维度

| 维度 | 检查方法 |
|------|---------|
| **死链检测** | markdown link `[xxx](path)` → 文件存在性 |
| **frontmatter** | 文件第 1 行 = `---` 且第 2 行非空 |
| **孤立文件** | 既无 markdown 入度也无文本入度 |
| **alwaysApply** | 是否标注 alwaysApply |
| **CHANGELOG** | 文件是否含历史版本 |
| **文件大小** | > 250 行触发警告（Phase D 待处理）|

## 3. 修复前后对比

| 维度 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| **质量分** | **0/100** | **80/100** | +80 |
| 死链 | 13 | 0 | -13 |
| 缺 frontmatter | 4 | 0 | -4 |
| 孤立文件 | 24 | 0 | -24 |
| alwaysApply | 10/59 | 10/59 | 维持 |
| 无 CHANGELOG | 25 | 25 | 维持 |
| > 250 行 | 19 | 20 | +1 (新增 dead=0 仍 250+ 触发器) |

## 4. 修复明细

### 4.1 补 frontmatter（4 个）

| 文件 | 修复内容 |
|------|---------|
| `core-service-architecture.md` | 新增 yaml frontmatter（title/last_updated/status/enforcement） |
| `development-workflow.md` | 新增 frontmatter（title/last_updated/status/version/based_on） |
| `release-sync-workflow.md` | 新增 frontmatter（title/last_updated/status/version） |
| `worktree-governance.md` | 新增 frontmatter（title/last_updated/status/version） |

### 4.2 修死链（13 个，5 个文件）

**根因诊断**：`.trae/rules/` 实际位于 `d:\filework\.trae\rules\`（不在 `excel-to-diagram/` 项目内），规则文件中的相对路径假设在项目子目录中，导致路径深度错误。

| 文件 | 死链数 | 修复策略 |
|------|--------|---------|
| `audit-compliance.md` | 2 | 链接路径从 `../../` 改为 `../../excel-to-diagram/` |
| `context-usage.md` | 2 | 目标文件不存在 → 改为纯文本提及 + 注 "待重建" |
| `frontend-test-auth.md` | 1 | `../../../docs/...` → `../../excel-to-diagram/docs/...` |
| `meta-model-schema-sync.md` | 3 | 同 audit-compliance 模式 |
| `project_startup.md` | 5 | 拆分为 2/3 层混合路径，`.env` 不存在 → 移除 link 改纯文本 |
| `RULES_INDEX.md` | 3 | `systemmatic-debugging.md` 改为 backtick（是 skill，非规则）；2 个 `multi-agent-infrastructure-v20260620*.md` 改为 `.deprecated/` 路径说明 |

### 4.3 修孤立文件（24 个）

**根因诊断**：QC 算法最初只看 markdown link 入度，忽略"被任何文件文本提及"。修正后算法综合考虑：
- markdown link 入度
- 文本提及（文件名出现在其他文件正文）

**关键操作**：批量转换 `RULES_INDEX.md` 中的 `` `xxx.md` `` 引用为 markdown link `[xxx.md](./xxx.md)`，激活全部 48 个文件的入度引用。

修复后孤立数：**24 → 0**（全部因 RULES_INDEX.md linkify 而激活）。

## 5. 审查工具

- **QC v2**（tools/_tmp_qc2.py）：7 phase 检查，输出写入 `_tmp_qc_reports/` 目录
- **QC v3**：修正孤立判定，加入文本提及
- **QC v4**：完整入度+出度分析

> 工具为一次性审查脚本，未纳入长期工具链。报告输出文件已清理。

## 6. 已知遗留问题

| 问题 | 数量 | 建议 |
|------|------|------|
| > 250 行的超大文件 | 20 | **Phase D**：可拆分但需评估（已 Phase C 拆分过 12 子文件）|
| 无 CHANGELOG 文件 | 25 | 添加版本历史以追踪规范演化（低优先级）|
| `alwaysApply=true` 标记偏少 | 49/59 未标记 | 评估是否需要扩展入口类 alwaysApply 范围 |

## 7. 经验教训

1. **沙箱吞 stdout 陷阱**：本机 QC 脚本 stdout 被吞，导致前次只看到汇总数据。**改用 Write 直接写报告文件**绕过沙箱限制。
2. **SearchReplace 工具偶发不生效**：某些 case 报告"成功"但实际文件未改。**验证手段**：Read 工具读文件确认，或 `git diff` 验证。
3. **路径深度假设错误**：`.trae/rules/` 不在项目内导致所有相对路径深度偏浅。**修法**：写绝对路径或加 `excel-to-diagram/` 前缀。
4. **QC 算法需完整入度+出度**：孤立判定只看 markdown link 出度会漏报"纯文本提及"的文件。

## 8. CHANGELOG

| 日期 | 变更 | 评分 |
|------|------|------|
| 2026-09-02 | Round 2 修复完成 | **80/100** |
| 2026-09-02 | Round 2 修复前 | **0/100** |