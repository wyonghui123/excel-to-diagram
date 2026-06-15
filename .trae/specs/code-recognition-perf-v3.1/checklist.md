# Checklist: BO Framework 性能优化 v3.1

> **关联 spec**: [spec.md](./spec.md)
> **状态**: 草案 v1.0
> **创建日期**: 2026-06-10

---

## A. 拦截器链路（FR-001 + FR-002）

### A1. 批量化

- [ ] `ContextInterceptor.before_action` 一次性 `SELECT * FROM {table} WHERE id IN (...)` 注入 `context.cached_old_data`
- [ ] `LockInterceptor.before_action` 复用 `context.cached_old_data`（不重查）
- [ ] `AuditInterceptor.before_action` 复用 `context.cached_old_data`（不重查）
- [ ] 单条 update 拦截器链路 SQL 数从 10+ 降至 5-6
- [ ] 18 拦截器链顺序保持不变
- [ ] 单元测试：批量化命中/未命中/部分命中 3 路径
- [ ] 集成测试：update 链路 SQL 数 = 5-6

### A2. 并行化

- [ ] `Interceptor` 基类新增 `parallel_safe: bool` 默认 `False`
- [ ] 18 拦截器中标识 3-5 个 `parallel_safe=True`（Context/Version/Permission）
- [ ] `bo_framework.py` 用 `ThreadPoolExecutor` 并发执行 parallel_safe
- [ ] 串行/并行仍按声明的链顺序
- [ ] 单元测试：并行执行总耗时 < 串行的 1/N
- [ ] 集成测试：context 字段不互相污染

---

## B. Preview 端点（FR-003 + FR-004）

### B1. LRU + TTL 缓存

- [ ] 新增 `meta/core/lru_cache.py` `LRUCacheWithTTL` 类
- [ ] 新增 `meta/core/preview_cache.py` `PreviewCache` 模块
- [ ] `bo_api.py:847-986` 接入 PreviewCache
- [ ] key = `hash(version_id + domain_ids + sub_domain_ids + service_module_ids + business_object_ids)`
- [ ] TTL 默认 60s，可通过 `BO_PREVIEW_CACHE_TTL` 调节
- [ ] size 上限 100，可通过 `BO_PREVIEW_CACHE_SIZE` 调节
- [ ] 命中 P95 < 50ms（基线：未命中 500ms+）
- [ ] 命中时直接返回（不查 5 张表）
- [ ] 单元测试：命中/未命中/TTL 过期/LRU 淘汰
- [ ] E2E 测试：preview 第一次 vs 第二次响应时间

### B2. 索引 + CASE 下沉

- [ ] migration 加 4 个索引：
  - `idx_relationship_source_category`
  - `idx_relationship_target_category`
  - `idx_business_object_updated_at`
  - `idx_{table}_{search_column}`（按需）
- [ ] 表大小增长 < 5%
- [ ] 10000 条 relationship preview 端到端 < 800ms
- [ ] 仅加索引，不动物理列
- [ ] migration 单测：`test_idx_relationship_v3_1.py`

---

## C. Enrichment 优化（FR-005 + FR-006 + FR-015）

### C1. LRU + TTL + 写时失效

- [ ] `_name_cache` / `_record_cache` 加 LRU 10000 上限
- [ ] 60s TTL
- [ ] `PersistenceInterceptor.after_action` 触发 `enrichment_engine.invalidate(table_name)`
- [ ] 长跑 7 天 RSS 增长 < 200MB
- [ ] 写后下一次读立即失效（单元测试断言）
- [ ] 缓存命中 P95 < 1ms

### C2. 1 SQL JOIN 合并

- [ ] `_enrich_audit_virtual_fields` + `_enrich_association_counts` + `_enrich_fk_display_names` 合并为单 SQL
- [ ] 行为完全等价（与 v1 路径对比测试）
- [ ] 单元测试：命中率/未命中/异常 3 路径
- [ ] `BO_ENRICHMENT_MODE=v1` 回退开关

### C3. FK display target_table 分组

