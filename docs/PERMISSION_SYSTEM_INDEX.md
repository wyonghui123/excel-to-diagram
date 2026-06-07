# 权限体系文档索引

> 权限体系相关文档统一入口
> 最后更新: 2026-06-07

## 核心规范（活跃）

| 文档 | 主题 | 状态 |
|------|------|------|
| [spec_data_permission_unified_model.md](./specs/spec_data_permission_unified_model.md) | 数据权限统一模型 | 活跃 |
| [spec_role_permission_granular_control.md](./specs/spec_role_permission_granular_control.md) | 角色权限粒度控制 | 活跃 |
| [auth-permission-system-design.md](./auth-permission-system-design.md) | 认证权限系统设计 | 活跃 |
| [rfc_action_service_unified_model.md](./rfc_action_service_unified_model.md) | 动作服务统一模型 | 活跃 |

## 方案设计（已收敛为统一索引）

> 以下方案设计文档均围绕"元数据驱动权限体系"展开，建议优先阅读 RFC 详细设计。

| 文档 | 主题 | 关系 |
|------|------|------|
| [方案设计_元数据驱动权限体系.md](./permission-metadata-driven-solution.md) | 元数据驱动权限体系方案 | 入口文档 |
| [方案设计_权限体系元数据驱动优化.md](./permission-metadata-driven-optimization.md) | 优化方案 | 优化补充 |
| [方案细化_权限体系元数据驱动化.md](./permission-metadata-driven-refinement.md) | 细化方案 | 细化说明 |
| [权限体系元数据驱动化_细化方案设计.md](./permission-metadata-driven-design.md) | 细化方案设计 | 同上 |
| [Spec_权限体系元数据驱动化.md](./spec-permission-metadata-driven.md) | 元数据驱动化规格 | 规格 |
| [MetaAction权限体系深度分析与设计方案.md](./meta-action-permission-analysis.md) | 深度分析 | 分析参考 |

## 专题分析

| 文档 | 主题 | 状态 |
|------|------|------|
| [data-permission-field-attributes-mapping.md](./data-permission-field-attributes-mapping.md) | 数据权限字段映射 | 活跃 |
| [data-permission-impact-analysis.md](./data-permission-impact-analysis.md) | 数据权限影响分析 | 参考 |
| [data-permission-inheritance-model.md](./data-permission-inheritance-model.md) | 数据权限继承模型 | 活跃 |
| [权限体系_单一事实源补充分析.md](./permission-ssot-analysis.md) | 单一事实源分析 | 活跃 |
| [权限配置流程优化_维度驱动vs菜单驱动.md](./permission-config-optimization.md) | 配置流程优化 | 活跃 |
| [BACKLOG-Permission-System-Improvement.md](./BACKLOG-Permission-System-Improvement.md) | 改进待办 | 活跃 |

## 调研与对比

| 文档 | 主题 |
|------|------|
| [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md) | 竞品分析 |
| [用友BIP权限模型研究补充.md](./yonyou-bip-permission-research.md) | 友商研究 |
| [enterprise-security-architecture-analysis.md](./enterprise-security-architecture-analysis.md) | 企业安全架构分析 |
| [sap-deep-authorization-analysis.md](./sap-deep-authorization-analysis.md) | SAP 深度分析 |
| [sap-salesforce-field-level-security-analysis.md](./sap-salesforce-field-level-security-analysis.md) | SAP/ Salesforce 字段级安全 |

## 测试与审计

| 文档 | 主题 |
|------|------|
| [PERMISSION_TEST_REPORT.md](./PERMISSION_TEST_REPORT.md) | 权限测试报告 |
| [审计日志最佳实践.md](./audit-log-best-practices.md) | 审计日志最佳实践 |

## 权限体系升级专题

详见 [spec_权限体系升级/](./spec_权限体系升级/) 目录：
- [01_background.md](./spec_权限体系升级/01_background.md) — 背景分析
- [02_fr.md](./spec_权限体系升级/02_fr.md) — 需求规格
- [03_nfr_if_tr_constraints.md](./spec_权限体系升级/03_nfr_if_tr_constraints.md) — 约束
- [04_rfc_analysis.md](./spec_权限体系升级/04_rfc_analysis.md) — RFC 分析
- [05_rfc_detailed_design.md](./spec_权限体系升级/05_rfc_detailed_design.md) — RFC 详细设计
- [06_rfc_impl_test_tbd.md](./spec_权限体系升级/06_rfc_impl_test_tbd.md) — 实施测试
- [07_supplement_fr016_tbd.md](./spec_权限体系升级/07_supplement_fr016_tbd.md) — 补充 FR016

## 使用建议

1. **新接触权限体系** → [auth-permission-system-design.md](./auth-permission-system-design.md)
2. **数据权限开发** → [spec_data_permission_unified_model.md](./specs/spec_data_permission_unified_model.md) + [data-permission-inheritance-model.md](./data-permission-inheritance-model.md)
3. **方案设计参考** → [方案设计_元数据驱动权限体系.md](./permission-metadata-driven-solution.md)
4. **升级/重构参考** → [spec_权限体系升级/05_rfc_detailed_design.md](./spec_权限体系升级/05_rfc_detailed_design.md)

## 维护说明

- 核心规范（spec_*.md）必须保持最新
- 方案设计类文档已通过本索引收敛，避免内容重复
- 新增权限相关文档请更新本索引
