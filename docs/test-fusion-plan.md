## 目录

1. [0. 现状摸底](#0-现状摸底)
2. [1. 测试去重融合方案](#1-测试去重融合方案)
3. [2. 调整后的测试工作包（精简版）](#2-调整后的测试工作包（精简版）)
4. [3. 整合后的测试结构（目标态）](#3-整合后的测试结构（目标态）)
5. [4. 整合工作量对比](#4-整合工作量对比)
6. [5. 落地顺序](#5-落地顺序)
7. [6. 验证标准](#6-验证标准)
8. [7. 风险](#7-风险)

---
# v3 引擎测试体系融合调整（Test Fusion & Refinement）

> **日期**: 2026-06-06
> **状态**: 📋 调整计划（待审批）
> **输入**: [test-backlog.md](file:///d:/filework/excel-to-diagram/docs/test-backlog.md) + [spec-query-engine-unification-m8.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-unification-m8.md)
> **目标**: 现有 252 个 test 文件 + M1-M8 新增 60 个工作包 = **融合去重、避免重复造测试**

---

## 0. 现状摸底

### 0.1 现有测试文件统计

| 域 | 文件数 | 占比 |
|----|------:|:---:|
| 根目录（未整理） | 224 | 88.9% |
| `performance/` | 5 | 2.0% |
| `_consolidated/` | 5 | 2.0% |
| `api/` | 3 | 1.2% |
| `import_export/` | 3 | 1.2% |
| `interceptors/` | 3 | 1.2% |
| `auth/` | 2 | 0.8% |
| `bo/` | 2 | 0.8% |
| `core/` | 1 | 0.4% |
| `integration/` | 1 | 0.4% |
| `metadata/` | 1 | 0.4% |
| `permission/` | 1 | 0.4% |
| `query/` | 1 | 0.4% |
| `services/` | 1 | 0.4% |
| **合计** | **252** | 100% |

### 0.2 与 M1-M8 相关的已有测试（38 个）

| 文件 | M 对应 | 状态 |
|------|--------|------|
| `test_unified_meta_model.py` | M1 | 已有 |
| `test_query_api.py` | M1 | 已有 |
| `test_query_builder.py` | M1 | 已有 |
| `test_query_interceptor.py` | M1 | 已有 |
| `test_query_service.py` | M1/M3 | 已有 |
| `test_queryservice_dataperm.py` | M1/M6.5 | 已有 |
| `test_sql_adapters_filters.py` | M1 | 已有 |
| `test_filter_e2e.py` | M1/M3 | 已有 |
| `test_filter_service.py` | M1 | 已有 |
| `test_filter_field_semantics.py` | M1 | 已有 |
| `test_filter_variant_api.py` | M1/M8 | 已有 |
| `test_description_search_filter.py` | M1 | 已有 |
| `test_diagnose_domain_list.py` | M1 | 已有 |
| `test_dimension_aware_filtering.py` | M3 | 已有 |
| `test_dimension_scope_engine.py` | M3 | 已有 |
| `test_storage_filtering.py` | M1 | 已有 |
| `test_subscription_filter_service.py` | M1/M7.1 | 已有 |
| `test_hierarchy_filter_api.py` | M1 | 已有 |
| `test_hierarchy_filter_service.py` | M1 | 已有 |
| `test_value_help_api.py` | **M8 VP-1** | **已有** |
| `test_value_help_validation.py` | **M8 VP-1** | **已有** |
| `test_aggregate_manager.py` | **M8 VP-3** | **已有** |
| `test_aggregate_refresh_integration.py` | **M8 VP-3** | **已有** |
| `test_management_dimension_api.py` | M3 | 已有 |
| `test_audit_interceptor_unified.py` | M5 | 已有（9 failed） |
| `test_unified_meta_model.py` | M1 | 已有 |
| `test_role_permission_apis.py` | M6.5 | 已有 |
| `test_data_permission_api.py` | M6.5 | 已有 |
| `test_data_permission_generator.py` | M6.5 | 已有 |
| `test_data_permission_interceptor.py` | M6.5 | 已有 |
| `test_data_permission_service.py` | M6.5 | 已有 |
| `test_permission_service.py` | M6.5 | 已有 |
| `test_permission_service_edge.py` | M6.5 | 已有 |
| `test_permission_rule_api_extended.py` | M6.5 | 已有 |
| `test_condition_permission_service.py` | M6.5 | 已有 |
| `test_owner_auto_permission_interceptor.py` | M6.5 | 已有 |
| `test_require_permission_decorator.py` | M6.5 | 已有 |
| `test_v2_api_permissions.py` | M6.5 | 已有 |
| `test_permission_unified_semantic.py` | M6.5 | 已有 |
| `test_auth_permission.py` | M6.5 | 已有 |

### 0.3 M8 相关已有测试（关键发现）

| VP | 已有 | 缺口 |
|----|------|------|
| **VP-1 ValueHelp** | `value_help_api.py` 端点 + 14 个测试 | v3 facade 入口 + 多语言 + top 限制 |
| **VP-3 Aggregate** | `test_aggregate_manager.py` + refresh 集成 | REST 风格 GET + group_by 字符串 |
| **VP-4 Reverse** | `_query_reverse_m2m` 已有实现 | **无端点** |
| **VP-5 ETag** | ❌ 无 | 完全缺失 |
| **VP-6 CustomOrder** | ❌ 无 | 完全缺失 |
| **VP-2 Nested DSL** | ❌ 无 | 完全缺失 |

---

## 1. 测试去重融合方案

### 1.1 总体原则

> **能改不写**：先 patch 现有测试覆盖 M1-M8 缺口
> **能合不拆**：把零散测试整合到 M1-M8 命名空间
> **能跑不新加**：M1-M8 spec 写的"20 个测试场景"= 直接映射到现有 test_xxx.py 加 test method

### 1.2 现有 38 个 M 相关测试的去重分类

| 现有测试 | 映射到 M 工作包 | 动作 |
|---------|---------------|------|
| `test_query_api.py` | M1 / M8-VP3 | 保留 + 加 facade.execute 断言 |
| `test_query_builder.py` | M1 | 保留 + 加 M8 DSL 路径 |
| `test_query_service.py` | M1/M2/M3 | 保留 + 加 computed count |
| `test_sql_adapters_filters.py` | M1/M7.2 | 保留 + 加 3 个 adapter json_extract |
| `test_filter_service.py` | M1 | 保留 |
| `test_filter_field_semantics.py` | M1 | 保留 |
| `test_filter_variant_api.py` | M1/M4 | 保留 + 加 cursor 路径 |
| `test_filter_e2e.py` | M1-M3 | 保留 + 加 expand 路径 |
| `test_dimension_aware_filtering.py` | M3 | 保留 |
| `test_storage_filtering.py` | M1/M2 | 保留 |
| `test_subscription_filter_service.py` | M7.1 | 改名为 `test_m71_cdc_subscription.py` |
| `test_value_help_api.py` | **M8 VP-1** | 改名为 `test_m81_valuehelp.py` + 加 top/locale/display |
| `test_value_help_validation.py` | M8 VP-1 | 合并到 `test_m81_valuehelp.py` |
| `test_aggregate_manager.py` | **M8 VP-3** | 改名为 `test_m83_aggregate.py` |
| `test_aggregate_refresh_integration.py` | M8 VP-3 | 合并到 `test_m83_aggregate.py` |
| `test_data_permission_*.py` (4 个) | M6.5 | 合并为 `test_m65_data_permission.py` |
| `test_permission_*.py` (7 个) | M6.5 | 整合为 `test_m65_permission_*.py`（3 个） |
| `test_audit_interceptor_unified.py` | M5 | 修复 9 failed（**P0**） |
| `test_unified_meta_model.py` | M1 | 保留 |

---

## 2. 调整后的测试工作包（精简版）

### 2.1 P0 修复（37 failed）

| # | 工作包 | 文件 | 动作 |
|---|--------|------|------|
| 0.1 | 修复 audit interceptor | `test_audit_interceptor_unified.py` | 修 9 failed |
| 0.2 | 修复 persistence interceptor | `test_persistence_interceptor_detailed.py` | 修 7 failed |
| 0.3 | 修复 user_group api | `test_user_group_api_extended.py` | 修 3 fail + 8 err |
| 0.4 | 修复 import_export / ops / 等 | 14 个文件 | 修 18 failed |

### 2.2 M1 协议层（融合 4 个现有 + 新增 1 个）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 1.1 | **M1 facade** | `test_m1_facade.py` (新) | 3.1-3.12 | 新建 |
| 1.2 | M1 query builder | `test_query_builder.py` (已有) | 已有 | 加 M1.1-1.3 断言 |
| 1.3 | M1 field provider | `test_unified_meta_model.py` (已有) | 2.1-2.8 | 加 M1.2 断言 |
| 1.4 | M1 from_url_kwargs | `test_filter_service.py` (已有) | 1.1-1.12 | 加 1.1-1.10 断言 |

### 2.3 M2 服务层（融合 2 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 2.1 | M2 ListService | `test_filter_e2e.py` (已有) | 4.1-4.8 | 改名为 `test_m2_list_service.py` |
| 2.2 | M2 AssocService | `test_e2e_tree_to_list.py` (已有) | 4.5-4.6 | 保留 |

### 2.4 M3 高级查询（融合 3 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 3.1 | M3 computed count | `test_dimension_aware_filtering.py` (已有) | 5.1-5.7 | 加 5.1-5.3 断言 |
| 3.2 | M3 EXISTS 关联 | `test_storage_filtering.py` (已有) | 5.4-5.6 | 加 5.4-5.6 断言 |
| 3.3 | M3 correlation 修复 | `test_dimension_scope_engine.py` (已有) | 5.6 | 加相关性测试 |

### 2.5 M4 高级特性（融合 2 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 4.1 | M4 cursor | `test_filter_variant_api.py` (已有) | 6.1-6.7 | 加 cursor 断言 |
| 4.2 | M4 date funcs | (无) | 6.8-6.10 | 新建 `test_m4_date_funcs.py` |
| 4.3 | M4 plan cache | (无) | 6.11-6.15 | 新建 `test_m4_plan_cache.py` |

### 2.6 M5 写路径（融合 2 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 5.1 | M5 mutation facade | `test_query_api.py` (已有) | 7.1-7.5 | 加 mutation 断言 |
| 5.2 | M5 transaction baseline | (无) | 7.6-7.7 | 新建 |
| 5.3 | M5 transaction verifier | (无) | 7.8-7.10 | 新建 |
| 5.4 | M5 unit of work | (无) | 7.11-7.13 | 新建 |
| 5.5 | M5 deep insert nested | `test_audit_interceptor_unified.py` (已有) | 7.14-7.18 | 修复后覆盖 |
| 5.6 | **修复 audit interceptor** | `test_audit_interceptor_unified.py` | 9 failed | **P0** |

### 2.7 M6 加固（融合 11 个现有权限测试）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 6.1 | M6 allow list | (无) | 8.1-8.9 | 新建 `test_m61_allow_list.py` |
| 6.2 | M6 association expander | (无) | 8.10-8.16 | 新建 `test_m64_expand.py` |
| 6.3 | M6 explain API | (无) | 8.17-8.18 | 新建 `test_m62_explain.py` |
| 6.4 | M6 permission | `test_data_permission_*.py` (4 个已有) + `test_permission_*.py` (7 个) | 8.19-8.25 | **合并为 3 个** `test_m65_permission_*.py` |
| 6.5 | M6 整合测试 | `test_v2_api_permissions.py` (已有) | 联动 | 保留 |

### 2.8 M7 平台（融合 0 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 7.1 | M7.1 CDC bus | `test_subscription_filter_service.py` (已有) | 9.1-9.9 | 改名为 `test_m71_cdc_bus.py` + 加 9.1-9.9 |
| 7.2 | M7.1 CDC SSE | (无) | 9.10-9.15 | 新建 |
| 7.3 | M7.2 multi-db | `test_sql_adapters_filters.py` (已有) | 10.1-10.16 | 加 10.1-10.9 断言 |
| 7.4 | M7.2 tenant router | (无) | 10.13-10.16 | 新建 |
| 7.5 | M7.3 deep mutation | (无) | 11.1-11.13 | 新建 |
| 7.6 | M7.4 schema introspector | (无) | 12.1-12.10 | 新建 |

### 2.9 M8 消费侧（融合 2 个现有）

| # | 工作包 | 文件 | 覆盖 | 调整 |
|---|--------|------|------|------|
| 8.1 | **M8 VP-1 ValueHelp** | `test_value_help_api.py` (14 测试) | VP-1 1-7 | **改名为 `test_m81_valuehelp.py`** + 加 top/locale |
| 8.2 | M8 VP-2 Nested DSL | (无) | VP-2 1-6 | 新建 `test_m82_nested_dsl.py` |
| 8.3 | **M8 VP-3 Aggregate** | `test_aggregate_manager.py` + refresh (2 个) | VP-3 1-5 | **合并为 `test_m83_aggregate.py`** + 加 REST GET |
| 8.4 | M8 VP-4 Reverse Expand | (无) | VP-4 1-5 | 新建 `test_m84_reverse_expand.py` |
| 8.5 | M8 VP-5 ETag | (无) | VP-5 1-4 | 新建 `test_m85_etag.py` |
| 8.6 | M8 VP-6 Custom Order | (无) | VP-6 1-3 | 新建 `test_m86_custom_order.py` |

---

## 3. 整合后的测试结构（目标态）

```
meta/tests/
├── m1/                                # [新目录] M1 协议层
│   ├── test_m1_facade.py
│   ├── test_m1_query_builder.py       (从根迁移)
│   ├── test_m1_field_providers.py     (从根迁移)
│   └── test_m1_from_url_kwargs.py     (从根迁移)
├── m2/                                # [新目录] M2 服务层
│   ├── test_m2_list_service.py        (从根迁移)
│   └── test_m2_assoc_service.py       (从根迁移)
├── m3/                                # [新目录] M3 高级查询
│   ├── test_m3_computed_count.py      (从根迁移)
│   ├── test_m3_exists.py              (从根迁移)
│   └── test_m3_correlation.py         (从根迁移)
├── m4/                                # [新目录] M4 高级特性
│   ├── test_m4_cursor.py              (从根迁移)
│   ├── test_m4_date_funcs.py          (新)
│   └── test_m4_plan_cache.py          (新)
├── m5/                                # [新目录] M5 写路径
│   ├── test_m5_mutation_facade.py
│   ├── test_m5_transaction_baseline.py
│   ├── test_m5_transaction_verifier.py
│   ├── test_m5_unit_of_work.py
│   └── test_m5_deep_insert_nested.py
├── m6/                                # [新目录] M6 加固
│   ├── test_m61_allow_list.py
│   ├── test_m62_explain.py
│   ├── test_m63_expand.py
│   ├── test_m64_permission_spec.py    (合并 7 个)
│   ├── test_m65_data_permission.py    (合并 4 个)
│   └── test_m66_unified_permissions.py (从根迁移)
├── m7/                                # [新目录] M7 平台
│   ├── test_m71_cdc_bus.py
│   ├── test_m72_cdc_sse.py
│   ├── test_m73_multi_db.py
│   ├── test_m74_tenant_router.py
│   ├── test_m75_deep_mutation.py
│   └── test_m76_schema_introspector.py
├── m8/                                # [新目录] M8 消费侧
│   ├── test_m81_valuehelp.py          (从根迁移 14 个)
│   ├── test_m82_nested_dsl.py         (新)
│   ├── test_m83_aggregate.py          (从根迁移 2 个)
│   ├── test_m84_reverse_expand.py     (新)
│   ├── test_m85_etag.py               (新)
│   └── test_m86_custom_order.py       (新)
├── integration/                       # 跨模块 E2E
│   ├── test_e1_create_order_with_items.py
│   ├── test_e2_list_with_expand.py
│   ├── test_e3_complex_query.py
│   ├── test_e4_large_txn_rollback.py
│   ├── test_e5_allow_list_with_permission.py
│   ├── test_e6_cross_db_query.py
│   ├── test_e7_cdc_subscribe.py
│   ├── test_e8_valuehelp_with_cdc.py  # [M8 新增]
│   └── test_e9_aggregate_with_dsl.py  # [M8 新增]
├── performance/                       # 性能
│   ├── test_p1_list_10k.py
│   ├── test_p2_list_10k_with_5_expand.py
│   ├── test_p3_cursor_page_100.py
│   ├── test_p4_computed_count_1m.py
│   ├── test_p5_fts_search_100k.py
│   ├── test_p6_concurrent_100.py
│   ├── test_p7_writes_1000_per_sec.py
│   ├── test_p8_10w_txn_with_1_child.py
│   ├── test_p9_cdc_1000_events_per_sec.py
│   └── test_p10_cdc_memory_10k.py
├── fault_injection/                   # 故障注入
│   └── ... (F1-F10)
├── regression/                        # 回归
│   └── ... (R1-R6)
├── core/                              # 通用
│   ├── test_core_utilities.py         (已有)
│   └── ...
├── auth/                              # 认证
│   └── ...
├── interceptors/                      # 拦截器
│   ├── test_cascade_interceptor_detailed.py
│   ├── test_persistence_interceptor_detailed.py  (修复 7 failed)
│   └── test_validation_interceptors.py
├── permission/                        # 权限（保留）
│   └── test_permission_services.py
├── query/                             # 查询（保留）
│   └── test_query_filters.py
├── services/                          # 服务（保留）
│   └── test_user_services.py
├── import_export/                     # 导入导出（保留）
│   ├── test_export_pagination_and_options.py
│   ├── test_import_export_apis.py
│   └── test_import_template.py
├── integration/                       # 集成
│   └── test_integration_scenarios.py
├── performance/                       # 性能
│   └── ...
├── metadata/                          # 元数据
│   └── test_metadata_validators.py
├── bo/                                # BO
│   ├── test_formula_bo.py
│   └── test_hierarchy_bo.py
├── api/                               # API
│   ├── test_enum_extended.py
│   ├── test_extended_apis.py
│   └── test_role_permission_apis.py
├── _consolidated/                     # 已整合（保留）
│   └── ...
└── (根目录散落文件待迁移)             # 由 m1-m8 子目录吸收
```

---

## 4. 整合工作量对比

| 方案 | 写入 | 改动 | 迁移 | 合并 | **净增** |
|------|------|------|------|------|:-------:|
| 原计划（每个工作包新文件） | 60 | 0 | 0 | 0 | 60 |
| **融合后（推荐）** | 26 | 14 | 16 | 8 | **26** |
| **节省** | -34 | +14 | +16 | +8 | **-34** |

| 项目 | 写入 | 改动 | 迁移 | 合并 |
|------|:---:|:---:|:---:|:---:|
| M1-M7 子目录 | 26 | 14 | 16 | 8 |
| M8 子目录 | 4 | 2 | 2 | 2 |
| 整合 P0 修复 | 0 | 11 | 0 | 0 |
| 跨模块 E2E | 9 | 0 | 0 | 0 |
| 性能 + 故障 + 回归 | 26 | 0 | 0 | 0 |
| **小计** | 65 | 27 | 18 | 10 |

**净增 26 个新 test 文件 / 27 个改动 / 18 个迁移 / 10 个合并**

---

## 5. 落地顺序

### 档位 A：核心闭环（13d）

1. **P0 修复 37 failed** (3d)
2. **M5/M6/M7 写路径 + 加固 + 平台** (4d)
   - M5.1 mutation facade (在 `test_query_api.py` 加 mutation)
   - M5.6 audit interceptor 修复
   - M6.4 permission 整合（7→3）
   - M7.1 cdc bus 改名 + 加测
3. **M8 消费侧核心** (3d)
   - M8.1 valuehelp 改名 + 加 top/locale
   - M8.3 aggregate 合并
   - M8.4 reverse expand
4. **M1/M2/M3/M4 读路径** (3d)
   - 迁移 14 个现有 + 加 M1.1-1.10 断言

### 档位 B：完整（27d）

档位 A + 全部 E2E（E1-E9）+ 性能 + 故障注入 + 回归

### 档位 C：仅 P0 + 整合（5d）

仅修 37 failed + 整理测试目录结构（合并/迁移）

---

## 6. 验证标准

- [ ] P0 修复：`test.py --failed` 0 失败
- [ ] 目录结构：m1/m2/m3/m4/m5/m6/m7/m8 子目录就位
- [ ] 现有 38 个相关测试全部迁移/合并
- [ ] M1-M8 spec 全部场景覆盖
- [ ] E2E 9 个集成
- [ ] 全量 `test.py` 通过率 ≥ 4665 + M 新增数
- [ ] 单测 < 100ms, 集成 < 1s, E2E < 5s

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| 迁移破坏现有测试 | 分批迁移 + 每批跑 test.py --failed |
| 合并丢失测试用例 | 合并前 grep 现有 test method name |
| M8 端点未实现 | 先 stub 端点 + 标记 expected failure |
| 性能测试假数据 | 用现有 seed 数据 |
| 权限测试用户差异 | 用 `conftest` 共享 auth |

---

请选择档位（A / B / C）开始实施。
