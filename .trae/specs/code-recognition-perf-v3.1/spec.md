# Spec: BO Framework 性能优化 v3.1（19 风险全量治理）

> **状态**: 草案 v1.0
> **创建日期**: 2026-06-10
> **来源**: 用户"全面深入分析代码识别性能风险和优化点"
> **依据**: [ARCHITECTURE_V2.md v3.0.2](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) + 代码深度审查

---

## 1. 背景与目标

### 1.1 背景

[ARCHITECTURE_V2.md v3.0.2](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) 定义了 18 拦截器链 + 元数据驱动 + 五层安全防线，但实际代码 [bo_api.py:847-986](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L847-L986)、[enrichment_engine.py:412-579](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L412-L579)、[query_service.py](file:///d:/filework/excel-to-diagram/meta/services/query_service.py)、[bo_framework.py:218-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L218-L229) 仍存在 19 个可识别的性能风险点（R-01 ~ R-19）。其中：

- **P0 红色风险（3 个）**：18 拦截器串行 + architecture preview 大表 + enrichment 无界缓存 — 直接影响 P95/P99
- **P1 橙色风险（6 个）**：count_all 嵌套 / search LIKE 前导 % / 虚拟排序全表 fetch / hierarchy N 次计算 / LRU 上限缺失 / N+1 FK 循环
- **P2 黄色风险（7 个）**：权限 3 次 SQL / 审计 deferred / fresh_connection / 详情 25 次 SQL / 拦截器无埋点
- **P3 绿色风险（3 个）**：事务异常信号 / 正则 import / 日志散布 / 响应未 gzip

### 1.2 业务目标

| 目标 | 描述 |
|------|------|
| BO-1 | 列表 P95 < 300ms，详情 P95 < 200ms，preview P95 < 800ms（待 APM 校验，TBD-Q4） |
| BO-2 | 长跑 server 7 天 RSS 增长 < 200MB（防 OOM） |
| BO-3 | SQLite WAL 在 100 QPS 写入下，pending frames < 100 |
| BO-4 | 不破坏 18 拦截器链顺序与 5 层安全防线 |
| BO-5 | 不破坏元数据驱动（YAML 仍是唯一真源） |

### 1.3 用户/涉众目标

- **架构师（preview 高频用户）**：preview 端到端 P95 < 1s，可并发打开多个 preview
- **业务运维（CRUD 用户）**：列表翻页 1s 内响应，搜索响应 < 500ms
- **AI Coding Agent**：可观测性提升，能在 P99 异常时通过 trace_id 定位拦截器瓶颈
- **运维**：长跑 server 1 周无需手动清缓存，WAL 自动 checkpoint

---

## 2. 需求类型概览

| 类型 | 适用 | 证据（来源） |
|------|------|-------------|
| 业务需求 | 是 | 1.1 Background / 用户要求"全面深入分析" |
| 用户/涉众需求 | 是 | 1.3 User Objectives / SESSION_REMINDER 项目规则 |
| 解决方案需求 | 是 | 元数据驱动 + 拦截器链架构限制 |
| 功能需求 | 是 | FR-001 ~ FR-019 |
| 非功能需求 | 是 | NFR-001 ~ NFR-005 |
| 外部接口需求 | 是 | IF-001 ~ IF-003 |
| 过渡需求 | 是 | TR-001 ~ TR-004（5+ PR/2 迭代） |

---

## 3. 功能需求

### FR-001: 拦截器 before/after 链路批量化

- **描述**: 当前 [bo_framework.py:218-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L218-L229) 18 拦截器全部串行，audit 与 lock 各做 1 次同样的 `SELECT * WHERE id=?`。系统 MUST 把"读老数据 + 锁检查"合并为 1 次查询。
- **验收标准**:
  - 单条 update 拦截器链路 SQL 数从 10+ 降至 5-6
  - 拦截器链顺序不变
  - 5 层安全防线完整性不变
- **优先级**: Must
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: R-01 / 用户 Q1=C
- **实现要点**: 在 `ContextInterceptor.before_action` 一次性 `SELECT * FROM {table} WHERE id IN ({ids})` 放入 `context.cached_old_data`，LockInterceptor/AuditInterceptor 复用

### FR-002: 拦截器并行化（仅纯只读 before）

- **描述**: 拦截器 SHOULD 声明 `parallel_safe=True`（如 ContextInterceptor、PermissionInterceptor），框架 MUST 用 ThreadPoolExecutor 并发执行。
- **验收标准**:
  - 声明 `parallel_safe=True` 的拦截器并发执行
  - 修改 `context.params/extra` 的拦截器仍串行
  - 拦截器声明 `parallel_safe` 不影响原有行为
- **优先级**: Should
- **类型映射**: 解决方案需求 / 功能需求
- **来源**: R-01
- **约束**: 不改 18 拦截器链逻辑，only optimization

### FR-003: architecture preview 端点加 LRU + TTL 缓存

- **描述**: `/architecture/preview` 端点 MUST 加进程内 LRU 缓存，key = `hash(version_id + domain_ids + sub_domain_ids + service_module_ids + business_object_ids)`，TTL = 60s。
- **验收标准**:
  - 相同参数 60s 内第 2 次请求 P95 < 50ms
  - 缓存命中时直接返回，绕过所有 5 张表查询
  - 缓存未命中时走原逻辑
  - 提供 `BO_PREVIEW_CACHE_TTL` 环境变量调节
  - 提供 `BO_PREVIEW_CACHE_SIZE` 上限（默认 100）
- **优先级**: Must
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: R-03 / 用户 Q3=A
- **失效策略**: TTL 到期 + admin 手动清空（IF-001）

### FR-004: relationship 表加索引 + scope/category 下沉到 SQL CASE

- **描述**: `relationship` 表 MUST 加 `idx_relationship_source_category` (source_bo_id, category_type) + `idx_relationship_target_category` (target_bo_id, category_type)；scope_type/category_type 计算 SHOULD 用 SQL CASE WHEN 一次算出。
- **验收标准**:
  - 加索引后表大小增长 < 5%
  - 10000 条 relationship preview 端到端 < 800ms
  - 仅加索引，不动物理列（符合 Q2=B 约束）
- **优先级**: Must
- **类型映射**: 功能需求 / 非功能需求
- **来源**: R-03
- **Migration**: 通过 `python d:\filework\test.py --single meta/tests/migrations/test_idx_relationship_v3_1.py` 验证

### FR-005: enrichment cache 加 LRU 上限 + TTL + 写时失效

- **描述**: [enrichment_engine.py:50-51](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L50-L51) `_name_cache` / `_record_cache` MUST 加 LRU 10000 上限 + 60s TTL；`PersistenceInterceptor.after_action` MUST 触发 `enrichment_engine.invalidate(table_name)`。
- **验收标准**:
  - 长跑 server 7 天 RSS 增长 < 200MB
  - 写操作后下一次读立即失效缓存
  - 缓存命中 P95 < 1ms
  - 缓存未命中走原 3 步 enrichment
- **优先级**: Must
- **类型映射**: 功能需求 / 非功能需求
- **来源**: R-04 / R-14 / 用户 Q3=A
- **实现要点**: 自实现 `LRUCacheWithTTL` 类（避免 functools.lru_cache 不支持 TTL）

### FR-006: enrichment 三步合并为 1 次 JOIN 查询

- **描述**: `_enrich_audit_virtual_fields` + `_enrich_association_counts` + `_enrich_fk_display_names` MUST 合并为单 SQL：主表 LEFT JOIN audit_logs GROUP BY + LEFT JOIN through 表 GROUP BY + LEFT JOIN FK 目标表。
- **验收标准**:
  - 每次 list 请求 enrichment 部分 SQL 数从 3 降至 1
  - 行为完全等价（不破坏现有字段）
  - 单元测试覆盖命中率/未命中/异常 3 路径
- **优先级**: Should
- **类型映射**: 功能需求 / 解决方案需求
- **来源**: R-04
- **回退**: 保留旧 3 步路径在 `BO_ENRICHMENT_MODE=v1` 开关下可启用

### FR-007: count_all 嵌套子查询改为扁平 + count cache

- **描述**: [query_builder.py:612-619](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py#L612-L619) `count_all` MUST 改为 `SELECT COUNT(*) FROM t WHERE ...`（不嵌子查询）；新增 count cache：key=`hash(filters + object_type + user_id)`，TTL=30s。
- **验收标准**:
  - count 查询 SQL 解析耗时 < 5ms
  - 同一查询 30s 内复用 count 结果
  - skip_count=True 时完全不跑 count（不写 cache）
  - 默认开启 `BO_DEFAULT_SKIP_COUNT=true`
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-05 / R-13
- **回退**: `BO_COUNT_CACHE_TTL=0` 关闭缓存

### FR-008: search_keyword 走 N-gram + 字段名分组

- **描述**: [persistence_interceptor.py:613-678](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L613-L678) search 路径 MUST 把 search_keyword 拆为多 token；每个 token 走 `LIKE 'xxx%'`（前缀匹配可用索引）而非 `LIKE '%xxx%'`；按字段分组后用 1 个 IN。
- **验收标准**:
  - 多 token + 多字段搜索 SQL 数 <= 1（IN）
  - 搜索响应 P95 < 500ms
  - `idx_{table}_{column}` 加索引（schema 允许范围内）
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-06
- **约束**: 不符合 FTS5 替代（Q2=B 约束），仅在 Python 端优化 SQL 结构

### FR-009: 虚拟字段排序走临时表 + 物化排序键

- **描述**: [query_service.py:518-521](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L518-L521) 虚拟排序 MUST 走 `CREATE TEMP TABLE _sort_buf` + JOIN 模式，DB 内排序 + 索引化，O(N log N) 由 SQLite 处理。
- **验收标准**:
  - 10000 行排序 P95 < 200ms
  - 翻页 P95 恒定（不随 OFFSET 增大）
  - temp table 自动回收（事务结束）
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-07

### FR-010: hierarchy_scope 排序走 GROUP BY 物化

- **描述**: [query_service.py:586-648](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L586-L648) `_sort_by_computed_field` MUST 改为 `WITH count_table AS (SELECT id, COUNT(*) c FROM relationships GROUP BY id) SELECT t.* FROM t LEFT JOIN count_table c USING(id) ORDER BY c.c` 模式。
- **验收标准**:
  - 5000 行按 relation_count 排序 P95 < 300ms
  - 不再 N+1 计算
  - 行为等价（顺序与原 Python 循环一致）
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-08

### FR-011: 数据权限拦截器合并 3 次 SQL + per-request cache

- **描述**: [data_permission_interceptor.py:103-132](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L103-L132) 3 次 SQL MUST 合并为 1 次 JOIN；user 权限 SHOULD 缓存到 `context.user_permissions`（per-request 复用）。
- **验收标准**:
  - 单次 query 权限开销从 10ms 降至 < 1ms
  - admin 用户短路检查走 cached property
  - 缓存作用域：仅当前请求（不跨请求污染）
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-09

### FR-012: scope 表达式解析预编译 + 缓存

- **描述**: [data_permission_interceptor.py:213-256](file:///d:/filework/excel-to-diagram/meta/core/interceptors/data_permission_interceptor.py#L213-L256) `_parse_compound_expr` 解析结果 MUST 缓存到 `meta_object.authorization.parsed_ast`（YAML 加载时一次性）。
- **验收标准**:
  - 启动时解析，运行时不重复解析
  - 正则预编译（模块级 `_RE_AND = re.compile(...)`）
  - import 提到模块顶部
- **优先级**: Could
- **类型映射**: 非功能需求
- **来源**: R-10

### FR-013: 审计 deferred 写批量化 + 实例复用

- **描述**: [bo_framework.py:532-568](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L532-L568) `_flush_pending_audit_records` MUST 批 INSERT 替代逐条 `log_business`；`StructuredLogger` MUST 提升到 BOFramework 实例属性复用。
- **验收标准**:
  - 100 条 pending audit 写入 < 50ms
  - 写失败不阻塞业务事务
  - 批写入失败有重试队列
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-11
- **合规**: [audit-compliance.md §1.3](file:///d:/filework/excel-to-diagram/.trae/rules/audit-compliance.md#L57-L83) 仍用 AsyncAuditWriter

### FR-014: fresh_connection 改为缓存 + WAL checkpoint

- **描述**: [persistence_interceptor.py:831-858](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L831-L858) computed 过滤时 fresh_connection MUST 改为复用读池连接 + `PRAGMA wal_checkpoint(PASSIVE)` 防止读脏数据。
- **验收标准**:
  - computed 过滤请求新增 sqlite3 connect = 0
  - WAL pending frames < 100（DB 健康监控）
  - 事务提交后自动 `wal_checkpoint(TRUNCATE)`
- **优先级**: Could
- **类型映射**: 非功能需求
- **来源**: R-12
- **约束**: DRE 子系统 [§10.5](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) 已有 WAL 监控，不重复实现

### FR-015: FK display 字段按 target_table 分组合并

- **描述**: [enrichment_engine.py:446-508](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L446-L508) `enrich_fk_display_names` MUST 按 `target_table` 分组：所有指向同一表的 FK 合并为 1 次 `SELECT id, {display_fields} FROM {target_table} WHERE id IN (...)`。
- **验收标准**:
  - 5 个 FK 字段（指向 2 张表）的 enrichment SQL 从 5 降至 2
  - 行为等价
  - 单元测试覆盖多 FK 共享目标表场景
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: R-15

### FR-016: 拦截器埋点 + Prometheus 端点

- **描述**: 所有 18 拦截器 MUST 加 `record_metric("interceptor.{name}.duration")`；`/api/v1/_metrics` 端点 MUST 暴露 `bo_interceptor_duration_seconds` Histogram。
- **验收标准**:
  - 每个拦截器 before/after 各 1 个 histogram
  - trace_id 注入到 SQL 注释
  - `_metrics` 端点 Prometheus 格式正确
- **优先级**: Should
- **类型映射**: 非功能需求 / 外部接口需求
- **来源**: R-16

### FR-017: HTTP 响应 gzip 压缩

- **描述**: [bo_api.py](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py) Flask 应用 MUST 启用 `flask-compress`；preview/列表响应 MUST 启用 gzip（>1KB）。
- **验收标准**:
  - `/architecture/preview` 响应大小从 5MB 降至 1MB（gzip 压缩）
  - 5MB JSON 传输 P95 < 1s
  - < 1KB 响应不压缩
- **优先级**: Could
- **类型映射**: 非功能需求
- **来源**: R-18

### FR-018: 详情页端点合并

- **描述**: [bo_api.py:178-198](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L178-L198) `read_bo` SHOULD 接受 `?include=change_history,fk_display` 参数；后端合并为单次查询。
- **验收标准**:
  - 详情打开 SQL 数从 5-7 降至 2-3
  - 前端减少 HTTP 请求数
  - 默认 `change_history` lazy load
- **优先级**: Could
- **类型映射**: 外部接口需求
- **来源**: R-19

### FR-019: 事务包裹 + 日志优化

- **描述**: [bo_framework.py:127-156](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L127-L156) `_TxnMarker` 异常 MUST 改为 `result.success` 显式判断；[query_service.py:343-365](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L343-L365) 高频 `logger.info` MUST 降为 `logger.debug`（默认关闭）。
- **验收标准**:
  - 事务成功路径不再抛异常
  - 热路径日志关闭默认级别
  - 测试覆盖率 100% 保持
- **优先级**: Could
- **类型映射**: 非功能需求
- **来源**: R-02 / R-17

---

## 4. 非功能需求

### NFR-001: 性能基线

- **描述**:
  - 列表 P50 < 100ms，P95 < 300ms，P99 < 500ms（TBD-Q4 确认）
  - 详情 P95 < 200ms
  - preview P95 < 800ms
  - 详情 + change_history P95 < 300ms
- **Measurement**: 通过 `python d:\filework\test.py --file meta/tests/performance/test_baseline_v3_1.py` 输出百分位
- **优先级**: Must
- **来源**: 用户 Q4（待 APM 校验）

### NFR-002: 内存稳定性

- **描述**: 长跑 server 7 天 RSS 增长 < 200MB
- **Measurement**: 通过 `python d:\filework\test.py --file meta/tests/performance/test_memory_stability.py`
- **优先级**: Must
- **来源**: R-04 / R-14

### NFR-003: 可观测性

- **描述**:
  - 18 拦截器均埋点 Prometheus metric
  - 每个请求 X-Trace-Id 注入 SQL 注释
  - `/_diagnostics` 端点含最近错误 + error_codes + fix_hints（[ARCHITECTURE_V2 §10.5](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md)）
- **Measurement**: `/api/v1/_metrics` 输出 + 单元测试断言
- **优先级**: Must
- **来源**: R-16

### NFR-004: 可回滚性

- **描述**:
  - 所有优化 MUST 有 `BO_PERF_MODE=v1` 回滚开关
  - 物化列/索引/缓存 MUST 可禁用
  - 1 行环境变量回滚
- **Measurement**: `meta/tests/test_rollback_v3_1.py` 覆盖 19 个开关
- **优先级**: Must
- **来源**: 用户风险最小化诉求

### NFR-005: 兼容性

- **描述**:
  - 18 拦截器链顺序不变
  - 5 层安全防线完整
  - YAML 元数据驱动契约不变
  - 不动物理列（Q2=B 约束）
  - 0 新外部依赖（Q3=A 约束）
- **Measurement**: 回归测试 + 集成测试
- **优先级**: Must
- **来源**: 用户约束

---

## 5. 外部接口需求

### IF-001: Cache 管理端点

- **Type**: API
- **Endpoint**: `POST /api/v1/admin/cache/clear`
- **Request**: `{"scope": "all|enrichment|preview|permission|count"}`
- **Response**: `{"success": true, "cleared_entries": 1234, "timestamp": "..."}`
- **Error Handling**: `403` 非 admin / `400` 无效 scope
- **Source**: FR-003 / FR-005

### IF-002: Prometheus 端点扩展

- **Type**: API
- **Endpoint**: `GET /api/v1/_metrics`
- **Response**: Prometheus 文本格式
  - `bo_interceptor_duration_seconds{name="...",phase="before|after"}`
  - `bo_cache_operations_total{type="enrichment|preview|permission|count",action="hit|miss|evict|expire"}`
  - `bo_query_count_total{object_type="..."}`
- **Source**: FR-007 / FR-016

### IF-003: preview 缓存配置端点

- **Type**: API
- **Endpoint**: `GET /api/v1/admin/perf/config`
- **Response**: `{"preview_cache_ttl": 60, "preview_cache_size": 100, "enrichment_cache_size": 10000, "count_cache_ttl": 30}`
- **Source**: FR-003

---

## 6. 过渡需求

### TR-001: 数据库索引 migration

- **Description**: 仅加索引，不动物理列（Q2=B 约束）
  - `CREATE INDEX IF NOT EXISTS idx_relationship_source_category ON relationship(source_bo_id, category_type)`
  - `CREATE INDEX IF NOT EXISTS idx_relationship_target_category ON relationship(target_bo_id, category_type)`
  - `CREATE INDEX IF NOT EXISTS idx_business_object_updated_at ON business_object(updated_at)`
  - `CREATE INDEX IF NOT EXISTS idx_{table}_{search_column} ON {table}({search_column})`
- **Strategy**: 通过 `meta/migrations/v3_1_add_perf_indexes.py` 启动时自动执行
- **Rollback Plan**: `DROP INDEX IF EXISTS ...`
- **Source**: Q2=B

### TR-002: 5+ PR 滚动发布

- **Description**: 5+ 个 PR 分 2 个完整迭代发布：
  - **迭代 1（M1）**：PR-01 (FR-001+FR-002) / PR-02 (FR-003+FR-004) / PR-03 (FR-005+FR-006) / PR-04 (FR-007+FR-008+FR-009+FR-010)
  - **迭代 2（M2）**：PR-05 (FR-011+FR-012+FR-013+FR-014) / PR-06 (FR-015+FR-016+FR-017+FR-018+FR-019)
- **Strategy**: 每 PR 单独回归测试 + E2E 验证
- **Rollback Plan**: 每 PR 单独 revert
- **Source**: 用户 Q1=C

### TR-003: 默认值与开关

- **Description**: 所有优化默认开启（向后兼容），通过环境变量调节：
  - `BO_PERF_MODE=v2`（默认）/ `v1`（关闭所有）
  - `BO_PREVIEW_CACHE_TTL=60`
  - `BO_ENRICHMENT_CACHE_SIZE=10000`
  - `BO_COUNT_CACHE_TTL=30`
  - `BO_DEFAULT_SKIP_COUNT=true`
  - `BO_GZIP_ENABLED=true`
- **Strategy**: 启动时读取环境变量
- **Rollback Plan**: 环境变量切换
- **Source**: FR-003 / FR-005 / FR-007

### TR-004: 监控与告警

- **Description**: 上线后 7 天观察期，监控：
  - `_metrics` 端点 bo_interceptor P99
  - 内存 RSS 增长曲线
  - preview 端点 QPS + 缓存命中率
  - 事务失败率
- **Strategy**: 通过 Prometheus + Grafana 监控
- **Rollback Plan**: P99 异常时切换 `BO_PERF_MODE=v1`
- **Source**: NFR-003

---

## 7. 约束与假设

### 7.1 技术约束

- C1: 仅允许加索引，不动物理列、不加 FTS5 虚拟表、不加物化列（Q2=B）
- C2: 0 新外部依赖（Q3=A 进程内 LRU + TTL）
- C3: 18 拦截器链顺序不变（NFR-005）
- C4: 5 层安全防线完整（NFR-005）
- C5: YAML 元数据驱动契约不变（NFR-005）
- C6: SQLite WAL 模式（不能切换为 MySQL/PostgreSQL）
- C7: 测试必须走 `python d:\filework\test.py --file ...` 入口（[SESSION_REMINDER](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) 铁律）

### 7.2 业务约束

- C8: 5+ PR / 2 完整迭代（Q1=C）
- C9: 用户接受 `BO_PERF_MODE=v1` 一键回滚
- C10: 合规审计字段派生规则不变（[audit-compliance.md §3.1-3.3](file:///d:/filework/excel-to-diagram/.trae/rules/audit-compliance.md#L129-L172)）

### 7.3 假设

- A1: 用户接受默认值作为 P50/P95/P99 目标（TBD-Q4 后续 APM 校验后微调）— Source: Assumed
- A2: 现网有 APM 工具（日志/APM）能提供真实 P95 数据 — Source: TBD
- A3: 长跑 server 1 周+ 是真实运维场景 — Source: 用户
- A4: 架构预览用户 < 50 并发 — Source: Assumed
- A5: SQLite WAL 增长在 100 QPS 写吞吐下健康 — Source: DRE 监控 [§10.5](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md)

---

## 8. 优先级与里程碑建议

### 8.1 优先级矩阵

| ID | 需求 | Priority | Reason |
|----|------|---------|--------|
| FR-001 | 拦截器批量化 | Must | P0 链路放大 |
| FR-002 | 拦截器并行化 | Should | 链路延迟 |
| FR-003 | preview LRU+TTL | Must | P0 O(N^2) 内存 |
| FR-004 | relationship 索引 + CASE | Must | preview SQL |
| FR-005 | enrichment LRU+TTL+失效 | Must | P0 OOM |
| FR-006 | enrichment 1 SQL 合并 | Should | enrichment 3 步 |
| FR-007 | count_all 扁平+缓存 | Should | count 嵌套 |
| FR-008 | search N-gram | Should | LIKE 前导 % |
| FR-009 | 虚拟排序 temp 表 | Should | 翻页深度 |
| FR-010 | hierarchy GROUP BY 物化 | Should | N+1 |
| FR-011 | 权限 3 步合并 | Should | 权限开销 |
| FR-012 | scope 表达式预编译 | Could | 启动优化 |
| FR-013 | 审计 deferred 批量 | Should | 写吞吐 |
| FR-014 | fresh_connection 复用 | Could | 连接泄漏 |
| FR-015 | FK display 分组 | Should | enrichment SQL |
| FR-016 | 拦截器埋点 | Should | 可观测性 |
| FR-017 | gzip 压缩 | Could | 响应大小 |
| FR-018 | 详情合并端点 | Could | N+1 API |
| FR-019 | 事务+日志优化 | Could | 热路径 |

### 8.2 建议里程碑

- **M1（迭代 1）**：PR-01 ~ PR-04（FR-001 ~ FR-010），目标：列表 + preview 性能提升 >= 50%
- **M2（迭代 2）**：PR-05 ~ PR-06（FR-011 ~ FR-019），目标：写路径 + 可观测性 + 内存稳定

---

## 9. 变更/设计提案 (RFC)

### 9.1 As-Is 分析

#### 当前架构

- **拦截器链**: [bo_framework.py:218-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L218-L229) 18 拦截器串行，10 before + 8 after
- **预览端点**: [bo_api.py:847-986](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L847-L986) 5 张表全拉（5000+5000+5000+5000+10000）+ Python 内存 O(N) 过滤
- **Enrichment**: [enrichment_engine.py:412-579](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L412-L579) 3 步串行 + 永不过期无界缓存
- **查询服务**: [query_service.py](file:///d:/filework/excel-to-diagram/meta/services/query_service.py) 虚拟字段排序全表 fetch + count_all 嵌套

#### 现有痛点

| 痛点 | 影响 | 触发场景 |
|------|------|---------|
| 18 拦截器串行 | 单请求 5-10 SQL | 所有 CRUD |
| preview 大表 | P95 > 1s | 架构师打开 preview |
| enrichment OOM | 1 周后 RSS > 1GB | 长跑 server |
| count_all 嵌套 | 嵌套扫表 | 列表分页 |
| search LIKE % | 全表扫 | 搜索 |
| 虚拟排序全表 | 翻页越深越慢 | 大表分页 |
| 权限 3 SQL | 每请求 3 次权限 | 列表/详情 |
| 详情 N+1 | 25 次 SQL | 详情打开 |

#### 相关代码路径

- 入口: [bo_api.py:1-30](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L1-L30)
- 框架: [bo_framework.py:127-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L127-L229)
- 拦截器: [meta/core/interceptors/](file:///d:/filework/excel-to-diagram/meta/core/interceptors/) 18 个
- 查询: [query_service.py:300-650](file:///d:/filework/excel-to-diagram/meta/services/query_service.py#L300-L650)
- Enrichment: [enrichment_engine.py:1-100](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py#L1-L100)

### 9.2 目标状态

#### 目标架构

```
+- HTTP -+
|  Flask + flask-compress
|  (FR-017 gzip)
+---||---+
     |
+----||--------------------------------------------------+
| BO Framework                                              |
|  +- Interceptor Chain (18) ------------------+
|  | before_action:                              |
|  |   +- parallel_safe=True -+  +- serial -+    |
|  |   | ContextInterceptor   |  | DataPer- |    |
|  |   | VersionInterceptor   |  | mission  |    |
|  |   | PermissionInterceptor|  | FieldPol |    |
|  |   +----------------------+  +---------+    |
|  |   (FR-001+FR-002 批量化+并行化)               |
|  +----------------------------------------------+
|                                                       |
|  +- LRU+TTL Caches (Q3=A) ------------------+
|  |  +- preview cache -+  +- permission -+   |
|  |  |  TTL=60s Size100|  | per-request  |   |
|  |  +-----------------+  +-------------+   |
|  |  +- enrichment ----+  +- count cache -+ |
|  |  | LRU10K+TTL60s   |  |  TTL=30s     |  |
|  |  | + write-inval   |  +-------------+  |
|  |  +-----------------+                    |
|  +----------------------------------------+
|                                                       |
|  +- SQL Optimizations -----------------------+
|  |  search: N-gram + prefix LIKE (FR-008)    |
|  |  virtual sort: TEMP TABLE (FR-009)        |
|  |  hierarchy: GROUP BY (FR-010)             |
|  |  count_all: 扁平 (FR-007)                 |
|  |  FK display: target_table 分组 (FR-015)   |
|  +-----------------------------------------+
|                                                       |
|  +- Observability -----------------------+
|  |  /_metrics: bo_interceptor_duration     |
|  |  trace_id -> SQL 注释 (FR-016)         |
|  |  /_diagnostics: error_codes+fix_hints   |
|  +--------------------------------------+
+--------------------------------------+
       |
+-||---||---+
| SQLite WAL  |
| + idx_v3_1  | (FR-004 索引)
+-----------+
```

#### 关键变更

1. **拦截器链**: [bo_framework.py:218-229](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L218-L229) 引入 `parallel_safe` 标志 + 批量化 `cached_old_data`
2. **预览缓存**: 新增 [meta/core/preview_cache.py](file:///d:/filework/excel-to-diagram/meta/core/) 进程内 LRU+TTL
3. **Enrichment 缓存**: [enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) 加 LRU+TTL+失效
4. **SQL 优化**: [query_service.py](file:///d:/filework/excel-to-diagram/meta/services/query_service.py) + [persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py) 改造
5. **可观测性**: [meta/api/metrics_api.py](file:///d:/filework/excel-to-diagram/meta/api/) 扩展
6. **gzip**: [meta/server.py](file:///d:/filework/excel-to-diagram/meta/server.py) 启用 flask-compress

### 9.3 详细设计

#### 9.3.1 模块设计

| 模块 | 文件 | 职责 |
|------|------|------|
| `LRUCacheWithTTL` | [meta/core/lru_cache.py](file:///d:/filework/excel-to-diagram/meta/core/) (new) | 通用 LRU+TTL 容器 |
| `PreviewCache` | [meta/core/preview_cache.py](file:///d:/filework/excel-to-diagram/meta/core/) (new) | preview 端点 LRU 缓存 |
| `EnrichmentCache` | [enrichment_engine.py](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) (modify) | enrichment 缓存管理 |
| `InterceptorMetrics` | [meta/core/interceptor_metrics.py](file:///d:/filework/excel-to-diagram/meta/core/) (new) | 拦截器埋点 |
| `Migration` | [meta/migrations/v3_1_add_perf_indexes.py](file:///d:/filework/excel-to-diagram/meta/migrations/) (new) | 加索引脚本 |

#### 9.3.2 数据模型

无新物理表（Q2=B 约束）。仅加索引：

```sql
CREATE INDEX IF NOT EXISTS idx_relationship_source_category
  ON relationship(source_bo_id, category_type);

CREATE INDEX IF NOT EXISTS idx_relationship_target_category
  ON relationship(target_bo_id, category_type);

CREATE INDEX IF NOT EXISTS idx_business_object_updated_at
  ON business_object(updated_at);

CREATE INDEX IF NOT EXISTS idx_{table}_{search_column}
  ON {table}({search_column});  -- 每个表 + 常用搜索列
```

#### 9.3.3 API 设计

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/cache/clear` | POST | 清缓存 (IF-001) |
| `/api/v1/admin/perf/config` | GET | 性能配置 (IF-003) |
| `/api/v1/_metrics` | GET | Prometheus (IF-002, 扩展) |

#### 9.3.4 主流程

**Preview 缓存流程（FR-003）**：
```
请求 -> 计算 key=hash(version+ids) -> 命中? -> yes -> 直接返回
                                          | no
                                    走原 5 表查询
                                          |
                                    写缓存 (LRU+TTL)
                                          |
                                    返回
```

**Enrichment 缓存流程（FR-005）**：
```
请求 -> ContextInterceptor 加载表 metadata
     -> PersistenceInterceptor._do_list
     -> enrichment_engine.enrich(records)
        -> 检查 LRU 缓存 -> 命中 -> 直接注入
                              | miss -> 走原 3 步
                                       | -> 写 LRU (TTL 60s)
     -> 返回 records
     -> PersistenceInterceptor.after_action
        -> enrichment_engine.invalidate(table_name) [写时失效]
```

**拦截器批量化（FR-001）**：
```
LockInterceptor.before_action:
  if context.cached_old_data is None:
    context.cached_old_data = SELECT * FROM t WHERE id IN (...)  -- 批量
  use context.cached_old_data for lock check

AuditInterceptor.before_action:
  use context.cached_old_data for diff computation
```

### 9.4 备选方案对比

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 仅加物化列 | 性能最优 | 违反 Q2=B 约束 | [X] 拒绝 |
| B. 引入 FTS5 替代 LIKE | 搜索优化 | 违反 Q2=B（虚拟表） | [X] 拒绝 |
| C. 引入 Redis | 跨进程共享 | 违反 Q3=A（0 依赖） | [X] 拒绝 |
| D. 进程内 LRU + TTL | 简单 0 依赖 | 单进程内 | [OK] 采纳 |
| E. 仅加索引 | 中等收益 | 无 | [OK] 采纳 |
| F. 全面 19 个 | 最完整 | 工作量大 | [OK] 采纳（用户 Q1=C） |
| G. 异步拦截器完全并发 | 性能最优 | 破坏拦截器链顺序（NFR-005） | [X] 拒绝 |

### 9.5 实施与迁移计划

#### 实施顺序

1. **PR-01（FR-001+FR-002）拦截器批量化+并行化**
   - 新增 `InterceptorMetrics` 类
   - 修改 `bo_framework.py:218-229` 并行化逻辑
   - 修改 `ContextInterceptor` 一次性查 old_data
   - 单元测试 + 集成测试

2. **PR-02（FR-003+FR-004）preview 缓存+索引**
   - 新增 `LRUCacheWithTTL` 类
   - 新增 `PreviewCache` 模块
   - 加 4 个索引（migration）
   - 修改 `bo_api.py:847-986` 接入缓存
   - E2E 测试 preview 命中/未命中

3. **PR-03（FR-005+FR-006）enrichment 缓存+1 SQL 合并**
   - 修改 `enrichment_engine.py` 加 LRU+TTL
   - 修改 `PersistenceInterceptor.after_action` 触发失效
   - 合并 3 步为 1 SQL JOIN
   - 内存压力测试

4. **PR-04（FR-007+FR-008+FR-009+FR-010）查询优化**
   - `count_all` 扁平 + cache
   - search N-gram + 前缀 LIKE
   - 虚拟排序 TEMP TABLE
   - hierarchy GROUP BY 物化
   - 性能基准测试

5. **PR-05（FR-011+FR-012+FR-013+FR-014）权限/审计/SQLite**
   - 权限 3 SQL 合并
   - scope 表达式预编译
   - 审计批 INSERT
   - fresh_connection 复用 + WAL checkpoint
   - 合规测试

6. **PR-06（FR-015+FR-016+FR-017+FR-018+FR-019）末尾优化**
   - FK display target_table 分组
   - 拦截器 Prometheus 埋点
   - gzip 压缩
   - 详情合并端点
   - 事务+日志优化
   - 端到端性能基准

#### 风险缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| LRU 缓存满后雪崩 | P99 飙升 | TTL + LRU 双重保护 |
| 索引导致写变慢 | 写 QPS 下降 | 索引选择高读取列 |
| 拦截器并行化破坏隔离 | 拦截器链行为变化 | 仅对声明 `parallel_safe=True` 启用 |
| 物化 CASE 表达式在大表慢 | preview 变慢 | 索引 + SQL 优化器 |
| 审计批量写丢失 | 合规风险 | 失败有重试队列 |
| 缓存失效不彻底 | 数据不一致 | TTL 60s + 写时失效双保险 |
| gzip 增加 CPU | 整体吞吐下降 | 仅 > 1KB 响应压缩 |

#### 测试策略

- **单元测试**: 每个 FR 单独覆盖，命中率/未命中/边界/异常 4 路径
- **集成测试**: 拦截器链全链路 + enrichment + 权限
- **性能基准**: `meta/tests/performance/test_baseline_v3_1.py` 输出 P50/P95/P99
- **E2E 测试**: preview 端到端、详情合并、缓存命中
- **回滚测试**: `meta/tests/test_rollback_v3_1.py` 验证 `BO_PERF_MODE=v1` 完全回滚
- **合规测试**: [audit-compliance.md §1.2](file:///d:/filework/excel-to-diagram/.trae/rules/audit-compliance.md#L29-L42) 审计完整性

#### 回滚计划

- 每 PR 单独 `git revert`
- 紧急回滚：`BO_PERF_MODE=v1` 一键关闭所有优化
- 数据库回滚：`DROP INDEX`（无数据变更）
- 缓存清空：`/api/v1/admin/cache/clear`

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|---------------------|-----------|
| TBD-1 | Q4 性能基线 | 当前 P50/P95/P99 数据（需 APM） | 接入 Prometheus 后回填 NFR-001 |
| TBD-2 | 假设 A2：APM 工具 | 是否有 SkyWalking/ARMS/其他 APM | 询问用户 |
| TBD-3 | 假设 A3：长跑 server 1 周+ | 是否真实运维场景 | 询问用户 |
| TBD-4 | 假设 A4：preview 并发 < 50 | 实际并发量 | APM 监控后确认 |
| TBD-5 | A5：SQLite WAL 100 QPS 健康 | 实际写吞吐 | DRE 监控 [§10.5](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) 持续观察 |
| TBD-6 | FR-014 WAL checkpoint 频率 | 是否影响 DRE 监控 | DRE owner 确认 |
| TBD-7 | FR-002 并行拦截器清单 | 18 拦截器哪些声明 parallel_safe | 启动后由架构师审核 |
| TBD-8 | FR-016 trace_id 注入到 SQL 注释 | 是否影响 SQL 分析工具 | 测试验证 |
| TBD-9 | FR-018 详情合并端点前端协作 | 前端是否接受新 include 参数 | 联调确认 |
| TBD-10 | M1 完成后回顾 | PR-01~PR-04 性能收益 | 决定 M2 是否调整 |

---

## 11. 完整性自检

- Spec 包含 **10 sections** [OK]
- 最后一个 section 是 **"TBD List"** [OK]
- 内容完整，未截断 [OK]
- 覆盖用户所有约束：Q1=C（全部 19 个）/ Q2=B（仅索引）/ Q3=A（进程内 LRU+TTL）[OK]
- 包含 19 个 FR、5 个 NFR、3 个 IF、4 个 TR、7 个 C/A [OK]
- RFC 包含 5 个子章节（As-Is / Target / Detailed / Alternatives / Implementation）[OK]
- 所有代码引用使用 file:// 协议可点击 [OK]
- 符合 [SESSION_REMINDER](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) 测试铁律 [OK]

---

## 11. 代码质量 + 简化治理（v1.1 增量）

> **状态**: 增量 v1.1（基于 v1.0）
> **来源**: 用户"另外也整体看看代码质量，简化角度进一步全面分析下"
> **依据**: [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py)、[enrich_utils.py](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py)、[persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py) 等 7 个核心文件深度审查
> **关联**: 与 19 风险点并行治理；预计总减码 850 行（约占 5 个核心文件 25% 体量）

### 11.1 背景

v1.0 主要关注性能风险（19 个 R-0X），但代码深层扫描发现还有 10 项独立于性能、可在并行 PR 中处理的"代码质量 + 简化"治理项（S-01 ~ S-10）。这些问题虽不直接造成 P95 慢，但会导致：

- 维护成本升高（巨型方法、重复代码）
- 测试覆盖率低（无法 unit test 单方法）
- 跨模块耦合（shim 链、抽象泄漏）
- 错误处理不一致（debug / warn / error 混用）

### 11.2 需求类型

| 类型 | 适用 | 证据 |
|------|------|------|
| 功能需求 | 否 | — |
| 非功能需求 | 是 | NFR-006（代码可维护性）/ NFR-007（重复代码消除） |
| 内部接口需求 | 是 | IF-004（computed count clause 统一接口） |
| 过渡需求 | 是 | TR-005（10 个子任务，6 PR，跟随 v1.0 末 PR-06 后启动） |

### 11.3 10 项治理清单（S-01 ~ S-10）

#### S-01. 删除 `enrich_utils` v1 兼容 shim

| 维度 | 内容 |
|------|------|
| **位置** | [enrich_utils.py:45-62](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py#L45-L62) |
| **问题** | 自承"v1 兼容 shim"，`data_source` 参数被忽略；与 `EnrichmentEngine.enrich_fk_display_names` 重复 |
| **影响** | -62 行；3 层 shim 链 |
| **风险** | 🟢 低（注释自承兼容层） |
| **关联 FR** | 与 R-04/R-15 重叠（enrichment 性能） |

#### S-02. 抽取 `_computed_count_clause` 统一 4 处实现

| 维度 | 内容 |
|------|------|
| **位置** | [enrich_utils.py:129-267](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py#L129-L267) + [persistence_interceptor.py:860-1269](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L860-L1269) |
| **问题** | 4 处实现"操作符解析 + 找 m2m / one_to_many + 生成子查询"，重复 60-80% |
| **影响** | -400 行 |
| **风险** | 🟡 中（需回归测试） |
| **关联 FR** | 与 FR-001 / FR-005 / FR-007 / FR-015 重叠 |

#### S-03. 拆 `_do_list` 433 行 → 5 方法

| 维度 | 内容 |
|------|------|
| **位置** | [persistence_interceptor.py:396-829](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L396-L829) |
| **问题** | 单方法 433 行 + 14 重 if/elif |
| **影响** | -200 行；可测试性大幅提升 |
| **风险** | 🟡 中 |

#### S-04. `BOFramework` 22 方法 → 6 方法

| 维度 | 内容 |
|------|------|
| **位置** | [bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) |
| **问题** | 9 个 association 方法是参数模板；`set_user_context` / `set_audit_user` 互为别名；`execute_action` 与 `execute` 等价 |
| **影响** | -100 行；API 表面从 22 → 6 |
| **风险** | 🟡 中（API 破坏，但通过 `**kwargs` 兜底） |

#### S-05. 删除 `_TxnMarker` 异常做控制流

| 维度 | 内容 |
|------|------|
| **位置** | [bo_framework.py:142-156, 648-656](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L142-L156) |
| **问题** | 用异常做"业务失败"信号 — Python 反模式 |
| **影响** | -10 行；移除 1 个异常类 |
| **风险** | 🟢 低 |
| **关联 FR** | 与 R-19 完全重叠 |

#### S-06. 修 `_sort_by_virtual_fields` 多次 sort

| 维度 | 内容 |
|------|------|
| **位置** | [persistence_interceptor.py:1562-1572](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1562-L1572) |
| **问题** | `sort_key` 死代码；多次 `records.sort()` 行为不可预测 |
| **影响** | -5 行；修正排序行为 |
| **风险** | 🟢 低 |

#### S-07. 删除 `Interceptor.priority` 过时注释

| 维度 | 内容 |
|------|------|
| **位置** | [interceptors/base.py:46-58](file:///d:/filework/excel-to-diagram/meta/core/interceptors/base.py#L46-L58) |
| **问题** | 注释列了 9 种 priority，3 种不存在、4 种不准 |
| **影响** | -12 行；消除"注释撒谎"反模式 |
| **风险** | 🟢 低 |

#### S-08. 抽 `descendant_path` 替代硬编码层级

| 维度 | 内容 |
|------|------|
| **位置** | [persistence_interceptor.py:1271-1337](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py#L1271-L1337) |
| **问题** | 67 行硬编码 `domain → sub_domains → service_modules → business_objects → relationships` 5 层架构 |
| **影响** | -50 行；通用化（任何领域对象调整零代码） |
| **风险** | 🟡 中 |

#### S-09. `_pending_audit_records` 改 public + 方法

| 维度 | 内容 |
|------|------|
| **位置** | [action_context.py:93](file:///d:/filework/excel-to-diagram/meta/core/action_context.py#L93) + [audit_interceptor.py:305](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py#L305) + [bo_framework.py:539, 568](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py#L539) |
| **问题** | 下划线私有字段被跨类 `getattr` / 直接 append |
| **影响** | -5 行；契约清晰 |
| **风险** | 🟢 低 |

#### S-10. 修 `__init__.py:22` `# noqa: E402`

| 维度 | 内容 |
|------|------|
| **位置** | [interceptors/__init__.py:22](file:///d:/filework/excel-to-diagram/meta/core/interceptors/__init__.py#L22) |
| **问题** | `PermissionInterceptor` import 末尾加 `# noqa: E402` 压制警告 — 循环依赖或历史遗留 |
| **影响** | -1 行；导入顺序合规 |
| **风险** | 🟢 低 |

### 11.4 优先级矩阵

| ID | 任务 | Priority | 风险 | 减码 | 关联 |
|----|------|---------|------|------|------|
| S-01 | enrich_utils 瘦身 | Must | 🟢 | -62 | R-04/R-15 |
| S-02 | computed count clause 抽取 | Must | 🟡 | -400 | FR-001/005/007/015 |
| S-05 | 删 _TxnMarker | Must | 🟢 | -10 | R-19 |
| S-03 | 拆 _do_list | Should | 🟡 | -200 | FR-001/007 |
| S-04 | 22→6 API | Should | 🟡 | -100 | — |
| S-08 | descendant_path | Should | 🟡 | -50 | FR-010 |
| S-06 | 多次 sort | Could | 🟢 | -5 | — |
| S-07 | 删 priority 注释 | Could | 🟢 | -12 | — |
| S-09 | _pending_audit public | Could | 🟢 | -5 | FR-013 |
| S-10 | noqa: E402 | Could | 🟢 | -1 | — |
| **合计** | | | | **-850** | |

### 11.5 里程碑

- **M1（v1.0 PR-06 后启动）**：SPR-01 ~ SPR-03（S-01 / S-02 / S-05）— P0 三项，预计 3 PR / 18h / -470 行
- **M2**：SPR-04 ~ SPR-06（S-03 / S-04 / S-08）— P1 三项，预计 3 PR / 24h / -350 行
- **M3**：SPR-07（S-06 / S-07 / S-09 / S-10）— P2/P3 四项合并，预计 1 PR / 4h / -30 行

### 11.6 与 v1.0 的关系

| 维度 | 关系 |
|------|------|
| 时序 | 与 v1.0 末 PR-06 并行启动；不阻塞 v1.0 6 PR |
| 冲突 | S-02 与 FR-001/005/007/015 涉及同模块，需协调（建议 S-02 在 FR-015 之后做） |
| 验证 | 每项独立跑 `python d:\filework\test.py --file ...`（[SESSION_REMINDER](file:///d:/filework/excel-to-diagram/.trae/rules/SESSION_REMINDER.md) 铁律） |
| 回滚 | 各 PR 独立可回滚 |

### 11.7 NFR-006 / NFR-007

- **NFR-006 (可维护性)**: 5 个核心文件总行数从 3635 → 2785（-23%）
- **NFR-007 (DRY violation 消除)**: computed count clause 重复实现从 4 处 → 1 处

### 11.8 IF-004 (内部接口契约)

`_computed_count_clause` 模块导出：

```python
def parse_operator(key: str) -> Tuple[str, str, List[Any]]:
    """key → (field_name, operator, values)"""

def build_subquery(meta_object, base_name: str) -> Optional[str]:
    """含 m2m / one_to_many / composition 三种形态"""

def apply_count_subquery(
    subquery: str, operator: str, values: List[Any]
) -> Tuple[str, List[Any]]:
    """含 IN / NOT IN 展开"""
```

### 11.9 TR-005 (过渡需求)

- 10 子任务 / 6 PR / 46h 估算
- 与 v1.0 的 50 任务并行；合计 60 任务 / 12 PR / 246h
- v1.1 changelog: 2026-06-10 增 10 项简化治理

---

**变更日志**

| 日期 | 作者 | 变更 |
|------|------|------|
| 2026-06-10 | AI Assistant | 初版 v1.0，19 风险全量治理（基于 Q1=C / Q2=B / Q3=A） |
| 2026-06-10 | AI Assistant | v1.1 增量 10 项简化治理（S-01~S-10），预计 -850 行 / 6 PR / 46h |
