# Tasks: BO Framework 性能优化 v3.1

> **关联 spec**: [spec.md](./spec.md)
> **关联 checklist**: [checklist.md](./checklist.md)
> **创建日期**: 2026-06-10

---

## 总体实施计划（5+ PR / 2 迭代）

```
迭代 1 (M1) ──────────────────────────────────────────────
  PR-01: 拦截器批量化 + 并行化 (FR-001+FR-002)
  PR-02: preview 缓存 + 索引 (FR-003+FR-004)
  PR-03: enrichment 缓存 + 1 SQL 合并 (FR-005+FR-006+FR-015)
  PR-04: 查询优化（count/search/sort）(FR-007+FR-008+FR-009+FR-010)

迭代 2 (M2) ──────────────────────────────────────────────
  PR-05: 权限 + 审计 + SQLite (FR-011+FR-012+FR-013+FR-014)
  PR-06: 可观测性 + 接口 + 末尾优化 (FR-016+FR-017+FR-018+FR-019)
```

---

## PR-01: 拦截器批量化 + 并行化 (M1)

**关联**: FR-001 / FR-002
**预估代码量**: ~200 行
**依赖**: 无
**Owner**: TBD

### T-01-01: 实现 LRUCacheWithTTL

- **文件**: [meta/core/lru_cache.py](file:///d:/filework/excel-to-diagram/meta/core/) (new)
- **类型**: Functionality
- **预估**: 4h
- **验证**:
  - 单元测试：命中/未命中/TTL 过期/LRU 淘汰
  - 性能测试：10000 entry P99 < 1ms

### T-01-02: 实现 InterceptorMetrics

- **文件**: [meta/core/interceptor_metrics.py](file:///d:/filework/excel-to-diagram/meta/core/) (new)
- **类型**: Functionality
- **预估**: 2h
- **验证**:
  - 单测：record_metric 正确输出 Prometheus 格式

### T-01-03: Interceptor 基类加 parallel_safe

- **文件**: [meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 18 拦截器基类声明 `parallel_safe = False` 默认

### T-01-04: ContextInterceptor 标记 parallel_safe + 批量化

- **文件**: [meta/core/interceptors/context_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/context_interceptor.py)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - `cached_old_data` 注入正确
  - 并行安全

### T-01-05: VersionInterceptor / PermissionInterceptor 标记 parallel_safe

- **文件**: [meta/core/interceptors/](file:///d:/filework/excel-to-diagram/meta/core/interceptors/) (modify)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单元测试：并行执行不互相污染 context

### T-01-06: LockInterceptor 复用 cached_old_data

- **文件**: [meta/core/interceptors/lock_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/lock_interceptor.py)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单元测试：复用命中/未命中

### T-01-07: AuditInterceptor 复用 cached_old_data

- **文件**: [meta/core/interceptors/audit_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单元测试：复用命中/未命中
  - 合规性：审计字段完整

### T-01-08: bo_framework.py 并行化逻辑

- **文件**: [meta/core/bo_framework.py:218-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L218-L229)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：声明 parallel_safe 的拦截器并发执行
  - 集成测试：单条 update SQL 数 = 5-6

### T-01-09: PR-01 集成测试

- **文件**: [meta/tests/interceptors/test_batch_parallel_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/interceptors/test_batch_parallel_v3_1.py`
  - 通过

---

## PR-02: preview 缓存 + 索引 (M1)

**关联**: FR-003 / FR-004
**预估代码量**: ~250 行
**依赖**: PR-01 (LRUCacheWithTTL)
**Owner**: TBD

### T-02-01: PreviewCache 模块

- **文件**: [meta/core/preview_cache.py](file:///d:/filework/excel-to-diagram/meta/core/) (new)
- **类型**: Functionality
- **预估**: 4h
- **验证**:
  - 单测：key 计算 / 命中 / 未命中 / TTL

### T-02-02: migration 加 4 个索引

- **文件**: [meta/migrations/v3_1_add_perf_indexes.py](file:///d:/filework/excel-to-diagram/meta/migrations/) (new)
- **类型**: Migration
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --single meta/tests/migrations/test_idx_relationship_v3_1.py`
  - 表大小增长 < 5%

### T-02-03: preview 端点接入缓存

- **文件**: [meta/api/bo_api.py:847-986](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L847-L986)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 第二次相同请求 P95 < 50ms

### T-02-04: scope_type / category_type 用 SQL CASE WHEN

- **文件**: [meta/core/interceptors/persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 10000 条 relationship preview < 800ms

### T-02-05: 环境变量 BO_PREVIEW_CACHE_TTL/SIZE

- **文件**: [meta/core/config.py](file:///d:/filework/excel-to-diagram/meta/core/config.py) (modify)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 启动时读取环境变量

### T-02-06: PR-02 E2E 测试

- **文件**: [meta/tests/api/test_preview_cache_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/api/test_preview_cache_v3_1.py`

---

## PR-03: enrichment 缓存 + 1 SQL 合并 (M1)

**关联**: FR-005 / FR-006 / FR-015
**预估代码量**: ~400 行
**依赖**: PR-01 (LRUCacheWithTTL)
**Owner**: TBD

### T-03-01: EnrichmentCache LRU+TTL

- **文件**: [meta/core/enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py)
- **类型**: Modify
- **预估**: 6h
- **验证**:
  - 单测：命中/未命中/TTL/LRU 淘汰

### T-03-02: PersistenceInterceptor.after_action 写时失效

- **文件**: [meta/core/interceptors/persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：写后下次读立即失效

### T-03-03: 1 SQL JOIN 合并 3 步 enrichment

- **文件**: [meta/core/enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py)
- **类型**: Modify
- **预估**: 8h
- **验证**:
  - 单测：合并后行为等价（与 v1 对比）
  - SQL 数从 3 降至 1

### T-03-04: FK display target_table 分组

- **文件**: [meta/core/enrichment_engine.py:446-508](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L446-L508)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：多 FK 共享目标表场景

### T-03-05: BO_ENRICHMENT_MODE=v1 回退

- **文件**: [meta/core/enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 启动时读取环境变量

### T-03-06: 内存压力测试

- **文件**: [meta/tests/performance/test_enrichment_memory_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 7 天模拟 RSS 增长 < 200MB

### T-03-07: PR-03 集成测试

- **文件**: [meta/tests/enrichment/test_cache_join_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/enrichment/test_cache_join_v3_1.py`

---

## PR-04: 查询优化 (M1)

**关联**: FR-007 / FR-008 / FR-009 / FR-010
**预估代码量**: ~300 行
**依赖**: 无
**Owner**: TBD

### T-04-01: count_all 扁平化

- **文件**: [meta/core/query_builder.py:612-619](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py#L612-L619)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单测：扁平化后行为等价

### T-04-02: count cache

- **文件**: [meta/core/query_builder.py](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：命中/未命中/TTL

### T-04-03: skip_count 默认开启

- **文件**: [meta/api/bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - skip_count=True 时不跑 count

### T-04-04: search N-gram + 前缀 LIKE

- **文件**: [meta/core/interceptors/persistence_interceptor.py:613-678](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L613-L678)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：多 token 拆分 + 前缀 LIKE
  - 搜索响应 P95 < 500ms

### T-04-05: 虚拟排序 TEMP TABLE

- **文件**: [meta/services/query_service.py:518-521](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L518-L521)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 10000 行排序 P95 < 200ms

### T-04-06: hierarchy GROUP BY 物化

- **文件**: [meta/services/query_service.py:586-648](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L586-L648)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 5000 行按 relation_count 排序 P95 < 300ms

### T-04-07: 性能基准测试

- **文件**: [meta/tests/performance/test_query_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 输出 P50/P95/P99

### T-04-08: PR-04 集成测试

- **文件**: [meta/tests/query/test_count_search_sort_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/query/test_count_search_sort_v3_1.py`

---

## PR-05: 权限 + 审计 + SQLite (M2)

**关联**: FR-011 / FR-012 / FR-013 / FR-014
**预估代码量**: ~250 行
**依赖**: 无
**Owner**: TBD

### T-05-01: 数据权限 3 SQL 合并

- **文件**: [meta/core/interceptors/data_permission_interceptor.py:103-132](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L103-L132)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：合并后等价 + per-request cache 命中

### T-05-02: per-request user_permissions 缓存

- **文件**: [meta/core/interceptors/context_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/context_interceptor.py)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单测：context.user_permissions 复用

### T-05-03: scope 表达式预编译

- **文件**: [meta/core/interceptors/data_permission_interceptor.py:213-256](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L213-L256)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单测：解析缓存命中

### T-05-04: 审计批 INSERT

- **文件**: [meta/core/bo_framework.py:532-568](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L532-L568)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单测：100 条 pending audit < 50ms
  - 合规性：审计完整

### T-05-05: StructuredLogger 实例复用

- **文件**: [meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 单元测试

### T-05-06: fresh_connection 复用 + WAL checkpoint

- **文件**: [meta/core/interceptors/persistence_interceptor.py:831-858](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L831-L858)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - computed 过滤 sqlite3 connect = 0
  - WAL pending frames < 100

### T-05-07: PR-05 集成测试

- **文件**: [meta/tests/security/test_perf_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/security/test_perf_v3_1.py`

---

## PR-06: 可观测性 + 接口 + 末尾优化 (M2)

**关联**: FR-016 / FR-017 / FR-018 / FR-019
**预估代码量**: ~250 行
**依赖**: PR-01 (InterceptorMetrics)
**Owner**: TBD

### T-06-01: 18 拦截器埋点

- **文件**: [meta/core/interceptors/](file:///d:/filework/excel-to-diagram/meta/core/interceptors/) 18 个 (modify)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 所有拦截器 before/after 有 metric

### T-06-02: Prometheus 端点扩展

- **文件**: [meta/api/metrics_api.py](file:///d:/filework/excel-to-diagram/meta/api/) (modify)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - `/api/v1/_metrics` 输出 Prometheus 格式
  - trace_id 注入 SQL 注释

### T-06-03: Flask gzip 启用

- **文件**: [meta/server.py](file:///d:/filework/excel-to-diagram/meta/server.py)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 5MB JSON 响应 < 1MB
  - < 1KB 不压缩

### T-06-04: 详情合并端点

- **文件**: [meta/api/bo_api.py:178-198](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L178-L198)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 详情 SQL 数从 5-7 降至 2-3
  - 前端联调通过

### T-06-05: _TxnMarker 改 result.success

- **文件**: [meta/core/bo_framework.py:127-156](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L127-L156)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单元测试：事务成功路径不抛异常

### T-06-06: 高频 logger.info 降级

- **文件**: [meta/services/query_service.py:343-365](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L343-L365)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 单元测试：默认级别无 info 日志

### T-06-07: Cache 管理端点

- **文件**: [meta/api/admin_cache_api.py](file:///d:/filework/excel-to-diagram/meta/api/) (new)
- **类型**: Functionality
- **预估**: 4h
- **验证**:
  - `POST /api/v1/admin/cache/clear`
  - `GET /api/v1/admin/perf/config`

### T-06-08: PR-06 端到端测试

- **文件**: [meta/tests/e2e/test_perf_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/e2e/test_perf_v3_1.py`

### T-06-09: BO_PERF_MODE=v1 回滚测试

- **文件**: [meta/tests/test_rollback_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 19 个 FR 各自独立回滚

---

## 总计

| 维度 | 数值 |
|------|------|
| PR 数 | 6 |
| 任务数 | 50 |
| 预估代码量 | ~1700 行 |
| 预估测试代码 | ~800 行 |
| 预估总工时 | 200h |
| 迭代 1 (M1) | 100h |
| 迭代 2 (M2) | 100h |

---

## 依赖关系图

```
PR-01 (拦截器批量化+并行化) ────────────┐
  └─ LRUCacheWithTTL (T-01-01)         │
                                        │
PR-02 (preview 缓存+索引) ──────────────┤
  └─ depends on PR-01                   │
                                        │
PR-03 (enrichment 缓存+1 SQL) ──────────┤
  └─ depends on PR-01                   │
                                        │
PR-04 (查询优化) ───────────────────────┤
  └─ 无依赖                            │
                                        │
PR-05 (权限+审计+SQLite) ───────────────┤
  └─ 无依赖                            │
                                        │
PR-06 (可观测性+接口+末尾) ─────────────┤
  └─ depends on PR-01 (InterceptorMetrics)
                                        │
                                     (并行可)
PR-04, PR-05 互不依赖，可并行            │
PR-02, PR-03 互不依赖，可并行            │
```

---

## 风险跟踪

| 风险 | 缓解 | 跟踪 PR |
|------|------|---------|
| LRU 雪崩 | TTL + LRU 双重保护 | PR-01/02/03 |
| 索引导致写变慢 | 索引选择高读取列 | PR-02 |
| 拦截器并行破坏隔离 | 声明 parallel_safe 才启用 | PR-01 |
| 审计丢失 | 重试队列 | PR-05 |
| 缓存不一致 | TTL + 写时失效 | PR-03 |

# v1.1 增量：代码质量 + 简化治理（S-01 ~ S-10）

> **来源**: 用户"另外也整体看看代码质量，简化角度进一步全面分析下"
> **关联**: 与 v1.0 6 PR / 50 任务并行；不阻塞 v1.0
> **预计**: 7 PR / 32 任务 / 46h / -850 行
> **Back-burner**: 3 项 P3 任务暂不实施（写入跟踪）

---

## SPR-01: enrich_utils 瘦身（M1 / P0）

**关联**: S-01
**预估代码量**: -62 行
**依赖**: 无
**Owner**: TBD

### T-S01-01: 改 query_service.py 调用方

- **文件**: [meta/services/query_service.py:381, 439, 505](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L381)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/test_query_service.py`

### T-S01-02: 改 manage_api.py 调用方

- **文件**: [meta/api/manage_api.py:496](file:///d:/filework/excel-to-diagram/meta/api/manage_api.py#L496)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/test_manage_api.py`

### T-S01-03: 删 persistence_interceptor wrapper

- **文件**: [meta/core/interceptors/persistence_interceptor.py:10, 1576-1582](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L10)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 跑 `python d:\filework\test.py --file meta/tests/interceptors/test_persistence_interceptor.py`

### T-S01-04: 删 enrich_utils v1 shim

- **文件**: [meta/core/enrich_utils.py:45-62](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py#L45-L62)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 全量 `python d:\filework\test.py --unit` 通过
  - grep 验证：全工程无 `from meta.core.enrich_utils import enrich_fk`

---

## SPR-02: computed count clause 抽取（M1 / P0）

**关联**: S-02
**预估代码量**: -400 行
**依赖**: T-S02-01 (新模块先建好)
**Owner**: TBD

### T-S02-01: 新增 _computed_count_clause.py

- **文件**: [meta/core/_computed_count_clause.py](file:///d:/filework/excel-to-diagram/meta/core/_computed_count_clause.py) (new)
- **类型**: New
- **预估**: 4h
- **验证**:
  - 模块接口：parse_operator / build_subquery / apply_count_subquery
  - 单元测试：10+ case

### T-S02-02: enrich_utils.build_*_clause 改调

- **文件**: [meta/core/enrich_utils.py:129-267](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py#L129-L267)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 调用 association_engine 行为等价

### T-S02-03: persistence_interceptor filter 改调

- **文件**: [meta/core/interceptors/persistence_interceptor.py:1013-1269](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1013-L1269)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单元测试：computed filter 行为等价

### T-S02-04: persistence_interceptor sort 改调

- **文件**: [meta/core/interceptors/persistence_interceptor.py:860-1011](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L860-L1011)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 单元测试：computed sort 行为等价

### T-S02-05: 重复代码清零验证

- **文件**: 全局 grep
- **类型**: Verify
- **预估**: 0.5h
- **验证**:
  - `grep -nE "__in|__notin|__like|__gte|__lte|_start|_end" meta/core/_computed_count_clause.py` 只在 parse_operator 出现
  - 双向 COUNT subquery 只在 build_subquery 出现
  - 减码 ≥ 400 行验证

---

## SPR-03: 删 _TxnMarker（M1 / P0）

**关联**: S-05 (与 R-19 重叠)
**预估代码量**: -10 行
**依赖**: 无
**Owner**: TBD

### T-S05-01: 移除 _TxnMarker 异常类

- **文件**: [meta/core/bo_framework.py:648-656](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L648-L656)
- **类型**: Modify
- **预估**: 0.5h

### T-S05-02: 改事务失败信号传递

- **文件**: [meta/core/bo_framework.py:142-156](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L142-L156)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 事务失败时 `context.result.success=False` 直接传递，不抛异常
  - 单元测试：失败场景不抛 `_TxnMarker`

### T-S05-03: TransactionContext 简化

- **文件**: [meta/core/bo_framework.py:529-545](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L529-L545)
- **类型**: Modify
- **预估**: 0.5h
- **验证**:
  - `__exit__` 不再处理 `_TxnMarker`

---

## SPR-04: 拆 _do_list（M2 / P1）

**关联**: S-03
**预估代码量**: -200 行
**依赖**: 无
**Owner**: TBD

### T-S03-01: 抽 _build_where_clauses

- **文件**: [meta/core/interceptors/persistence_interceptor.py:396-820](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L396-L820)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 单方法 ≤ 80 行
  - 单元测试：scope / ctf / computed / semantic / search OR 各自单独覆盖

### T-S03-02: OPERATOR_HANDLERS dispatch table

- **文件**: [meta/core/interceptors/persistence_interceptor.py:489-583](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L489-L583)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 7 重 if/elif 替换为 1 个 dict dispatch
  - 行为等价单测

### T-S03-03: 抽 _build_order_by

- **文件**: [meta/core/interceptors/persistence_interceptor.py:766-805](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L766-L805)
- **类型**: Modify
- **预估**: 2h

### T-S03-04: 抽 _build_select_columns

- **文件**: [meta/core/interceptors/persistence_interceptor.py:746-762](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L746-L762)
- **类型**: Modify
- **预估**: 1h

### T-S03-05: 抽 _post_process_records

- **文件**: [meta/core/interceptors/persistence_interceptor.py:817-824](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L817-L824)
- **类型**: Modify
- **预估**: 1h

### T-S03-06: 集成测试

- **文件**: [meta/tests/interceptors/test_persistence_list_v3_1.py](file:///d:/filework/excel-to-diagram/meta/tests/interceptors/test_persistence_list_v3_1.py) (new)
- **类型**: Test
- **预估**: 4h
- **验证**:
  - 行为与拆前等价
  - 50+ 测覆盖所有操作符

---

## SPR-05: BOFramework 22→6 API（M2 / P1）

**关联**: S-04
**预估代码量**: -100 行
**依赖**: 无
**Owner**: TBD

### T-S04-01: 9 个 association 方法收口

- **文件**: [meta/core/bo_framework.py:277-396](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L277-L396)
- **类型**: Modify
- **预估**: 4h
- **验证**:
  - 9 个方法合并为 1 个 `_dispatch_association` 接收 `**kwargs`
  - 调用方改用新 API

### T-S04-02: 删 set_audit_user 别名

- **文件**: [meta/core/bo_framework.py:97-99](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L97-L99)
- **类型**: Modify
- **预估**: 0.5h

### T-S04-03: 删 execute_action / read / update / delete / query

- **文件**: [meta/core/bo_framework.py:238-258, 274-275](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L238-L258)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 调用方改用 `execute(object_type, 'crud_X', params)`

### T-S04-04: API 集成测试

- **文件**: [meta/tests/test_bo_framework_api.py](file:///d:/filework/excel-to-diagram/meta/tests/test_bo_framework_api.py) (new)
- **类型**: Test
- **预估**: 2h

---

## SPR-06: 抽 descendant_path 替代硬编码（M2 / P1）

**关联**: S-08
**预估代码量**: -50 行
**依赖**: 无
**Owner**: TBD

### T-S08-01: YAML / computation 加 descendant_path 字段

- **文件**: meta/yaml/*.yaml (domain / sub_domain / service_module)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 声明 `descendant_path: ['sub_domains:domain_id', 'service_modules:sub_domain_id', ...]`

### T-S08-02: 通用 builder 函数

- **文件**: 新增 `meta/core/_descendant_subquery.py`
- **类型**: New
- **预估**: 3h

### T-S08-03: 改写 _try_build_count_relations_filter

- **文件**: [meta/core/interceptors/persistence_interceptor.py:1271-1337](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1271-L1337)
- **类型**: Modify
- **预估**: 2h
- **验证**:
  - 67 行 → ≤ 20 行
  - 单元测试：domain / sub_domain / service_module 各自覆盖

---

## SPR-07: 微优化集合（M3 / P2+P3）

**关联**: S-06 / S-07 / S-09 / S-10
**预估代码量**: -23 行
**依赖**: 无
**Owner**: TBD

### T-S06-01: 修 _sort_by_virtual_fields

- **文件**: [meta/core/interceptors/persistence_interceptor.py:1562-1572](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1562-L1572)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 删未用 `sort_key`；改单次 sort
  - 行为等价单测

### T-S07-01: 删 Interceptor.priority 注释

- **文件**: [meta/core/interceptors/base.py:46-58](file:///d:/filework/excel-to-diagram/meta/core/interceptors/base.py#L46-L58)
- **类型**: Modify
- **预估**: 0.5h
- **验证**:
  - 删 13 行误导注释
  - 添加 `InterceptorPriority` enum（如有需要）

### T-S09-01: _pending_audit_records 改 public

- **文件**: [meta/core/action_context.py:93](file:///d:/filework/excel-to-diagram/meta/core/action_context.py#L93)
- **类型**: Modify
- **预估**: 1h
- **验证**:
  - 加 `add_pending_audit()` / `drain_pending_audits()` 方法
  - 调用方改用方法

### T-S09-02: 删 bo_framework 中 getattr 私有访问

- **文件**: [meta/core/bo_framework.py:539, 568](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L539)
- **类型**: Modify
- **预估**: 0.5h

### T-S10-01: 修 noqa: E402

- **文件**: [meta/core/interceptors/__init__.py:22](file:///d:/filework/excel-to-diagram/meta/core/interceptors/__init__.py#L22)
- **类型**: Modify
- **预估**: 0.5h
- **验证**:
  - 排查循环依赖并修复
  - `python -m py_compile meta/core/interceptors/__init__.py` 通过

---

## Back-burner (S-11 ~ S-13, 暂不实施，本期跟踪)

### T-S11-01: 统一错误处理分级（暂不实施）

- **原因**: 涉及全局推广，风险高
- **后续**: 单独 spec 评估
- **跟踪**: O1 checklist item

### T-S12-01: 类型注解一致性（暂不实施）

- **原因**: 非阻塞，不影响功能
- **后续**: 跟随 Python 3.12+ 升级时统一处理
- **跟踪**: O2 checklist item

### T-S13-01: 命名一致性（暂不实施）

- **原因**: API 表面稳定优先
- **后续**: S-04 完成后可考虑
- **跟踪**: O3 checklist item

---

## 汇总

| PR | 任务数 | 预估工时 | 减码 | 关联 |
|----|-------|---------|------|------|
| SPR-01 | 4 | 4h | -62 | S-01 |
| SPR-02 | 5 | 11.5h | -400 | S-02 |
| SPR-03 | 3 | 2h | -10 | S-05 |
| SPR-04 | 6 | 14h | -200 | S-03 |
| SPR-05 | 4 | 7.5h | -100 | S-04 |
| SPR-06 | 3 | 6h | -50 | S-08 |
| SPR-07 | 5 | 3.5h | -23 | S-06/07/09/10 |
| **合计** | **30** | **48.5h** | **-845** | — |

实际估算与 v1.0 6 PR / 50 任务 / 200h 并行：合计 12 PR / 80 任务 / 248.5h

---

**变更日志**

| 日期 | 作者 | 变更 |
|------|------|------|
| 2026-06-10 | AI Assistant | 初版 v1.0，6 PR / 50 任务 / 200h |
| 2026-06-10 | AI Assistant | v1.1 增量：增 SPR-01~SPR-07（30 任务 / 48.5h / -845 行）+ 3 back-burner |
