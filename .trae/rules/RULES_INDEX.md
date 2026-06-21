---
alwaysApply: false
description: "规则索引：所有规则文件的目录和分类"
---

# 规范规则索引

> 最后更新: 2026-06-20 | 状态: 活跃
> **v3 升级**: 2026-06-20 添加 multi-agent-infrastructure V1 + V2 规则
> 本文件是所有规范规则的统一索引和依赖图
> **v2 升级**: 2026-06-19 加 START_HERE.md + 顶层协调文档

## 快速入口

| 入口 | 文件 | 用途 |
|------|------|------|
| [d:\filework\START_HERE.md](../../START_HERE.md) | **新 agent 必读入口** | 5 步快速开始 |
| [d:\filework\AGENT_GUIDELINES.md](../../AGENT_GUIDELINES.md) | **顶层协调规范** | v3.20 多 agent 协作 |
| [SESSION_REMINDER.md](./SESSION_REMINDER.md) | 18 条铁律 | 新会话必读 |
| [project_rules.md](./project_rules.md) | 项目核心 | 索引 + 必读文件 |
| [core/](./core/) | 核心子规范 | 拆分后的详细规则 |

## 活跃规范目录

### 顶层规范（13个）

| 规范 | 主题 | 状态 | 优先级 |
|------|------|------|--------|
| [SESSION_REMINDER.md](./SESSION_REMINDER.md) | 会话开始铁律 | 活跃 | 必读 |
| [project_rules.md](./project_rules.md) | 项目核心（索引） | 活跃 | 必读 |
| [ai-coding-standards.md](./ai-coding-standards.md) | AI 编码规范 | 活跃 | 必读 |
| [context-usage.md](./context-usage.md) | Context 使用 | 活跃 | 推荐 |
| [e2e-simplification.md](./e2e-simplification.md) | E2E v2 简化方案 | 活跃 | 必读 |
| [e2e-testing.md](./e2e-testing.md) | E2E 测试 | 活跃 | 必读 |
| [engineering-guidelines.md](./engineering-guidelines.md) | 工程规范 | 活跃 | 参考 |
| [file-encoding-rules.md](./file-encoding-rules.md) | 文件编码 | 活跃 | 必读 |
| [powershell-execution-guide.md](./powershell-execution-guide.md) | PowerShell + trae-sandbox 整合规范 | 活跃 | 必读（v2026.06.20 整合）|
| [powershell-curl-alias.md](./powershell-curl-alias.md) | PowerShell curl 别名 | 活跃 | 推荐 |
| [project_startup.md](./project_startup.md) | 项目启动 | 活跃 | 参考 |
| [doc-sync-rules.md](./doc-sync-rules.md) | 文档同步 | 活跃 | 推荐 |
| [AI_AGENT_COMPONENT_GUIDE.md](./AI_AGENT_COMPONENT_GUIDE.md) | AI 组件指南 | 活跃 | 参考 |

### core/ 核心子规范（8个，2026-06-07 新拆分）

| 规范 | 主题 | 来源 |
|------|------|------|
| [core/checklist.md](./core/checklist.md) | 强制检查清单 + 会话一致性 | project_rules.md |
| [core/ui-standards.md](./core/ui-standards.md) | UI 样式规范 | project_rules.md |
| [core/coding-standards.md](./core/coding-standards.md) | AI 编码规范 | project_rules.md + ai-coding-standards.md |
| [core/server-management.md](./core/server-management.md) | 服务器管理 | project_rules.md |
| [core/e2e-testing.md](./core/e2e-testing.md) | E2E 核心经验 | project_rules.md |
| [core/form-debugging.md](./core/form-debugging.md) | 表单渲染调试 | project_rules.md |
| [core/component-layers.md](./core/component-layers.md) | 组件分层架构 | project_rules.md |
| [core/agent-roles.md](./core/agent-roles.md) | 智能体角色 | project_rules.md |

### 测试规范（7个）

| 规范 | 主题 | 优先级 |
|------|------|--------|
| [test_rules.md](./test_rules.md) | 测试运行规则 | 必读 |
| [test-case-standards.md](./test-case-standards.md) | 测试用例标准 | 必读 |
| [test-data-rules.md](./test-data-rules.md) | 测试数据管理 | 推荐 |
| [test-observability-rules.md](./test-observability-rules.md) | 测试可观测性 | 推荐 |
| [test-runner-template.md](./test-runner-template.md) | 测试运行模板 | 参考 |
| [test-script-quality-analysis.md](./test-script-quality-analysis.md) | 测试脚本质量分析 | 参考 |
| [frontend-testing-standards.md](./frontend-testing-standards.md) | 前端测试 | 推荐 |

### 架构/元模型规范（5个）

