# 权限体系专题待办 (Permission System TODOs)

> **更新日期**: 2026-06-26
> **依据**: 全量 [docs/specs/](../specs/) + [docs/auth/](../auth/) + [docs/PERMISSION_SYSTEM_INDEX.md](../PERMISSION_SYSTEM_INDEX.md) + [docs/BACKLOG-Permission-System-Improvement.md](../BACKLOG-Permission-System-Improvement.md) 状态盘点
> **当前体系** (3 层并存, 部分重叠):
>   1. **M11 声明式 RLS** (rls_rules/*.yaml + rls/loader.py) - v1.4.0 已 130% 完成
>   2. **DimensionScopeEngine** (运行时派生, 实际主路径)
>   3. **DataPermissionService** (旧表, role_data_permissions/group_data_permissions)
> **核心架构债**: 3 层权限体系并存, 拦截器 [DECORATIVE] 标记未清除, dimension scope SSOT 不一致

---

## 🔴 P0 - 紧急 (已修复待 PR / 用户阻塞)

### P0.1 BUG-V026 owner exception 对子对象 SQL 错误
- **现象**: `/api/v2/bo/domain?version_id=764&page_size=1000` → 400
  - 错误消息: `"no such column: product_id"`
- **影响**: TEST333 (普通 user) 无法查看 domain/sub_domain
- **根因**: `data_permission_interceptor._add_owner_exception` (L907-919) 对子对象用 `field='product_id'` 直查, 但 domain/sub_domain/service_module/business_object 表无 product_id 列
- **修复**: 改用 `chain_owner_resolver.build_owner_exception_subquery` 构造 chain SQL
- **测试**: ✅ `meta/tests/test_bug_v026.py`, ✅ `meta/tests/test_v020_v027_regression.py`
- **状态**: 修复已 staged, 需 PR 合并
- **关联 spec**: 无 (属于 BUG 修复)

---

## 🟠 P1 - 重要 (体系性问题, 1-2 周可解)

### P1.1 三层权限体系统一 (核心架构债)
- **现状**:
  - M11 (rls_rules/*.yaml) 130% 完成 (155 PASS 测试)
  - 但 domain/sub_domain 实际走 DimensionScopeEngine
  - M11 仍是 [DECORATIVE] 标记, 主路径仍是 DimensionScopeEngine
- **风险**:
  - admin 行 M11: `condition: "true"`
  - admin 行 DimensionScope: 用 `role_dimension_scopes` 派生 `id IN (...)`
  - 两套规则未必一致, 可能产生权限泄漏
- **方向**:
  - 让 M11 YAML 成为 SSOT (Single Source of Truth)
  - DimensionScopeEngine 退化为"维值过滤器" (只负责从 role_dimension_scopes 读 dim value 列表)
  - 拦截器统一从 rls.get_active_row_filter 读 row filter
- **关联 spec**:
  - [spec-m11-rls-implementation.md v1.4.0](../specs/spec-m11-rls-implementation.md) (D1-D5 + TODO-1+2+3+4+5+6 全部完成, 仅 TODO-7 M10 协同留待)
  - [spec-permission-derivation-MASTER-PLAN-2026-06-08.md](../specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md) (v1.0.1 spec + v1.1 spec + v1.2 spec + MASTER PLAN 4 文档齐全)
  - [spec_权限体系升级/05_rfc_detailed_design.md](../spec_权限体系升级/05_rfc_detailed_design.md) (RFC 详细设计)
- **文件**:
  - `rls_rules/{domain,sub_domain,service_module,business_object,version,product}.yaml`
  - `meta/services/dimension_scope_engine.py`
  - `meta/core/interceptors/permission_interceptor.py` (L582 _check_yaml_row_filter)
  - `meta/core/interceptors/data_permission_interceptor.py` (L907-919)
- **状态**: M11 仍是 [DECORATIVE]
- **优先级**: P1 (高)

### P1.2 废弃 data_permissions 旧表
- **现状**:
  - `role_data_permissions` / `group_data_permissions` 表已为空 (0 条数据)
  - 但 `DataPermissionService.get_allowed_resource_ids()` 仍在查这些表
- **方向**:
  - 确认无遗留数据, 写迁移脚本
  - `DataPermissionService` 内部调 `DimensionScopeEngine` (P1.1 完成后)
  - DROP TABLE role_data_permissions / group_data_permissions
- **文件**: `meta/services/data_permission_service.py`, 数据库迁移脚本
- **关联 spec**: [BACKLOG-Permission-System-Improvement.md](../BACKLOG-Permission-System-Improvement.md) P2 PERM-005
- **状态**: 待处理
- **优先级**: P1 (中)

### P1.3 关系 BO 权限改为运行时派生 (Phase 2)
- **现状**: `ASSOCIATION_BOS` 将 relationship 权限写死到 `role_permissions` 表
- **方向**: 改为运行时派生 (用户访问 relationship → 后端查 source 端点权限 → 通过则放行)
- **关联 spec**:
  - [spec-permission-association-derivation-2026-06-08-v1.0.md](../specs/spec-permission-association-derivation-2026-06-08-v1.0.md) (m2m / polymorphic / self_ref / reverse / sibling 5 种关联)
  - [spec-permission-derivation-parent-read-2026-06-08-v1.1.md](../specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md) (FR-007 FK 元数据 yaml 化 + FR-008 启动一致性校验 + FR-009 可观测测导出)
- **文件**: `meta/core/interceptors/permission_interceptor.py`, `meta/services/dimension_scope_engine.py`
- **状态**: 关联 spec 已写, 待实施
- **优先级**: P1

### P1.4 spec-permission-derivation-MASTER-PLAN 落地
- **现状**: MASTER-PLAN v1.0.1 文档齐全 (v1.0.1 + v1.1 + v1.2 4 文档)
- **方向**: 按 MASTER-PLAN 9 步骤实施 (MetaAction.ACTION_SUFFIX_MAP → PermissionSyncService → MenuAutoGenerator → role_dimension_scope.yaml → DimensionScopeEngine → /api/v1/menu/visible → /api/v1/roles/{id}/dimension-scopes → /api/v1/roles/{id}/derived-permissions → role_menu_api.py 清理)
- **文件**: `meta/core/models.py`, `meta/services/permission_sync_service.py`, `meta/api/menu_auto_generator.py`, `role_dimension_scope.yaml`
- **总工时**: 13-17 天 (含 buffer)
- **状态**: 文档齐备, 实施待启动
- **优先级**: P1 (高)

### P1.5 M11 RLS 内部表未完全集成测试
- **现状**: rls_rules/ 36 BO yaml 全覆盖
  - ✅ `audit_log`, `ai_async_task`, `change_event`, `permission/role/user_group` 有 yaml
  - ❌ `task_execution`, `task_queue`, `scheduled_task` 缺集成测试
- **风险**: 内部表走 native permission 路径, 跟 M11 不一致
- **方向**: 所有 BO 都走 M11 RLS, 统一拦截器
- **优先级**: P1

### P1.6 Dimension Scope 和 Condition 支持 `*` 通配符
- **现状**: 功能权限支持 `*`（超级管理员），但 dimension scope 和 condition 不支持
- **风险**: 无法表达"全量维度"的合法场景，admin 需逐个配置所有维度值
- **方向**: 扩展 role_dimension_scopes 支持 scope_mode='all'，condition 支持 '*'
- **关联**: [WILDCARD_SUPPORT_RESEARCH.md](WILDCARD_SUPPORT_RESEARCH.md), INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md 6.3.10
- **状态**: 研究完成，待实施
- **优先级**: P1 (中)

---

## 🟡 P2 - 评估 (历史 TODO 重新审视 + BACKLOG)

### P2.1 历史拦截器端点 (低风险, 来自原 TODOS.md)
| # | 端点 | 风险 | 关联 spec | 备注 |
|---|------|------|----------|------|
| 2.1 | /api/v1/relationships | 中 | - | 临时修复 (L89-117) 仍生效, 待 v2 迁移 |
| 2.2 | query_associations 端点 | 低 | - | association 树受限 |
| 2.3 | retrieve_with_associations | 低 | - | 内部 read() 应用 scope |
| 2.4 | /api/v1/business_object/{id}/relations | 低 | - | 数据特性保护 (version 全覆盖) |
| 2.5 | /api/v2/bo/architecture/preview | 中 | - | 用户传 ID 可绕过 |
| 2.6 | /api/v1/analytics/{type} | 低 | - | 分析数据非敏感 |

### P2.2 is_query_action 补充 association actions
- **现状**: `is_query_action=False` → 拦截器 early return
- **方向**: 扩展 `ActionContext.is_query_action` 或在 `DataPermissionInterceptor.before_action` 中单独处理
- **文件**: `meta/core/action_context.py`, `meta/core/interceptors/data_permission_interceptor.py`
- **关联 spec**: P1.3 同步
- **状态**: 待评估
- **优先级**: P2 (中)

### P2.3 菜单过滤加入 dimension scope
- **现状**: 菜单可见性只看 permission code, 不看 dimension scope 范围
- **现状**: 方案 A (接受现状) — TEST60 看到 4 个菜单是正确的
- **文件**: `meta/api/menu_permission_api.py`
- **关联 spec**: spec_权限体系升级/06_rfc_impl_test_tbd.md Step 6 GET /api/v1/menu/visible
- **状态**: 方案 A 接受
- **优先级**: P2 (低)

### P2.4 导入导出端点无 dim scope 过滤
- **现状**: `useImportExportApi.js` / `boExportImportService.exportData()` 无 dim scope 过滤
- **现状**: ExportDialog 当前不向用户开放
- **方向**: 导出时传入 `dimension_scope` 参数, 后端过滤
- **文件**: `src/services/useImportExportApi.js`, `src/services/boExportImportService.js`
- **关联 spec**: spec_权限体系升级 Step 8
- **状态**: 待处理
- **优先级**: P2 (中)

### P2.5 BACKLOG-Permission-System-Improvement.md (2026-05-08 创, 长期规划)
- **PERM-001 引入系统级权限** (P1, 0.5d)
  - 业务权限控制 vs 系统级权限 (system:manage)
  - 验收: `system:manage` 权限 + 菜单权限重配置
- **PERM-002 权限集机制 (临时授权)** (P1, 5d)
  - 临时项目访问, 跨部门门岗
  - YAML 配置: `permission_set` 块 (id/name/permissions/constraints)
  - 约束: 审批流程, 时效控制, 完整审计, SoD 检查
- **PERM-005 (推测) 废弃 data_permissions 旧表** (P2, 已在 P1.2 列出)
- **完整 BACKLOG**: [BACKLOG-Permission-System-Improvement.md](../BACKLOG-Permission-System-Improvement.md) (2026-05-08 创建, 待规划)

---

## 🟢 P3 - 已完成 + 待回顾 (历史成果, 需要审计)

### P3.1 M11 RLS D1-D5 + TODO 1-6 全部完成
- **M11 v1.4.0** (`spec-m11-rls-implementation.md`)
  - D1: YAML 加载器 (`rls/loader.py`) - 24 PASS
  - D2: 高层 API (`rls/enforce.py`) - 23 PASS
  - D3: 集成示例 (`rls/examples/`) - 15 PASS
  - D4: AI Agent 角色 (`permission_interceptor.py` +12 行)
  - D5: 文档同步
  - TODO-1: AI Agent 集成测试 (19 PASS)
  - TODO-2: 3 拦截器真实集成 (22 PASS)
  - TODO-3: 配置热加载 (`rls/hot_reload.py`) (9 PASS)
  - TODO-4: 5x5 场景矩阵 (14 PASS)
  - TODO-5: DSL 解析 (`rls/dsl.py`) (21 PASS)
  - TODO-6: 10 entity YAML (8 PASS)
- **遗留**: TODO-7 (M10 协同) 留待
- **状态**: ✅ 130% 完成, 155 PASS

### P3.2 spec-permission-derivation-parent-read-2026-06-08 (v1.0 + v1.1)
- **v1.0.1 spec**: 角色权限推导 + 父读校验 (audit-only) + 链中 read 校验 + read/list 合并 + 菜单 2 态
- **v1.1 spec**: + FR-007 FK 元数据 yaml 化 + FR-008 启动一致性校验 + FR-009 可观测测导出
- **状态**: spec 已批准, 实施待启动 (P1.4)

### P3.3 spec-permission-association-derivation-2026-06-08 v1.0
- **覆盖**: 5 种非 parent 关联 (m2m / polymorphic / self_reference / reverse 1:N / sibling BO)
- **对标**: SAP CDS Association + DEFINE HIERARCHY / Oracle FK + REFERENCES + REF column / Odoo Many2many / fields.Reference / Mendix 关联
- **状态**: spec 已批准, 实施待启动 (P1.3)

### P3.4 spec-permission-ux-transparency-2026-06-09 v1.0
- **主题**: 权限派生 UX 透明化
- **状态**: 设计完成, 待实施

### P3.5 spec-auth-object-category-v2-2026-06-10 v2.1
- **主题**: Auth 元对象模型简化 (V1 清理 + V2+ 渐进)
- **状态**: 📋 Designed — 待评审 (按"先简单满足基本上线"原则拆阶段)

### P3.6 M11 体系下 dimension scope 表设计 (role_dimension_scope.yaml)
- **状态**: ✅ 已实现 (P1.4 Step 4 完成)
- **后续**: spec_权限体系升级 06_rfc_impl_test_tbd.md Step 5 DimensionScopeEngine 集成

### P3.7 PermissionSyncService
- **状态**: ✅ 已实现
- **位置**: `meta/services/permission_sync_service.py`
- **后续**: spec_权限体系升级 06_rfc_impl_test_tbd.md Step 2

### P3.8 MenuAutoGenerator + menu.yaml
- **状态**: ✅ 已实现
- **后续**: spec_权限体系升级 06_rfc_impl_test_tbd.md Step 3

---

## 🔵 P4 - 远期规划 (来自 spec-backlog.md)

### P4.1 Record Type 设计
- **现状**: 待设计
- **关联 spec**: [research-yaml-config-boundary.md §10](../specs/research-yaml-config-boundary.md) (配置级核心承载体)
- **优先级**: P4 (远期)

### P4.2 Action Types 设计 (AI Agent 操作契约)
- **现状**: 待设计
- **关联 spec**: [research-yaml-config-boundary.md §14-15](../specs/research-yaml-config-boundary.md) (Palantir 深度分析)
- **优先级**: P4

### P4.3 多租户隔离
- **现状**: 远期 Phase 5+
- **方向**: 租户数据隔离与权限控制
- **优先级**: P4

### P4.4 审计增强 (合规报告)
- **现状**: 远期 Phase 5+
- **方向**: 完整变更追踪 + 合规报告生成
- **优先级**: P4

---

## 📦 权限相关 Spec 完整清单 (盘点结果 2026-06-26)

### 🔴 已实施 (活跃规范)

| Spec 文档 | 主题 | 状态 |
|----------|------|------|
| [auth-permission-system-design.md](../auth-permission-system-design.md) | 认证权限系统设计 | 活跃 |
| [spec_data_permission_unified_model.md](../specs/spec_data_permission_unified_model.md) | 数据权限统一模型 | 活跃 |
| [spec_role_permission_granular_control.md](../specs/spec_role_permission_granular_control.md) | 角色权限粒度控制 | 活跃 |
| [rfc_action_service_unified_model.md](../rfc_action_service_unified_model.md) | 动作服务统一模型 | 活跃 |
| [data-permission-field-attributes-mapping.md](../data-permission-field-attributes-mapping.md) | 数据权限字段映射 | 活跃 |
| [data-permission-inheritance-model.md](../data-permission-inheritance-model.md) | 数据权限继承模型 | 活跃 |
| [permission-ssot-analysis.md](../permission-ssot-analysis.md) | 单一事实源分析 | 活跃 |
| [permission-config-optimization.md](../permission-config-optimization.md) | 配置流程优化 | 活跃 |

### 🟡 M11 RLS (v1.4.0 130% 完成)

| Spec 文档 | 状态 |
|----------|------|
| [spec-m11-rls-implementation.md v1.4.0](../specs/spec-m11-rls-implementation.md) | ✅ D1-D5 + TODO-1+2+3+4+5+6 全部完成, TODO-7 M10 协同留待 |

### 🟡 Permission Derivation 体系 (MASTER-PLAN 文档齐备)

| Spec 文档 | 主题 | 状态 |
|----------|------|------|
| [spec-permission-derivation-MASTER-PLAN-2026-06-08.md](../specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md) v1.0.1 | 整体 Master Plan | 可执行 (4 文档齐全) |
| [spec-permission-derivation-parent-read-2026-06-08-v1.0.md](../specs/spec-permission-derivation-parent-read-2026-06-08-v1.0.md) | v1.0.1 spec | 已批准 |
| [spec-permission-derivation-parent-read-2026-06-08-v1.1.md](../specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md) | v1.1 spec | 已批准 |
| [spec-permission-association-derivation-2026-06-08-v1.0.md](../specs/spec-permission-association-derivation-2026-06-08-v1.0.md) | 5 种关联派生 | 已批准 |
| [spec-permission-ux-transparency-2026-06-09-v1.0.md](../specs/spec-permission-ux-transparency-2026-06-09-v1.0.md) | UX 透明化 | 设计完成 |

### 🟡 权限体系升级 RFC (7 文档系列)

| Spec 文档 | 主题 |
|----------|------|
| [spec_权限体系升级/01_background.md](../spec_权限体系升级/01_background.md) | 背景分析 |
| [spec_权限体系升级/02_fr.md](../spec_权限体系升级/02_fr.md) | 需求规格 (FR-001 ~ FR-015) |
| [spec_权限体系升级/03_nfr_if_tr_constraints.md](../spec_权限体系升级/03_nfr_if_tr_constraints.md) | 约束 |
| [spec_权限体系升级/04_rfc_analysis.md](../spec_权限体系升级/04_rfc_analysis.md) | RFC 分析 (As-Is / To-Be) |
| [spec_权限体系升级/05_rfc_detailed_design.md](../spec_权限体系升级/05_rfc_detailed_design.md) | RFC 详细设计 |
| [spec_权限体系升级/06_rfc_impl_test_tbd.md](../spec_权限体系升级/06_rfc_impl_test_tbd.md) | 实施测试 (9 步骤) |
| [spec_权限体系升级/07_supplement_fr016_tbd.md](../spec_权限体系升级/07_supplement_fr016_tbd.md) | 补充 FR-016 (PermissionConfigPanel 维度驱动 UI 适配) |

### 🟡 元数据驱动权限方案设计

| Spec 文档 | 主题 |
|----------|------|
| [permission-metadata-driven-solution.md](../permission-metadata-driven-solution.md) | 元数据驱动权限体系方案 (入口文档) |
| [permission-metadata-driven-optimization.md](../permission-metadata-driven-optimization.md) | 优化方案 |
| [permission-metadata-driven-refinement.md](../permission-metadata-driven-refinement.md) | 细化方案 |
| [permission-metadata-driven-design.md](../permission-metadata-driven-design.md) | 细化方案设计 |
| [spec-permission-metadata-driven.md](../specs/spec-permission-metadata-driven.md) | 元数据驱动化规格 |
| [meta-action-permission-analysis.md](../meta-action-permission-analysis.md) | 深度分析 |

### 🟡 竞品对比 + 友商研究

| Spec 文档 | 主题 |
|----------|------|
| [competitive-analysis-metadata-permission.md](../competitive-analysis-metadata-permission.md) | 竞品分析 |
| [yonyou-bip-permission-research.md](../yonyou-bip-permission-research.md) | 用友 BIP 权限模型 |
| [enterprise-security-architecture-analysis.md](../enterprise-security-architecture-analysis.md) | 企业安全架构分析 |
| [sap-deep-authorization-analysis.md](../sap-deep-authorization-analysis.md) | SAP 深度分析 |
| [sap-salesforce-field-level-security-analysis.md](../sap-salesforce-field-level-security-analysis.md) | SAP/ Salesforce 字段级安全 |
| [research/head-product-metadata-permission-research.md](../research/head-product-metadata-permission-research.md) | 头部产品元数据权限研究 |

### 🟡 测试 / 审计 / 报告

| Spec 文档 | 主题 |
|----------|------|
| [PERMISSION_TEST_REPORT.md](../PERMISSION_TEST_REPORT.md) | 权限测试报告 |
| [permission-testing-framework-spec.md](../specs/permission-testing-framework-spec.md) | 权限体系自动化测试框架 |
| [audit-log-best-practices.md](../audit-log-best-practices.md) | 审计日志最佳实践 |
| [BACKLOG-Permission-System-Improvement.md](../BACKLOG-Permission-System-Improvement.md) | 改进待办 (2026-05-08) |

### 🟡 auth/ 子目录 (3 文档)

| Spec 文档 | 主题 |
|----------|------|
| [auth/write-scope-interceptor.md](../auth/write-scope-interceptor.md) | Write Scope 拦截器 |
| [auth/role-templates.md](../auth/role-templates.md) | 角色模板 |
| [auth/role-migration-guide.md](../auth/role-migration-guide.md) | 角色迁移指南 |

### 🟡 其他涉及权限的 Spec

| Spec 文档 | 主题 | 关联 |
|----------|------|------|
| [spec-auth-object-category-v2-2026-06-10.md v2.1](../specs/spec-auth-object-category-v2-2026-06-10.md) | Auth 元对象模型简化 | V1 清理 + V2+ 渐进 |
| [spec-fr-ui-007-008-009-permission-system.md](../specs/spec-fr-ui-007-008-009-permission-system.md) | FR-UI 7/8/9 权限系统 | 📋 Designed — 待实施 |
| [permission-metadata-driven.md](../specs/spec-permission-metadata-driven.md) | 元数据驱动化规格 | - |
| [spec-phase1-p0-detailed-design.md](../specs/spec-phase1-p0-detailed-design.md) | Phase 1 P0 重新设计 (Reworked — BO Action First) | 📋 |
| [spec-phase1-safe-execution.md](../specs/spec-phase1-safe-execution.md) | Phase 1 安全执行守则 | 📋 |
| [spec-phase1-security-performance-critical.md](../specs/spec-phase1-security-performance-critical.md) | Phase 1 安全性能关键 | - |
| [spec-phase2-code-quality-deep-dive.md](../specs/spec-phase2-code-quality-deep-dive.md) | Phase 2 代码质量深入 (待确认) | - |
| [spec-perf-optimization-2026-06-08-v1.0.md](../specs/spec-perf-optimization-2026-06-08-v1.0.md) | 性能优化 (含权限检查性能) | - |
| [spec-soft-delete.md](../specs/spec-soft-delete.md) | ⚠️ 已废弃 (由 spec-audit-log-recovery 替代) | - |
| [spec-audit-log-recovery.md](../specs/spec-audit-log-recovery.md) | 审计日志恢复 (取代 Soft Delete) | 设计中 |
| [spec-audit-log-v2-action-aware.md](../specs/spec-audit-log-v2-action-aware.md) | Audit Log v2 Action-aware | 📋 草案 (Draft) |

---

## 📊 权限体系待办汇总

| 优先级 | 数量 | 状态 |
|--------|------|------|
| P0 紧急 | 1 | BUG-V026 待 PR 合并 |
| P1 重要 | 5 | 三层统一 + MASTER-PLAN 落地 + 旧表废弃 + 关联派生 + 内部表测试 |
| P2 评估 | 4 | 历史拦截器 + is_query_action + 菜单 + 导入导出 + BACKLOG PERM-001/002 |
| P3 已完成 | 8 | M11 D1-D5 + TODO 1-6 + 5 个 spec 文档已批 + SyncService + MenuAutoGenerator |
| P4 远期 | 4 | Record Type + Action Types + 多租户 + 审计增强 |

**权限相关 Spec 总数**: 38 个 (含 7 文档系列 + M11 + 5 个 Permission Derivation + 2 个 Research + 6 个方案设计 + 8 个活跃规范 + 2 个测试 + 4 个远期 + 2 个 backlog + 1 个 phase1 spec)

---

## 🎯 下一周权限体系建议 (2026-06-27 ~ 2026-07-03)

1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
| [spec-soft-delete.md](../specs/spec-soft-delete.md) | ⚠️ 已废弃 (由 spec-audit-log-recovery 替代) | - |
| [spec-audit-log-recovery.md](../specs/spec-audit-log-recovery.md) | 审计日志恢复 (取代 Soft Delete) | 设计中 |
| [spec-audit-log-v2-action-aware.md](../specs/spec-audit-log-v2-action-aware.md) | Audit Log v2 Action-aware | 📋 草案 (Draft) |

---

## 📊 权限体系待办汇总

| 优先级 | 数量 | 状态 |
|--------|------|------|
| P0 紧急 | 1 | BUG-V026 待 PR 合并 |
| P1 重要 | 5 | 三层统一 + MASTER-PLAN 落地 + 旧表废弃 + 关联派生 + 内部表测试 |
| P2 评估 | 4 | 历史拦截器 + is_query_action + 菜单 + 导入导出 + BACKLOG PERM-001/002 |
| P3 已完成 | 8 | M11 D1-D5 + TODO 1-6 + 5 个 spec 文档已批 + SyncService + MenuAutoGenerator |
| P4 远期 | 4 | Record Type + Action Types + 多租户 + 审计增强 |

**权限相关 Spec 总数**: 38 个 (含 7 文档系列 + M11 + 5 个 Permission Derivation + 2 个 Research + 6 个方案设计 + 8 个活跃规范 + 2 个测试 + 4 个远期 + 2 个 backlog + 1 个 phase1 spec)

---

## 🎯 下一周权限体系建议 (2026-06-27 ~ 2026-07-03)

1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
| [spec-soft-delete.md](../specs/spec-soft-delete.md) | ⚠️ 已废弃 (由 spec-audit-log-recovery 替代) | - |
| [spec-audit-log-recovery.md](../specs/spec-audit-log-recovery.md) | 审计日志恢复 (取代 Soft Delete) | 设计中 |
| [spec-audit-log-v2-action-aware.md](../specs/spec-audit-log-v2-action-aware.md) | Audit Log v2 Action-aware | 📋 草案 (Draft) |

---

## 📊 权限体系待办汇总

| 优先级 | 数量 | 状态 |
|--------|------|------|
| P0 紧急 | 1 | BUG-V026 待 PR 合并 |
| P1 重要 | 5 | 三层统一 + MASTER-PLAN 落地 + 旧表废弃 + 关联派生 + 内部表测试 |
| P2 评估 | 4 | 历史拦截器 + is_query_action + 菜单 + 导入导出 + BACKLOG PERM-001/002 |
| P3 已完成 | 8 | M11 D1-D5 + TODO 1-6 + 5 个 spec 文档已批 + SyncService + MenuAutoGenerator |
| P4 远期 | 4 | Record Type + Action Types + 多租户 + 审计增强 |

**权限相关 Spec 总数**: 38 个 (含 7 文档系列 + M11 + 5 个 Permission Derivation + 2 个 Research + 6 个方案设计 + 8 个活跃规范 + 2 个测试 + 4 个远期 + 2 个 backlog + 1 个 phase1 spec)

---

## 🎯 下一周权限体系建议 (2026-06-27 ~ 2026-07-03)

1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
| [spec-soft-delete.md](../specs/spec-soft-delete.md) | ⚠️ 已废弃 (由 spec-audit-log-recovery 替代) | - |
| [spec-audit-log-recovery.md](../specs/spec-audit-log-recovery.md) | 审计日志恢复 (取代 Soft Delete) | 设计中 |
| [spec-audit-log-v2-action-aware.md](../specs/spec-audit-log-v2-action-aware.md) | Audit Log v2 Action-aware | 📋 草案 (Draft) |

---

## 📊 权限体系待办汇总

| 优先级 | 数量 | 状态 |
|--------|------|------|
| P0 紧急 | 1 | BUG-V026 待 PR 合并 |
| P1 重要 | 5 | 三层统一 + MASTER-PLAN 落地 + 旧表废弃 + 关联派生 + 内部表测试 |
| P2 评估 | 4 | 历史拦截器 + is_query_action + 菜单 + 导入导出 + BACKLOG PERM-001/002 |
| P3 已完成 | 8 | M11 D1-D5 + TODO 1-6 + 5 个 spec 文档已批 + SyncService + MenuAutoGenerator |
| P4 远期 | 4 | Record Type + Action Types + 多租户 + 审计增强 |

**权限相关 Spec 总数**: 38 个 (含 7 文档系列 + M11 + 5 个 Permission Derivation + 2 个 Research + 6 个方案设计 + 8 个活跃规范 + 2 个测试 + 4 个远期 + 2 个 backlog + 1 个 phase1 spec)

---

## 🎯 下一周权限体系建议 (2026-06-27 ~ 2026-07-03)

1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
| [spec-soft-delete.md](../specs/spec-soft-delete.md) | ⚠️ 已废弃 (由 spec-audit-log-recovery 替代) | - |
| [spec-audit-log-recovery.md](../specs/spec-audit-log-recovery.md) | 审计日志恢复 (取代 Soft Delete) | 设计中 |
| [spec-audit-log-v2-action-aware.md](../specs/spec-audit-log-v2-action-aware.md) | Audit Log v2 Action-aware | 📋 草案 (Draft) |

---

## 📊 权限体系待办汇总

| 优先级 | 数量 | 状态 |
|--------|------|------|
| P0 紧急 | 1 | BUG-V026 待 PR 合并 |
| P1 重要 | 5 | 三层统一 + MASTER-PLAN 落地 + 旧表废弃 + 关联派生 + 内部表测试 |
| P2 评估 | 4 | 历史拦截器 + is_query_action + 菜单 + 导入导出 + BACKLOG PERM-001/002 |
| P3 已完成 | 8 | M11 D1-D5 + TODO 1-6 + 5 个 spec 文档已批 + SyncService + MenuAutoGenerator |
| P4 远期 | 4 | Record Type + Action Types + 多租户 + 审计增强 |

**权限相关 Spec 总数**: 38 个 (含 7 文档系列 + M11 + 5 个 Permission Derivation + 2 个 Research + 6 个方案设计 + 8 个活跃规范 + 2 个测试 + 4 个远期 + 2 个 backlog + 1 个 phase1 spec)

---

## 🎯 下一周权限体系建议 (2026-06-27 ~ 2026-07-03)

1. **【必做】合并 BUG-V026 修复** (用户已阻塞)
2. **【必做】P1.4 spec-permission-derivation-MASTER-PLAN 启动** (Step 1-3, 3-5d)
3. **【必做】P1.1 M11 [DECORATIVE] 标记部分清除** (3 层融合起步)
4. **【推荐】P1.2 废弃 data_permissions 旧表** (写迁移脚本, 1d)
5. **【推荐】P1.3 association 派生 5 种关联 (m2m/polymorphic/self_ref/reverse/sibling) 实施** (1 周)
6. **【选做】P1.5 rls_rules 内部表集成测试** (task_execution/task_queue/scheduled_task, 1d)
7. **【选做】P2.4 导入导出加 scope 过滤** (1d)
8. **【规划】P4.1/P4.2 Record Type / Action Types Spec 设计** (远期规划)
