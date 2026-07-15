# docs/INDEX.md

> **目标读者**: AI Agent / 任何要找文档的人
> **最后更新**: 2026-07-15
> **本文件用途**: docs/ 完整索引 (按类别)

---

## §0. 必读 (5 个)

| 文档 | 行数 | 一句话 |
|------|------|--------|
| [AGENT_INFRA.md](AGENT_INFRA.md) | ~80 | 5 分钟速查入口 |
| [../DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) | 331 | 部署/migration/远端 总入口 |
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | ~200 | migration 实战 (创建/跑/lint) |
| [STAGING_GUIDE.md](STAGING_GUIDE.md) | ~190 | staging 5 分钟上手 |
| [DEPLOYMENT_STANDARDS.md](DEPLOYMENT_STANDARDS.md) | 587 | 编码/部署/审计规范 |

---

## §1. 部署 / 运维 (本会话升级)

| 文档 | 用途 |
|------|------|
| [DEPLOY_HANDOVER_V007_44.md](DEPLOY_HANDOVER_V007_44.md) | 旧 V007.44 部署交接 |
| [DEPLOY_HANDOVER_V007_43.md](DEPLOY_HANDOVER_V007_43.md) | 旧 V007.43 部署交接 |
| [DEPLOY_HANDOVER_V007_20.md](DEPLOY_HANDOVER_V007_20.md) | 旧 V007.20 部署交接 |
| [DEPLOY_HANDOVER_V007_16.md](DEPLOY_HANDOVER_V007_16.md) | 旧 V007.16 部署交接 |
| [DEPLOY-MANUAL-20260630_002.md](DEPLOY-MANUAL-20260630_002.md) | 6/30 部署手册 v2 |
| [DEPLOY-MANUAL-20260630_001.md](DEPLOY-MANUAL-20260630_001.md) | 6/30 部署手册 v1 |
| [SOP-USER-DEPLOYMENT.md](SOP-USER-DEPLOYMENT.md) | 用户部署 SOP (955 行) |
| [DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) | **当前主入口** (2026-07-15 重写) |
| [STAGING_GUIDE.md](STAGING_GUIDE.md) | **当前 staging** (2026-07-15 重写) |
| [STAGING_DAY0_CHECKLIST.md](STAGING_DAY0_CHECKLIST.md) | staging day0 清单 |
| [STAGING_ENV_ANALYSIS.md](STAGING_ENV_ANALYSIS.md) | staging 环境分析 |
| [STAGING_V2_DETAILED_PLAN.md](STAGING_V2_DETAILED_PLAN.md) | staging V2 详细规划 |
| [NSFOCUS_L4_PROD_RESTART_RUNBOOK.md](NSFOCUS_L4_PROD_RESTART_RUNBOOK.md) | NSFOCUS L4 prod 重启 SOP |
| [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md) | 事故响应手册 |
| [PERFORMANCE_BASELINE.md](PERFORMANCE_BASELINE.md) | 性能基线 |
| [DEPLOYMENT_STANDARDS.md](DEPLOYMENT_STANDARDS.md) | **部署规范 v1.3+补遗** |
| [OPS_MANUAL.md](OPS_MANUAL.md) | 运维手册 |
| [UPLOAD-GUIDE-20260630_001.md](UPLOAD-GUIDE-20260630_001.md) | 上传指南 6/30 v1 |
| [UPLOAD-GUIDE-20260630_002.md](UPLOAD-GUIDE-20260630_002.md) | 上传指南 6/30 v2 |

## §2. Migration / Schema

| 文档 | 用途 |
|------|------|
| [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) | **当前 migration 实战 (2026-07-15 新建)** |
| [MIGRATION_SPEC.md](MIGRATION_SPEC.md) | 1711 行 design spec (历史 design, 不必读) |
| [MIGRATION_TO_V2_PLAN.md](MIGRATION_TO_V2_PLAN.md) | 迁移到 V2 计划 |
| [SPEC_PG_MIGRATION.md](SPEC_PG_MIGRATION.md) | PostgreSQL 迁移 spec |
| [V007_45_FIX_PLAN.md](V007_45_FIX_PLAN.md) | V007.45 修复计划 |

## §3. spec/ (业务 spec, 150+)

| 类别 | 路径 |
|------|------|
| 业务功能 | [specs/spec-*.md](specs/) (120+ 个) |
| 阶段规划 | [specs/spec-phase1-*.md](specs/), [specs/spec-phase2-*.md](specs/) 等 |
| 后端研究 | [specs/spec-m2-*.md](specs/), [specs/spec-m9-*.md](specs/) 等 |
| 审计日志 | [specs/object-audit-log-*.md](specs/), [specs/spec-audit-log-*.md](specs/) |
| 查询引擎 | [specs/spec-query-engine-*.md](specs/) (8 个) |
| 权限体系 | [specs/spec-fr-ui-007-*.md](specs/) 等 |

## §4. superpowers/ (设计 + 计划)

| 类别 | 路径 |
|------|------|
| 规格 | [superpowers/specs/](superpowers/specs/) |
| 计划 | [superpowers/plans/](superpowers/plans/) |
| 含 2026-07-14-deploy-infra-todo-spec | [superpowers/specs/2026-07-14-deploy-infra-todo-spec.md](superpowers/specs/2026-07-14-deploy-infra-todo-spec.md) |
| 含 smart-delta-deploy | [superpowers/specs/2026-07-14-smart-delta-deploy-design.md](superpowers/specs/2026-07-14-smart-delta-deploy-design.md) |

## §5. 测试

