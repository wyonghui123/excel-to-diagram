# 规范规则索引

> 最后更新: 2026-06-07 | 状态: 活跃
> 本文件是所有规范规则的统一索引和依赖图

## 快速入口

| 入口 | 文件 | 用途 |
|------|------|------|
| [SESSION_REMINDER.md](./SESSION_REMINDER.md) | 47 条铁律 | 新会话必读 |
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
| [powershell-rules.md](./powershell-rules.md) | PowerShell 规则 | 活跃 | 必读 |
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

## 已废弃规范（4个，2026-06-07 移至 deprecated/）

| 文件 | 废弃原因 | 替代方案 |
|------|---------|---------|
| [deprecated/mcp-testing.md](./deprecated/mcp-testing.md) | MCP 浏览器工具全面禁用 | PlaywrightCLI |
| [deprecated/mcp-parallel-integration.md](./deprecated/mcp-parallel-integration.md) | MCP 多实例方案废弃 | PlaywrightCLI |
| [deprecated/multi-agent-browser-isolation.md](./deprecated/multi-agent-browser-isolation.md) | session_manager 废弃 | PlaywrightCLI |
| [deprecated/multi-agent-quickstart.md](./deprecated/multi-agent-quickstart.md) | 旧版多智能体指南 | multi-agent-coordination.md |

**目录说明**：[deprecated/README.md](./deprecated/README.md)

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
| 2026-06-07 | AI Assistant | 创建 RULES_INDEX.md，统一规范索引和依赖图 |