| 规范 | 主题 | 优先级 |
|------|------|--------|
| [meta-model-schema-sync.md](./meta-model-schema-sync.md) | 元模型同步 | 必读 |
| [component-governance.md](./component-governance.md) | 组件治理 | 推荐 |
| [audit-compliance.md](./audit-compliance.md) | 审计合规 | 必读 |
| [frontend-test-auth.md](./frontend-test-auth.md) | 前端认证 | 必读 |
| [browser-test-verification.md](./browser-test-verification.md) | 浏览器验证 | 推荐 |
| [page-health-rules.md](./page-health-rules.md) | 页面健康 | 推荐 |
| [service-management-rules.md](./service-management-rules.md) | 服务管理 | 推荐 |

### 协作规范（3个）

| 规范 | 主题 | 优先级 |
|------|------|--------|
| [multi-agent-coordination.md](./multi-agent-coordination.md) | 多智能体协调 | 必读 |
| [agent-bootstrap.md](./agent-bootstrap.md) | AI Agent 启动 5 步检查（autoload 配套） | 必读 |

### AI 可观测性（2026-06-13 新增）

| 规范 | 主题 | 优先级 |
|------|------|--------|
| [test-observability-rules.md](./test-observability-rules.md) | 测试可观测性 | 推荐 |
| [.trae/scripts/metrics_aggregator.py](../.trae/scripts/metrics_aggregator.py) | 指标聚合脚本 | 参考 |
| [.trae/scripts/prune_agent_logs.py](../.trae/scripts/prune_agent_logs.py) | 日志清理脚本 | 参考 |

## 新加入 / 重要规范（2026-06-19 更新）

| 规范 | 主题 | 优先级 | 备注 |
|------|------|--------|------|
| [INCIDENT_2026-06-17.md](./INCIDENT_2026-06-17.md) | **6/17 P0 事故复盘** | **必读** | 2026-06-17 36h 开发成果丢失事故 |
| [d:\filework\START_HERE.md](../../START_HERE.md) | **新 agent 入口** | **必读** | 5 步快速开始（2026-06-19 新建）|
| [d:\filework\AGENT_GUIDELINES.md](../../AGENT_GUIDELINES.md) | 顶层协调规范 v3.20 | **必读** | 2026-06-19 P0/P1/P2 升级 |
| [d:\filework\spec_template.md](../../spec_template.md) | Spec 模板 | 必读 | P0 规范 |
| [ai-content-protection.md](./ai-content-protection.md) | AI 内容保护 | 推荐 | 防止 AI 误改 |
| [ai-agent-undo-protection.md](./ai-agent-undo-protection.md) | Undo 保护 | 推荐 | 防 stash 灾难 |
| [encoding-prevention-v20260612.md](./encoding-prevention-v20260612.md) | 编码预防 v20260612 | 推荐 | GBK 乱码防御 |
| [ui-standards.md](./ui-standards.md) | UI 样式规范（顶层）| 推荐 | 完整 UI 规范 |
| [service-management-rules.md](./service-management-rules.md) | 服务管理 | 推荐 | service_manager 规范 |
| [multi-agent-coordination.md](./multi-agent-coordination.md) | **多智能体协调 v3.19** | **必读** | 4 防护层 L1-L4 |
| [multi-agent-infrastructure-v20260620.md](./multi-agent-infrastructure-v20260620.md) | **多智能体基础设施 V1** | **必读** | 5 铁律（修复完整性） |
| [multi-agent-infrastructure-v20260620-v2.md](./multi-agent-infrastructure-v20260620-v2.md) | **多智能体基础设施 V2** | **必读** | 12 铁律（沙箱状态机 + Agent Status + Read-First）|

## 已废弃规范（2026-06-20 移至 .deprecated/）

> **目录前缀 . 用于让 Trae 完全跳过扫描**
> **当前废弃文件数：8 个**

### MCP 浏览器测试

| 废弃文件 | 废弃原因 | 替代方案 |
|------|---------|---------|
| [.deprecated/mcp-testing.md](./.deprecated/mcp-testing.md) | MCP 浏览器工具全面禁用 | PlaywrightCLI |
| [.deprecated/mcp-parallel-integration.md](./.deprecated/mcp-parallel-integration.md) | MCP 多实例方案废弃 | PlaywrightCLI |
| [.deprecated/multi-agent-browser-isolation.md](./.deprecated/multi-agent-browser-isolation.md) | session_manager 废弃 | PlaywrightCLI |
| [.deprecated/multi-agent-quickstart.md](./.deprecated/multi-agent-quickstart.md) | 旧版多智能体指南 | multi-agent-coordination.md |
| [.deprecated/ai-coding-standards.md](./.deprecated/ai-coding-standards.md) | 已合并到 coding-standards.md | coding-standards.md |
| [.deprecated/trae-sandbox-behavior.md](./.deprecated/trae-sandbox-behavior.md) | 2026-06-20 整合到 powershell-execution-guide.md | powershell-execution-guide.md |
| [.deprecated/powershell-rules.md](./.deprecated/powershell-rules.md) | 2026-06-20 整合到 powershell-execution-guide.md | powershell-execution-guide.md |

