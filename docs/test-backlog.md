## 目录

1. [优先级总览](#优先级总览)
2. [0. P0 紧急：修复 37 failed](#0-p0-紧急：修复-37-failed)
3. [1. M1: 读路径协议层](#1-m1-读路径协议层)
4. [2. M2: ListService / AssocQueryService](#2-m2-listservice-assocqueryservice)
5. [3. M3: computed count + EXISTS](#3-m3-computed-count-exists)
6. [4. M4: cursor + 日期 + cache + feature flag](#4-m4-cursor-日期-cache-feature-flag)
7. [5. M5: 写路径 + 事务](#5-m5-写路径-事务)
8. [6. M6: Allow-list + expand + Explain + 权限](#6-m6-allow-list-expand-explain-权限)
9. [7. M7.1: CDC 实时订阅](#7-m71-cdc-实时订阅)
10. [8. M7.2: Multi-DB 激活](#8-m72-multi-db-激活)
11. [9. M7.3: DeepMutationEngine](#9-m73-deepmutationengine)
12. [10. M7.4: SchemaIntrospector](#10-m74-schemaintrospector)
13. [11. 跨模块 E2E](#11-跨模块-e2e)
14. [12. 性能测试](#12-性能测试)
15. [13. 故障注入](#13-故障注入)
16. [14. 回归测试](#14-回归测试)
17. [统计](#统计)
18. [推荐实施顺序](#推荐实施顺序)
19. [当前进度](#当前进度)

---
# v3 引擎测试用例待办（Test Backlog）

> **来源**: 详细测试场景梳理（[test-scenarios-v3-engine.md](file:///d:/filework/excel-to-diagram/docs/test-scenarios-v3-engine.md)）
> **状态**: 📋 Backlog（待实施）
> **覆盖**: M1-M7 全部 7 个阶段 + 跨模块 E2E + 性能 + 故障注入 + 回归
> **总条目**: 30 个工作包 / ~144 个 test 文件 / 4665+ 现有通过 + 37 待修复

---

## 优先级总览

| 优先级 | 工作包数 | 阶段 |
|:-----:|:-------:|------|
| **P0** | 1 个 | 修复 37 failed（pre-existing bug） |
| **P0** | 9 个 | M1/M2/M5/M6/M7 单元集成测试 |
| **P1** | 16 个 | M3/M4 性能 + E2E + 完整 M 阶段 |
| **P2** | 1 个 | 跨模块 E2E |
| **P3** | 3 个 | 性能 / 故障注入 / 回归 |

---

## 0. P0 紧急：修复 37 failed

| # | 任务 | 状态 | 工作量 |
|---|------|:----:|:-----:|
| 0.1 | test_persistence_interceptor_detailed (7 failed) | ⏳ pending | 1d |
| 0.2 | test_audit_interceptor_unified (9 failed) | ⏳ pending | 1d |
| 0.3 | test_user_group_api_extended (3 fail + 8 err) | ⏳ pending | 1d |

**详细清单**（来自 M6 末值 `--failed` 报告）：
```
test_import_export_api (3)         test_security_pentest (1)
test_permission_services (1)       test_validation_interceptors (2)
test_meta_api (1)                  test_startup_checks (1)
test_ops_server (3)                test_user_group_api_extended (3+8)
test_relation_endpoints (1)        test_auth_permission (1)
test_persistence_interceptor_detailed (7)
test_audit_interceptor_unified (9)
test_permission_unified_semantic (2)
```

**目标**: test.py `--failed` 通过率 = 100%（pre-existing 错误清零）

---

## 1. M1: 读路径协议层

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 1.1 | test_m1_query_protocol.py | 1.1-1.12 from_url_kwargs / serialize / ValidationError | ⏳ pending | 0.5d |
| 1.2 | test_m1_field_providers.py | 2.1-2.8 fields / FK / count / nesting | ⏳ pending | 0.5d |
| 1.3 | test_m1_facade_basic.py | 3.1-3.12 list / filter / sort / paginate / field check | ⏳ pending | 1d |

---

## 2. M2: ListService / AssocQueryService

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 2.1 | test_m2_list_service.py | 4.1-4.8 list / order_by fix / shim | ⏳ pending | 1d |

---

## 3. M3: computed count + EXISTS

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 3.1 | test_m3_computed_count_and_exists.py | 5.1-5.7 subquery / ORDER BY count / EXISTS / NOT EXISTS / correlation | ⏳ pending | 1d |

---

## 4. M4: cursor + 日期 + cache + feature flag

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 4.1 | test_m4_cursor.py | 6.1-6.7 encode/decode/page/tamper/cross-field | ⏳ pending | 1d |
| 4.2 | test_m4_date_funcs.py | 6.8-6.10 date_diff / func_year / func_month | ⏳ pending | 0.5d |
| 4.3 | test_m4_plan_cache.py | 6.11-6.15 hit / TTL / LRU / feature flag | ⏳ pending | 0.5d |

---

## 5. M5: 写路径 + 事务

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 5.1 | test_m5_mutation_facade.py | 7.1-7.5 create/update/delete/unsupported/pre_check | ⏳ pending | 1d |
| 5.2 | test_m5_transaction_baseline.py | 7.6-7.7 interceptor + DISABLE flag | ⏳ pending | 0.5d |
| 5.3 | test_m5_transaction_verifier.py | 7.8-7.10 not_exist / empty / 9 字段 | ⏳ pending | 0.5d |
| 5.4 | test_m5_unit_of_work.py | 7.11-7.13 atomic / rollback / last_id placeholder | ⏳ pending | 0.5d |
| 5.5 | test_m5_deep_insert_nested.py | 7.14-7.18 in_transaction / raise / parent / audit / X-Transaction-Id | ⏳ pending | 1d |

---

## 6. M6: Allow-list + expand + Explain + 权限

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 6.1 | test_m6_allow_list.py | 8.1-8.9 register / 5 错误码 / wildcard / DISABLE flag | ⏳ pending | 1d |
| 6.2 | test_m6_association_expander.py | 8.10-8.16 parse_expand / batch / not-found / MAX_ASSOCS / MAX_DEPTH | ⏳ pending | 1d |
| 6.3 | test_m6_explain_api.py | 8.17-8.18 EXPLAIN / filter_count | ⏳ pending | 0.5d |
| 6.4 | test_m6_permission_spec.py | 8.19-8.25 hidden / mask email/phone/last4 / row_filter / None ctx / trace | ⏳ pending | 1d |

---

## 7. M7.1: CDC 实时订阅

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 7.1 | test_m71_cdc_bus.py | 9.1-9.9 subscribe / unsubscribe / multi / isolation / replay / exception / stats / to_sse / event_id | ⏳ pending | 1d |
| 7.2 | test_m71_cdc_sse.py | 9.10-9.15 add_commit_hook / _fire_commit_hooks / WriteOperation fields / SSE endpoint / Last-Event-ID / nested | ⏳ pending | 1d |

---

## 8. M7.2: Multi-DB 激活

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 8.1 | test_m72_multi_db_sqlite.py | 10.1-10.3 json_extract / FTS5 / supports_fts | ⏳ pending | 0.5d |
| 8.2 | test_m72_multi_db_mysql.py | 10.4-10.6 json_extract / MATCH AGAINST / supports | ⏳ pending | 0.5d |
| 8.3 | test_m72_multi_db_postgres.py | 10.7-10.9 jsonb / to_tsvector / supports | ⏳ pending | 0.5d |
| 8.4 | test_m72_factory_router.py | 10.10-10.16 DataSource 抽象 / Factory / DATABASE_TYPE / TenantRouter / multi-tenant / cross-db SQL | ⏳ pending | 1d |

---

## 9. M7.3: DeepMutationEngine

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 9.1 | test_m73_deep_mutation.py | 11.1-11.13 insert / update nested / create fk / delete / rollback / independent / missing id / cascade / txn_id | ⏳ pending | 1d |

---

## 10. M7.4: SchemaIntrospector

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 10.1 | test_m74_schema_introspector.py | 12.1-12.10 list_tables / blacklist / introspect / id PK / FK / yaml / diff / not_found / with_auto_schema / camelCase | ⏳ pending | 1d |

---

## 11. 跨模块 E2E

| # | 工作包 | 覆盖用例 | 状态 | 工作量 |
|---|--------|---------|:----:|:-----:|
| 11.1 | E1: create_order_with_items | 写 + 嵌套 + CDC | ⏳ pending | 0.5d |
| 11.2 | E2: list_with_expand | list + M6.4 + M6.2 | ⏳ pending | 0.5d |
| 11.3 | E3: complex_query | filter + sort + pagination + expand | ⏳ pending | 0.5d |
| 11.4 | E4: large_txn_rollback | 10 个子操作 + 回滚 | ⏳ pending | 0.5d |
| 11.5 | E5: allow_list_with_permission | M6.1 + M6.5 联动 | ⏳ pending | 0.5d |
| 11.6 | E6: cross_db_query | 跨 DB mock | ⏳ pending | 0.5d |
| 11.7 | E7: cdc_subscribe | CDC 客户端订阅 | ⏳ pending | 0.5d |
| 11.8 | E8: schema_with_yaml | Auto schema + 已有 yaml | ⏳ pending | 0.5d |

---

## 12. 性能测试

| # | 工作包 | 指标 | 状态 | 工作量 |
|---|--------|------|:----:|:-----:|
| 12.1 | P1: list_10k | P95 < 200ms | ⏳ pending | 0.5d |
| 12.2 | P2: list_10k_with_5_expand | P95 < 500ms | ⏳ pending | 0.5d |
| 12.3 | P3: cursor_page_100 | P95 < 100ms | ⏳ pending | 0.5d |
| 12.4 | P4: computed_count_1m | P95 < 1s | ⏳ pending | 0.5d |
| 12.5 | P5: fts_search_100k | P95 < 200ms | ⏳ pending | 0.5d |
| 12.6 | P6: concurrent_100 | 成功率 > 99% | ⏳ pending | 0.5d |
| 12.7 | P7: writes_1000_per_sec | 不丢 | ⏳ pending | 0.5d |
| 12.8 | P8: 10w_txn_with_1_child | 全部 commit | ⏳ pending | 0.5d |
| 12.9 | P9: cdc_1000_events_per_sec | 100% 投递 | ⏳ pending | 0.5d |
| 12.10 | P10: cdc_memory_10k | < 50MB | ⏳ pending | 0.5d |

---

## 13. 故障注入

| # | 工作包 | 场景 | 状态 | 工作量 |
|---|--------|------|:----:|:-----:|
| 13.1 | F1: db_lock_5s | DB 锁定 5s | ⏳ pending | 0.5d |
| 13.2 | F2: cursor_tampered | 篡改 cursor | ⏳ pending | 0.5d |
| 13.3 | F3: sql_injection | 注入攻击 | ⏳ pending | 0.5d |
| 13.4 | F4: txn_raise | transaction 中 raise | ⏳ pending | 0.5d |
| 13.5 | F5: parent_fail | parent 创建失败 | ⏳ pending | 0.5d |
| 13.6 | F6: sub_raise | CDC 订阅者抛异常 | ⏳ pending | 0.5d |
| 13.7 | F7: json_path_not_found | JSON 路径不存在 | ⏳ pending | 0.5d |
| 13.8 | F8: db_disconnect | 跨 DB 连接断开 | ⏳ pending | 0.5d |
| 13.9 | F9: write_queue_full | 队列满 | ⏳ pending | 0.5d |
| 13.10 | F10: checkpoint_fail | checkpoint 失败 | ⏳ pending | 0.5d |

---

## 14. 回归测试

| # | 工作包 | 场景 | 状态 | 工作量 |
|---|--------|------|:----:|:-----:|
| 14.1 | R1: v1_list_api | v1 list API 仍工作 | ⏳ pending | 0.5d |
| 14.2 | R2: v1_crud | v1 create/update/delete 仍工作 | ⏳ pending | 0.5d |
| 14.3 | R3: v1_assoc | v1 关联查询仍工作 | ⏳ pending | 0.5d |
| 14.4 | R4: yaml_loader | yaml_loader 仍加载 | ⏳ pending | 0.5d |
| 14.5 | R5: feature_flag_off | DISABLE 关闭回退 | ⏳ pending | 0.5d |
| 14.6 | R6: v2_vs_v3 | v2/v3 路径切换 | ⏳ pending | 0.5d |

---

## 统计

| 阶段 | 工作包数 | 累计 | 工作量 |
|------|:-------:|:----:|:-----:|
| P0 修复 | 1 | 1 | 3d |
| M1 协议 | 3 | 4 | 2d |
| M2 服务 | 1 | 5 | 1d |
| M3 computed | 1 | 6 | 1d |
| M4 高级 | 3 | 9 | 2d |
| M5 写路径 | 5 | 14 | 3.5d |
| M6 加固 | 4 | 18 | 3.5d |
| M7.1 CDC | 2 | 20 | 2d |
| M7.2 Multi-DB | 4 | 24 | 2.5d |
| M7.3 Deep | 1 | 25 | 1d |
| M7.4 Schema | 1 | 26 | 1d |
| E2E | 8 | 34 | 4d |
| 性能 | 10 | 44 | 5d |
| 故障 | 10 | 54 | 5d |
| 回归 | 6 | 60 | 3d |
| **总计** | **60** | - | **39.5d** |

---

## 推荐实施顺序

### 档位 A：关键闭环（13 个工作日）

1. **P0 修复 37 failed**（3d）— 先清回归
2. **M5 写路径核心**（5 个，3.5d）— 事务是企业级基线
3. **M6 安全基线**（4 个，3.5d）— Allow-list / 权限是大客户必查
4. **M7 平台基础**（8 个，4d）— CDC + Multi-DB + Deep + Schema
5. **M1 + M2 协议基础**（4 个，2d）— 读路径基线

### 档位 B：完整测试体系（39.5d）

档位 A + 全部 E2E + 性能 + 故障注入 + 回归

### 档位 C：仅 P0 修复（3d）

仅修复 37 failed，让 `test.py --failed` 通过率 = 100%

---

## 当前进度

- ✅ **Backlog 整理**：完成（60 个工作包 / 30 个大类）
- ⏳ **P0 修复 37 failed**：未开始
- ⏳ **M1-M7 单元集成**：未开始
- ⏳ **E2E / 性能 / 故障 / 回归**：未开始

请选择档位（A / B / C）开始实施。
