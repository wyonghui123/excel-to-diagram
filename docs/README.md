---
title: Excel-to-Diagram 文档门户
version: 1.1.0
date: 2026-06-13
status: 活跃
audience: 全员
---

# Excel-to-Diagram 文档门户

> 项目所有文档的统一入口
> 最后更新: 2026-06-13 (新增 useMetaList 拆分 + 浅响应式迁移规范索引)

## 核心文档

| 文档 | 用途 | 状态 |
|------|------|------|
| [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md) | 主架构文档 v3.0.2 | 活跃 |
| [架构设计文档.md](./architecture-design.md) | 架构设计总览 | 活跃 |
| [数据模型文档.md](./data-model.md) | 数据模型说明 | 活跃 |
| [需求文档.md](./requirements.md) | 需求规格说明 | 活跃 |
| [需求Backlog.md](./requirements-backlog.md) | 需求待办列表 | 活跃 |
| [API接口文档.md](./api-reference.md) | API 接口说明 | 活跃 |
| [TECH-DEBT.md](./TECH-DEBT.md) | 技术债务 | 活跃 |

## 专题索引

| 文档 | 主题 |
|------|------|
| [PERMISSION_SYSTEM_INDEX.md](./PERMISSION_SYSTEM_INDEX.md) | 权限体系文档统一索引 |
| [DOCUMENTATION_STANDARDS.md](./DOCUMENTATION_STANDARDS.md) | 文档编写规范（命名/分类/生命周期） |

## 专题子目录

### 架构子文档 [architecture/](./architecture/)（25 份）

核心架构设计、页面模式、API 契约、组件库规范等。

| 主要文档 | 主题 |
|---------|------|
| [01-principles.md](./architecture/01-principles.md) | 架构原则 |
| [02-yaml-conventions-v2.md](./architecture/02-yaml-conventions-v2.md) | YAML 元数据规范 v2 |
| [03-meta-driven-ui.md](./architecture/03-meta-driven-ui.md) | 元数据驱动 UI |
| [04-api-contracts-v2.md](./architecture/04-api-contracts-v2.md) | API 契约 v2 |
| [page-type-matrix.md](./architecture/page-type-matrix.md) | 页面类型矩阵 |
| [yaml-child-list-config-example.md](./architecture/yaml-child-list-config-example.md) | YAML 配置示例 |

### 设计规范 [specs/](./specs/)（93 份）

各子系统的设计规范与 RFC。

| 主要文档 | 主题 |
|---------|------|
| [spec-key-template.md](./specs/spec-key-template.md) | KeyTemplate 规范 |
| [spec-soft-delete.md](./specs/spec-soft-delete.md) | 软删除规范 |
| [spec-ai-agent-test-infra-v3.17.md](./specs/spec-ai-agent-test-infra-v3.17.md) | AI Agent 测试基础设施 v3.17 |
| [spec-query-engine-unification.md](./specs/spec-query-engine-unification.md) | 查询引擎统一 |
| [spec-state-management-enhancement.md](./specs/spec-state-management-enhancement.md) | 状态管理增强 |
| [spec-notification-task-alert.md](./specs/spec-notification-task-alert.md) | 通知任务告警 |
| [spec-task-scheduler.md](./specs/spec-task-scheduler.md) | 任务调度 |
| [spec-validation-metadata-driven.md](./specs/spec-validation-metadata-driven.md) | 验证元数据驱动 |
| [spec-version-visibility-draft.md](./specs/spec-version-visibility-draft.md) | 版本可见性 |
| [spec-v3-gap-analysis.md](./specs/spec-v3-gap-analysis.md) | v3 差距分析 |
| [spec-pre-deployment-optimization-v2.md](./specs/spec-pre-deployment-optimization-v2.md) | 部署前优化 v2 |
| [spec-code-health-phase2-2026-06-13.md](./specs/spec-code-health-phase2-2026-06-13.md) | 代码健康 Phase 2 (浅响应式迁移) |
| [spec-use-metalist-split-2026-06-13.md](./specs/spec-use-metalist-split-2026-06-13.md) | useMetaList 拆分分析 + 实施报告 (154 passed / 0 failed) |

### 权限体系升级专题 [spec_权限体系升级/](./spec_权限体系升级/)（7 份）

| 主要文档 | 主题 |
|---------|------|
| [01_background.md](./spec_权限体系升级/01_background.md) | 背景分析 |
| [02_fr.md](./spec_权限体系升级/02_fr.md) | 需求规格 |
| [05_rfc_detailed_design.md](./spec_权限体系升级/05_rfc_detailed_design.md) | RFC 详细设计 |

### 元数据 [metadata/](./metadata/)（1 份）

| 文档 | 主题 |
|------|------|
| [cross-table-filters.md](./metadata/cross-table-filters.md) | 跨表筛选器 |

### 性能 [performance/](./performance/)（4 份）