- [ ] `enrich_fk_display_names` 按 target_table 分组
- [ ] 5 FK 字段（指向 2 表）从 5 次 SQL 降至 2 次
- [ ] 单元测试：多 FK 共享目标表场景

---

## D. 查询优化（FR-007 + FR-008 + FR-009 + FR-010）

### D1. count_all 扁平 + 缓存

- [ ] `count_all` 改为 `SELECT COUNT(*) FROM t WHERE ...`（不嵌子查询）
- [ ] count cache：key = `hash(filters + object_type + user_id)`，TTL = 30s
- [ ] `BO_COUNT_CACHE_TTL=0` 关闭缓存
- [ ] `BO_DEFAULT_SKIP_COUNT=true` 默认开启
- [ ] skip_count=True 时完全不跑 count
- [ ] 单元测试：count 命中/未命中/skip_count 路径

### D2. search N-gram + 前缀 LIKE

- [ ] search_keyword 拆为多 token
- [ ] 每个 token 走 `LIKE 'xxx%'`（前缀匹配）
- [ ] 多字段走 1 个 IN 查询
- [ ] 搜索响应 P95 < 500ms
- [ ] 不引入 FTS5（Q2=B 约束）

### D3. 虚拟排序 TEMP TABLE

- [ ] 虚拟排序走 `CREATE TEMP TABLE _sort_buf` + JOIN
- [ ] 10000 行排序 P95 < 200ms
- [ ] 翻页 P95 恒定（不随 OFFSET 增大）
- [ ] 单元测试：排序等价性 + 翻页一致性

### D4. hierarchy GROUP BY 物化

- [ ] `_sort_by_computed_field` 改为 WITH count_table 模式
- [ ] 5000 行按 relation_count 排序 P95 < 300ms
- [ ] 行为等价（与 v1 对比）
- [ ] 单元测试：等同性

---

## E. 权限 + 审计 + SQLite（FR-011 + FR-012 + FR-013 + FR-014）

### E1. 数据权限 3 SQL 合并

- [ ] `data_permission_interceptor.py:103-132` 3 次 SQL 合并为 1 次 JOIN
- [ ] per-request `context.user_permissions` 缓存
- [ ] admin 用户短路（cached property）
- [ ] 单次 query 权限开销 < 1ms

### E2. scope 表达式预编译

- [ ] `_parse_compound_expr` 解析结果缓存到 `meta_object.authorization.parsed_ast`
- [ ] `_RE_AND = re.compile(...)` 模块级
- [ ] `import re` 提到模块顶部

### E3. 审计 deferred 批 INSERT