**目录说明**：[.deprecated/README.md](./.deprecated/README.md)

## 重复内容清理（2026-06-19 修正）

> **下表中的文件内容已被合并/重复，禁止在 Agent prompt 中同时引用。**
> **2026-06-19 验证**: 实际只有 1 处真正的 redirect, 其他 2 处经核实是**互补专题**而非重复。

| 文件 | 状态 | 实际关系 | 建议 |
|------|------|---------|------|
| [ai-coding-standards.md](./ai-coding-standards.md) | ✅ **真 redirect** (13 行, 已合并) | 内容已合并到 [core/coding-standards.md](./core/coding-standards.md) | 只读 core/coding-standards.md |
| [powershell-curl-alias.md](./powershell-curl-alias.md) | 🟡 **专题文档** (curl 专项) | 与 [powershell-rules.md](./powershell-rules.md) 互补 (通用 vs 专题) | **两者都读**（不重复）|
| [core/agent-roles.md](./core/agent-roles.md) | 🟡 **引用文档** (30 行) | 引用 [../context-usage.md](../context-usage.md) | **两者都读**（不重复）|

**修正说明**:
- 原 RULES_INDEX.md 标注 3 处重复, 实际只有 1 处
- powershell-curl-alias.md 是 curl 专项 (1706B), powershell-execution-guide.md 是通用 (14196B) — 互补
- core/agent-roles.md 引用 context-usage.md — 互补
- 建议: 把 ai-coding-standards.md 移到 deprecated/ 目录 (2026-06-19 待执行) |

## 规范依赖图

```
SESSION_REMINDER (核心入口)
   |
   +-- project_rules (项目核心)
   |     |
   |     +-- core/ui-standards
   |     +-- core/coding-standards
   |     +-- core/server-management
   |     +-- core/e2e-testing
   |     +-- core/form-debugging
   |     +-- core/component-layers
   |     +-- core/agent-roles
   |     +-- core/checklist
   |
   +-- e2e-simplification (v2 简化)
   |     |
   |     +-- e2e-testing (E2E 核心)
   |     +-- frontend-test-auth
   |     +-- browser-test-verification
   |
   +-- test_rules (测试)
   |     |
   |     +-- test-case-standards
   |     +-- test-data-rules
   |     +-- test-observability-rules
   |     +-- test-runner-template
   |
   +-- meta-model-schema-sync (元模型)
   |     |
   |     +-- audit-compliance
   |     +-- component-governance
   |
   +-- file-encoding-rules (基础设施)
   |     |
   |     +-- powershell-rules
   |     +-- powershell-curl-alias
   |
   +-- multi-agent-coordination (协作)
   |
   +-- doc-sync-rules (文档)
```

## 强制级别说明

- **必读**: 每个会话开始必须阅读
- **推荐**: 相关任务时阅读
- **参考**: 需要时查阅

## 规范使用顺序

### 1. 新会话开始

1. [SESSION_REMINDER.md](./SESSION_REMINDER.md) - 47 条铁律
2. [project_rules.md](./project_rules.md) - 项目核心

### 2. UI 任务

1. [core/ui-standards.md](./core/ui-standards.md)
2. [core/coding-standards.md](./core/coding-standards.md)
3. [core/checklist.md](./core/checklist.md) - 强制检查清单

### 3. E2E/前端测试

1. [e2e-simplification.md](./e2e-simplification.md) - v2 简化方案
2. [core/e2e-testing.md](./core/e2e-testing.md) - 核心经验
3. [frontend-test-auth.md](./frontend-test-auth.md)
4. [browser-test-verification.md](./browser-test-verification.md)

### 4. 后端任务

1. [core/coding-standards.md](./core/coding-standards.md)
2. [core/server-management.md](./core/server-management.md)
3. [meta-model-schema-sync.md](./meta-model-schema-sync.md)

### 5. 表单问题调试

1. [core/form-debugging.md](./core/form-debugging.md) - 7 铁律

### 6. 智能体协作

1. [multi-agent-coordination.md](./multi-agent-coordination.md)
2. [core/agent-roles.md](./core/agent-roles.md)

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-19 | Smart Agent A | v2 升级：加 START_HERE.md 入口；加 INCIDENT_2026-06-17.md；加 AGENT_GUIDELINES.md v3.20；加 spec_template.md；加 5 个缺失规范；修正 SESSION_REMINDER 18 条（非 47 条）；把 ai-coding-standards.md 移到 deprecated/；修正重复标记（实际只有 1 处）|
| 2026-06-13 | AI Assistant | 测试可观测性规范；标记 ai-coding-standards/powershell-curl-alias 重复 |
| 2026-06-07 | AI Assistant | 创建 RULES_INDEX.md，统一规范索引和依赖图 |