| 文档 | 用途 |
|------|------|
| [testing-strategy.md](testing-strategy.md) | 测试策略 |
| [testability/](testability/) | 可测试性分析 (4 个) |
| [test-backlog.md](test-backlog.md) | 测试 backlog |
| [test-fusion-plan.md](test-fusion-plan.md) | 测试融合计划 |
| [TEST-MIGRATION-GUIDE.md](TEST-MIGRATION-GUIDE.md) | 测试迁移指南 |
| [TEST-OPTIMIZATION-PLAN.md](TEST-OPTIMIZATION-PLAN.md) | 测试优化计划 |

## §6. 安全 / 合规

| 文档 | 用途 |
|------|------|
| [SECURITY_WHITELIST_REQUEST_2026-07-14.md](SECURITY_WHITELIST_REQUEST_2026-07-14.md) | 白名单请求 |
| [V4_L16_PATCH.md](V4_L16_PATCH.md) | V4 L16 补丁 |
| [V4_REFACTOR.md](V4_REFACTOR.md) | V4 重构 |
| [V4_COMPATIBILITY_REPORT.md](V4_COMPATIBILITY_REPORT.md) | V4 兼容性报告 |
| [violations/](violations/) | 合规违规记录 |
| [NSFOCUS_REMEDIATION_PLAN.md](NSFOCUS_REMEDIATION_PLAN.md) | NSFOCUS 整改计划 |

## §7. 用户指南

| 文档 | 用途 |
|------|------|
| [user-guide-design.md](user-guide-design.md) | 用户指南设计 |
| [user-guide-integration.md](user-guide-integration.md) | 用户指南集成 |
| [UI_COMPONENT_GUIDELINES.md](UI_COMPONENT_GUIDELINES.md) | UI 组件指南 |
| [UI_COMPONENT_LIBRARY_ANALYSIS.md](UI_COMPONENT_LIBRARY_ANALYSIS.md) | UI 组件库分析 |
| [ui-design-qa.md](ui-design-qa.md) | UI 设计 QA |
| [services/](services/) | 服务文档 (4 个) |

## §8. Todo / 计划 / 变更

| 文档 | 用途 |
|------|------|
| [TODOS.md](TODOS.md) | 全部 TODO 总览 |
| [TODO_LONGTERM.md](TODO_LONGTERM.md) | 长期 TODO |
| [TODO-2026-06-10-sorting-fix.md](TODO-2026-06-10-sorting-fix.md) | 排序修复 TODO |
| [TECH-DEBT.md](TECH-DEBT.md) | 技术债 |
| [todo/v3.18-tech-debt-todo.md](todo/v3.18-tech-debt-todo.md) | V3.18 技术债 |
| [todos/arch-improve-unified-field-permission.md](todos/arch-improve-unified-field-permission.md) | 统一字段权限改进 |
| [SPEC_V007.41.md](SPEC_V007.41.md) | V007.41 spec |

## §9. 评审 / 二次评审

| 文档 | 用途 |
|------|------|
| [SECOND_REVIEW_V007_44.md](SECOND_REVIEW_V007_44.md) | V007.44 二次评审 |
| [SECOND_REVIEW_V007_44_LOCATIONS.md](SECOND_REVIEW_V007_44_LOCATIONS.md) | 二次评审位置 |
| [SECOND_REVIEW_V007_44_CORRECTION.md](SECOND_REVIEW_V007_44_CORRECTION.md) | 二次评审更正 |
| [V050_L4_5_audit_async_design.md](V050_L4_5_audit_async_design.md) | V050 L4.5 审计异步设计 |

## §10. 数据 / 模型

| 文档 | 用途 |
|------|------|
| [SQLITE_IO_ERROR_DESIGN.md](SQLITE_IO_ERROR_DESIGN.md) | SQLite IO 错误设计 |
| [spec-sqlite-corruption-fix.md](spec-sqlite-corruption-fix.md) | SQLite 损坏修复 spec |
| [unified-model-analysis.md](unified-model-analysis.md) | 统一模型分析 |
| [unified-model-refactor-plan.md](unified-model-refactor-plan.md) | 统一模型重构计划 |
| [service-module-diagram-analysis.md](service-module-diagram-analysis.md) | 服务模块图分析 |
| [yonyou-bip-permission-research.md](yonyou-bip-permission-research.md) | 用友 BIP 权限研究 |
| [trae-ide-write-wrapper.md](trae-ide-write-wrapper.md) | Trae IDE 写包装器 |

## §11. 权限体系专项

| 文档 | 用途 |
|------|------|
| [spec-permission-metadata-driven.md](spec-permission-metadata-driven.md) | 权限元数据驱动 |
| [spec-permission-derivation-*.md](spec-permission-derivation-MASTER-PLAN-2026-06-08.md) 等 4 个 | 权限派生 master plan |
| [spec_权限体系升级/](spec_权限体系升级/) | 权限升级 7 步 (7 文件) |
| [spec_role_permission_granular_control.md](spec_role_permission_granular_control.md) | 角色权限细粒度控制 |
| [spec_data_permission_unified_model.md](spec_data_permission_unified_model.md) | 数据权限统一模型 |

---

## §12. 文档维护原则

1. **新功能/能力变更** → 改 [../DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) + [AGENT_INFRA.md](AGENT_INFRA.md) + 本 INDEX
2. **migration 实战** → 改 [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
3. **staging 变更** → 改 [STAGING_GUIDE.md](STAGING_GUIDE.md)
4. **deploy spec** → 改 [DEPLOYMENT_STANDARDS.md](DEPLOYMENT_STANDARDS.md)
5. **业务 spec** → 放 [specs/](specs/) 或 [superpowers/specs/](superpowers/specs/)

---

**总入口**: [AGENT_INFRA.md](AGENT_INFRA.md) 5 分钟 → [../DEPLOY_INFRASTRUCTURE.md](../DEPLOY_INFRASTRUCTURE.md) 总览 → 按需深入