- [ ] `_flush_pending_audit_records` 批 INSERT
- [ ] `StructuredLogger` 提升到 BOFramework 实例属性
- [ ] 100 条 pending audit 写入 < 50ms
- [ ] 写失败有重试队列
- [ ] 符合 [audit-compliance.md §1.3](file:///d:/filework/excel-to-diagram/.trae/rules/audit-compliance.md#L57-L83)

### E4. fresh_connection 复用 + WAL checkpoint

- [ ] computed 过滤时复用读池连接
- [ ] `PRAGMA wal_checkpoint(PASSIVE)` 防止读脏数据
- [ ] 事务提交后 `wal_checkpoint(TRUNCATE)`
- [ ] computed 过滤请求新增 sqlite3 connect = 0
- [ ] WAL pending frames < 100

---

## F. 可观测性 + 接口 + 末尾优化（FR-016 + FR-017 + FR-018 + FR-019）

### F1. 拦截器 Prometheus 埋点

- [ ] 18 拦截器加 `record_metric("interceptor.{name}.duration")`
- [ ] `/api/v1/_metrics` 暴露 `bo_interceptor_duration_seconds`
- [ ] trace_id 注入 SQL 注释
- [ ] `_metrics` Prometheus 格式正确

### F2. gzip 压缩

- [ ] Flask 启用 `flask-compress`
- [ ] preview/列表响应 >1KB 启用 gzip
- [ ] 5MB JSON 响应压缩后 < 1MB
- [ ] < 1KB 响应不压缩

### F3. 详情合并端点

- [ ] `read_bo` 接受 `?include=change_history,fk_display`
- [ ] 后端合并为单次查询
- [ ] 默认 change_history lazy load
- [ ] 详情 SQL 数从 5-7 降至 2-3
- [ ] 前端联调通过

### F4. 事务 + 日志优化

- [ ] `_TxnMarker` 异常改 `result.success` 显式判断
- [ ] `query_service.py:343-365` 高频 `logger.info` 改 `logger.debug`
- [ ] 事务成功路径不抛异常

---

## G. 监控与回滚（NFR-001 ~ NFR-005）

### G1. 性能基线

- [ ] `meta/tests/performance/test_baseline_v3_1.py` 输出 P50/P95/P99
- [ ] 列表 P95 < 300ms（基线：800ms-1.5s）
- [ ] 详情 P95 < 200ms
- [ ] preview P95 < 800ms
- [ ] 7 天 RSS 增长 < 200MB

### G2. 可回滚性

- [ ] `BO_PERF_MODE=v1` 一键回滚所有优化
- [ ] 19 个 FR 各自独立开关
- [ ] `meta/tests/test_rollback_v3_1.py` 覆盖 19 个开关

### G3. 兼容性

- [ ] 18 拦截器链顺序不变
- [ ] 5 层安全防线完整
- [ ] YAML 契约不变
- [ ] 不动物理列
- [ ] 0 新外部依赖

### G4. 监控端点

- [ ] `GET /api/v1/admin/perf/config` 返回当前配置
- [ ] `POST /api/v1/admin/cache/clear` 支持 scope 选择

---

## H. 文档与同步（[doc-sync-rules.md](file:///d:/filework/excel-to-diagram/.trae/rules/doc-sync-rules.md)）

- [ ] `docs/需求文档.md` 添加本功能条目
- [ ] 功能状态设置为「[IN_PROGRESS] 开发中」
- [ ] 记录 Spec 来源路径（`.trae/specs/code-recognition-perf-v3.1/`）
- [ ] 每 PR 完成更新 checklist
- [ ] 全部完成后状态改为「[DONE] 已完成」

---

## I. 里程碑验收

### M1（迭代 1）

- [ ] PR-01 ~ PR-04 全部合并
- [ ] 列表 + preview 性能提升 >= 50%
- [ ] enrichment OOM 风险消除
- [ ] M1 回顾决定 M2 调整

### M2（迭代 2）

- [ ] PR-05 + PR-06 全部合并
- [ ] 写路径 + 可观测性完成
- [ ] 内存稳定性达成
- [ ] 7 天观察期通过

---

## J. TBD 跟踪

- [ ] TBD-1 Q4 性能基线 — APM 接入后回填
- [ ] TBD-2 APM 工具确认 — 询问用户
- [ ] TBD-3 长跑 server 1 周+ 确认 — 询问用户
- [ ] TBD-4 preview 并发数确认 — APM 后填
- [ ] TBD-5 SQLite WAL 100 QPS 健康 — DRE 监控
- [ ] TBD-6 WAL checkpoint 频率 — DRE owner 确认
- [ ] TBD-7 并行拦截器清单 — 架构师审核
- [ ] TBD-8 trace_id 注入 SQL 注释 — 测试验证
- [ ] TBD-9 详情合并端点前端协作 — 联调
- [ ] TBD-10 M1 完成后回顾 — 决定 M2 调整

## K. 简化治理：enrich_utils 瘦身（S-01）

- [ ] 移除 [enrich_utils.py:45-62](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py#L45-L62) 两个 v1 兼容 shim 函数
- [ ] `query_service.py:381/439/505` 改调 `EnrichmentEngine().enrich_fk_display_names`
- [ ] `manage_api.py:496` 改调 `EnrichmentEngine().enrich_fk_display_names`
- [ ] `persistence_interceptor.py:10` 删 import；删 `_enrich_fk_display_names` / `_enrich_association_counts` wrapper
- [ ] `association_engine.py:23-27` 改调 `EnrichmentEngine()` 实例方法
- [ ] 行为等价单测：100+ 列表 + 50+ 详情查询结果一致
- [ ] 减码 -62 行

## L. 简化治理：computed count clause 抽取（S-02）

- [ ] 新增 `meta/core/_computed_count_clause.py`
- [ ] `parse_operator` / `build_subquery` / `apply_count_subquery` 三函数
- [ ] `enrich_utils.build_computed_count_filter_clause` 改调
- [ ] `enrich_utils.build_computed_count_order_clause` 改调
- [ ] `persistence_interceptor._try_build_computed_filter` 改调
- [ ] `persistence_interceptor._build_computed_count_sort_clause` 改调
- [ ] 操作符解析重复从 3 处 → 1 处
- [ ] 双向 COUNT subquery 重复从 2 处 → 1 处
- [ ] 减码 ≥ 400 行
- [ ] 单元测试：filter / sort 行为等价

## M. 简化治理：拆 `_do_list`（S-03）

- [ ] `_do_list` 从 433 行 → ≤ 100 行
- [ ] 拆出 5 个方法：`_build_where_clauses` / `_build_order_by` / `_build_select_columns` / `_execute_list_query` / `_post_process_records`
- [ ] 操作符 dispatch table（`__in` / `__notin` / `__like` / `_start` / `_end` 改为 `OPERATOR_HANDLERS` dict）
- [ ] 减码 -200 行
- [ ] 单元测试：每个新方法单独覆盖

## N. 简化治理：API / 控制流 / 微优化（S-04 ~ S-10）

- [ ] **S-04**: `BOFramework` 公开方法从 22 → ≤ 6
- [ ] **S-04**: 9 个 association 方法合并为 `_dispatch_association(**kwargs)`
- [ ] **S-04**: 删 `set_audit_user` 别名（仅留 `set_user_context`）
- [ ] **S-04**: 删 `execute_action` / `read` / `update` / `delete` / `query`（改用 `execute`）
- [ ] **S-05**: 移除 `_TxnMarker` 异常类（[bo_framework.py:648-656](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L648-L656)）
- [ ] **S-05**: 事务失败改用 `ActionResult(success=False)` 直接传递
- [ ] **S-05**: `TransactionContext.__exit__` 不再处理 `_TxnMarker`
- [ ] **S-06**: `_sort_by_virtual_fields` 删死代码 `sort_key`；改单次 sort
- [ ] **S-07**: 删 `Interceptor.priority` 注释中 9 行误导（[base.py:46-58](file:///d:/filework/excel-to-diagram/meta/core/interceptors/base.py#L46-L58)）
- [ ] **S-08**: `descendant_path` 在 YAML / computation 声明；`persistence_interceptor._try_build_count_relations_filter` 67 行 → ≤ 20 行
- [ ] **S-09**: `ActionContext._pending_audit_records` → `pending_audit_records`（public）
- [ ] **S-09**: 加 `add_pending_audit()` / `drain_pending_audits()` 方法
- [ ] **S-10**: 修 `interceptors/__init__.py:22` `# noqa: E402`（排查循环依赖）
- [ ] 减码合计 -178 行

## O. Back-burner（暂不实施，本期跟踪）

- [ ] **S-11 (P3)**: 统一错误处理分级（silent_for_debug / warn_for_data / error_for_5xx / fatal_for_data_corrupt）— 涉及全局推广，风险高，本期不纳入
- [ ] **S-12 (P3)**: 类型注解一致性（`int = None` → `Optional[int] = None`）
- [ ] **S-13 (P3)**: 命名一致性（`enrich_utils` → `enrich_compat`、`_get_engine` → `_get_enrichment_engine`）

---

**变更日志**

| 日期 | 作者 | 变更 |
|------|------|------|
| 2026-06-10 | AI Assistant | 初版 v1.0 |
| 2026-06-10 | AI Assistant | v1.1 增量：增 K-O 五大验收类（11 项简化治理 + 3 back-burner） |
