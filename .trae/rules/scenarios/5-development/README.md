---
title: 场景 5. 开发（编码/组件/UI）
scenario: 5-development
icon: "5."
---

# 场景 5. 开发（编码/组件/UI） (Development (Code/Component/UI))

> **场景定位**：日常开发规范：编码标准、组件治理、UI 标准、双端自适应基础设施、元模型、编码安全
> **场景关键词**：`编码` / `组件` / `UI` / `schema` / `meta` / `encoding` / `agent 开发` / `响应式` / `手机端`

---

## 何时进入此场景

当 AI 任务画像符合以下任一情况时，进入此场景：

- 编码
- 组件
- UI
- schema
- meta

---

## 必读文件（按重要性排序）

1. **[development-workflow.md](./development-workflow.md)** — 开发工作流 v4.0 (任务画像决策树)
1. **[responsive-adaptive-infra.md](./responsive-adaptive-infra.md)** — 双端自适应基础设施 (手机端 + PC 同级，断点/隧道/品牌名/CSS 铁律)
1. **[AI_AGENT_COMPONENT_GUIDE.md](./AI_AGENT_COMPONENT_GUIDE.md)** — AI Agent 组件指南入口 (拆分 ↓)
1. **[ai-component-reference.md](./ai-component-reference.md)** — AI 组件参考 (标准组件库)
1. **[ai-component-templates.md](./ai-component-templates.md)** — AI 组件模板 (Vue 3 Composition API)
1. **[ai-component-checklist.md](./ai-component-checklist.md)** — AI 组件检查清单

---

## 完整文件清单（28 个）

| 文件 | 用途 |
|------|------|
| [development-workflow.md](./development-workflow.md) | 开发工作流 v4.0 (任务画像决策树) |
| [responsive-adaptive-infra.md](./responsive-adaptive-infra.md) | **双端自适应基础设施** (断点/隧道/品牌名/CSS 铁律/验收标准) |
| [AI_AGENT_COMPONENT_GUIDE.md](./AI_AGENT_COMPONENT_GUIDE.md) | AI Agent 组件指南入口 (拆分 ↓) |
| [ai-component-reference.md](./ai-component-reference.md) | AI 组件参考 (标准组件库) |
| [ai-component-templates.md](./ai-component-templates.md) | AI 组件模板 (Vue 3 Composition API) |
| [ai-component-checklist.md](./ai-component-checklist.md) | AI 组件检查清单 |
| [component-governance.md](./component-governance.md) | 组件治理入口 (拆分 ↓) |
| [component-lifecycle.md](./component-lifecycle.md) | 组件生命周期 (FilterBar 等) |
| [component-rules.md](./component-rules.md) | 组件规则 (使用统计 + 迁移) |
| [component-config.md](./component-config.md) | 组件配置 (元模型 + API) |
| [coding-standards.md](../../core/coding-standards.md) | 编码标准 (核心规范) |
| [component-layers.md](../../core/component-layers.md) | 组件分层 (UI 架构) |
| [ui-standards.md](../../core/ui-standards.md) | UI 标准 (界面规范) |
| [agent-roles.md](../../core/agent-roles.md) | Agent 角色定义 (RBAC) |
| [checklist.md](../../core/checklist.md) | 开发检查清单 |
| [meta-model-schema-sync.md](./meta-model-schema-sync.md) | 元模型 schema 同步 (drift 检测) |
| [meta-ui-view-config.md](./meta-ui-view-config.md) | **元模型 UI 视图配置** (list/form/detail 三态必填、customFetcher 判据、权限码双段式) |
| [meta-menu-retirement.md](./meta-menu-retirement.md) | **元数据菜单生命周期** (独立菜单判据、init 脚本清理假成功、migration 退役存量行) |
| [audit-compliance.md](./audit-compliance.md) | 审计合规 (audit_log) |
| [encoding-prevention-v20260612.md](../../encoding-prevention-v20260612.md) | 编码预防 (CRLF/BOM/UTF-8) |
| [file-encoding-rules.md](../../file-encoding-rules.md) | 文件编码规则 |
| [ai-content-protection.md](../../ai-content-protection.md) | AI 内容保护 (版权扫描) |
| [ai-agent-undo-protection.md](../../ai-agent-undo-protection.md) | AI 撤销保护 (防误改) |
| [context-usage.md](./context-usage.md) | 上下文使用 (.trae/context/) |
| [agent-bootstrap.md](./agent-bootstrap.md) | Agent 启动引导 (新人/AI) |
| [doc-sync-rules.md](../../doc-sync-rules.md) | 文档同步规则 (代码 ↔ 文档) |
| [project_rules.md](../../project_rules.md) | 项目规则总览 |
| [engineering-guidelines.md](./engineering-guidelines.md) | 工程指南 (最佳实践) |

---

## 关联场景

**前序场景**：
- 视任务而定

**后续场景**：
- 视任务而定

---

## CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-10-23 | 新增「元模型 UI 视图配置」与「元数据菜单生命周期」两份规范（文件数 26 → 28） |
| 2026-10-13 | 新增双端自适应基础设施规范 (手机端与 PC 端同级) |
| 2026-09-02 | v5.0 场景化重构 (从扁平主题分类迁移到场景目录) |