| 文档 | 主题 |
|------|------|
| [PERFORMANCE_REPORT.md](./performance/PERFORMANCE_REPORT.md) | 性能报告 |
| [FRONTEND_OPTIMIZATION.md](./performance/FRONTEND_OPTIMIZATION.md) | 前端优化 |
| [SUMMARY.md](./performance/SUMMARY.md) | 性能总结 |
| [QUICK_START.md](./performance/QUICK_START.md) | 性能快速开始 |

### 研究与调研 [research/](./research/)（17 份）

| 文档 | 主题 |
|------|------|
| [README.md](./research/README.md) | 研究文档索引 |
| [association-fk-model-research.md](./research/association-fk-model-research.md) | 关联 FK 模型研究 |
| [groupModel-refactor-plan.md](./research/groupModel-refactor-plan.md) | groupModel 重构计划 |
| [layout-interaction-framework.md](./research/layout-interaction-framework.md) | 布局交互框架 |
| [元数据驱动架构与权限体系-头部产品研究.md](./research/元数据驱动架构与权限体系-头部产品研究.md) | 头部产品研究 |

### 经验教训 [lessons-learned/](./lessons-learned/)（6 份）

| 文档 | 主题 |
|------|------|
| [README.md](./lessons-learned/README.md) | 经验教训索引 |
| [testing/testability-iron-rules.md](./lessons-learned/testing/testability-iron-rules.md) | 可测试性铁律 |
| [layout/group-model-refactor.md](./lessons-learned/layout/group-model-refactor.md) | groupModel 重构 |
| [element-plus/dropdown-modal-occlusion.md](./lessons-learned/element-plus/dropdown-modal-occlusion.md) | 下拉遮挡问题 |

### 服务说明 [services/](./services/)（4 份）

| 文档 | 主题 |
|------|------|
| [README.md](./services/README.md) | 服务索引 |
| [useMetaList.md](./services/useMetaList.md) | useMetaList 服务 |
| [draftPersistService.md](./services/draftPersistService.md) | 草稿持久化 |
| [keyTemplateService.md](./services/keyTemplateService.md) | KeyTemplate 服务 |

### 复盘 [retrospectives/](./retrospectives/)（2 份）

| 文档 | 主题 |
|------|------|
| [2026-06-04-relation-scope-tree-bug.md](./retrospectives/2026-06-04-relation-scope-tree-bug.md) | 关系作用域树 bug |
| [2026-06-04-ui-color-issues.md](./retrospectives/2026-06-04-ui-color-issues.md) | UI 颜色问题 |

### 进度报告 [progress/](./progress/)（23 份，已归档）

历史进度报告，按版本号归档。

## 重要单文档

| 文档 | 主题 |
|------|------|
| [DEPLOYMENT_STANDARDS.md](./DEPLOYMENT_STANDARDS.md) | 部署标准 |
| [DIRECTORY_STRUCTURE.md](./DIRECTORY_STRUCTURE.md) | 目录结构 |
| [ENTERPRISE_PLATFORM_CAPABILITY_PLANNING.md](./ENTERPRISE_PLATFORM_CAPABILITY_PLANNING.md) | 企业平台能力规划 |
| [ENTERPRISE_UI_BENCHMARK.md](./ENTERPRISE_UI_BENCHMARK.md) | 企业 UI 基准 |
| [FRONTEND_V1_TO_V2_MIGRATION.md](./FRONTEND_V1_TO_V2_MIGRATION.md) | 前端 v1→v2 迁移 |
| [MIGRATION_TO_V2_PLAN.md](./MIGRATION_TO_V2_PLAN.md) | v2 迁移计划 |
| [SOP-USER-DEPLOYMENT.md](./SOP-USER-DEPLOYMENT.md) | 用户部署 SOP |
| [UI_COMPONENT_GUIDELINES.md](./UI_COMPONENT_GUIDELINES.md) | UI 组件指南 |
| [审计日志最佳实践.md](./audit-log-best-practices.md) | 审计日志最佳实践 |
| [CHANGELOG-2026-06-13-M1-phase2.md](./CHANGELOG-2026-06-13-M1-phase2.md) | M1+Phase 2 完成报告 (浅响应式 + 拆分前置 + MVU 抽取) |

## 旧版本与归档

历史文档已迁移至 [archive/](./archive/) 和 [superpowers/specs/](./superpowers/specs/)。

## 文档使用建议

1. **新会话开始** → 阅读 [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md)
2. **UI 开发** → [architecture/03-meta-driven-ui.md](./architecture/03-meta-driven-ui.md) + [UI_COMPONENT_GUIDELINES.md](./UI_COMPONENT_GUIDELINES.md)
3. **后端开发** → [architecture/04-api-contracts-v2.md](./architecture/04-api-contracts-v2.md) + 相关 spec
4. **新功能开发** → [需求Backlog.md](./requirements-backlog.md) + 相关 spec

## 维护说明

- 新增文档请遵循分类（架构/规范/进度/复盘）
- 过时文档请移至 [archive/](./archive/)
- 命名规范：小写中划线（待统一）
- 详细规范见 [DOCUMENTATION_STANDARDS.md](./DOCUMENTATION_STANDARDS.md)（待建立）
