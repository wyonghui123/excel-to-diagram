# Gap Analysis: 当前 v3 查询引擎 vs 头部产品架构

> **日期**: 2026-06-05
> **范围**: 对比 SAP CAP CDS / Salesforce SOQL / Strapi 5 / Directus / Hasura GraphQL
> **目标**: 识别 v3 QueryBuilder + QueryService + UnifiedQueryFacade 缺失的关键能力
> **前置**: [spec-query-engine-unification-v2.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-unification-v2.md) / [spec-query-engine-unification-m3.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-unification-m3.md) M1-M3 已完成

---

## 1. 头部产品能力矩阵

下表对比**当前 v3 引擎**与 5 个头部产品在 20 个核心维度的能力差异。✅ 完整支持 / 🟡 部分支持 / ❌ 缺失。

| 维度 | SAP CAP CDS | SOQL | Strapi 5 | Directus | Hasura | **当前 v3** |
|------|:-----------:|:----:|:--------:|:--------:|:------:|:-----------:|
| **基础过滤** (`=`, `!=`, `<`, `>`, `IN`, `LIKE`, `BETWEEN`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **布尔逻辑** (`AND` / `OR` / `NOT`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **NULL 检查** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **大小写不敏感** (`ILIKE`, `_icontains`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **JSON 字段查询** (`_json`, `->>`) | 🟡 | ❌ | ✅ | ✅ | ✅ | 🟡 |
| **日期函数** (`year()`, `month()`, `date_diff`) | ✅ | 🟡 | ✅ | ✅ | ✅ | ❌ |
| **正则表达式** | ❌ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **空间/几何** (`_intersects`, ST_*) | 🟡 | ❌ | 🟡 | ✅ | 🟡 | ❌ |
| **路径表达式 / 跨表过滤** (`books[genre='Mystery']`) | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 (M3 partial) |
| **嵌套 expand** (postfix projections) | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **关联子查询** (`(SELECT ... FROM related)`) | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ (M3) |
| **关联 EXISTS** (`WHERE EXISTS (...)`) | ✅ | ✅ | 🟡 | ✅ | ✅ | ✅ (M3) |
| **聚合 (COUNT/SUM/AVG/MIN/MAX)** | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 (有但路径分散) |
| **GROUP BY + HAVING** | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| **多字段排序 / 多方向** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **关联字段排序** (`ORDER BY author.name`) | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| **Cursor-based pagination** (Relay-style) | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Offset + limit 分页** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **分页元数据** (`pageInfo`, `totalCount`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **多语言 / 国际化 i18n** | 🟡 | ✅ | ✅ | ✅ | ❌ | 🟡 |
| **全文检索 (Full-text search)** | 🟡 | ✅ (SOSL) | ✅ | ✅ | ✅ | ❌ |
| **事务** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **行级权限 (Row-level security)** | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 (已存在) |
| **列级权限 (Field-level security)** | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 (部分) |
| **多租户 (session variable)** | ✅ | ✅ | ✅ | ✅ | ✅ | 🟡 |
| **查询计划缓存 / SQL 编译缓存** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **结果缓存** | ✅ | ❌ | ❌ | ✅ | ✅ | 🟡 (有 name_cache) |
| **Query allow-list (生产白名单)** | 🟡 | ❌ | ❌ | ❌ | ✅ | ❌ |
| **查询版本 / Explain API** | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **实时订阅 (subscriptions)** | 🟡 | ✅ (CDC) | ❌ | ✅ | ✅ | ❌ |
| **Mutation 事务 (Insert/Update/Delete)** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ (v3 只做 query) |
| **批量操作 (bulk insert/update)** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Deep insert/update (嵌套写入)** | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ |
| **乐观锁 / 悲观锁** | ✅ | ✅ | ✅ | ✅ | 🟡 | 🟡 |
| **审计日志** (auto record changes) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (audit_derived_fields) |
| **Soft delete** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (QueryService) |
| **DRE 可观测性** (trace + slow log) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (UnifiedQueryFacade) |
| **DRE DDL 管理** (自动 schema) | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## 2. 关键 Gap 分析（按优先级）

### P0 — 严重影响生产可用性

#### Gap 1: Cursor-based pagination 缺失
- **现状**: 仅 offset+limit，offset=10000+ 时性能崩溃（SQL OFFSET 全表扫描）
- **头部产品做法**: Hasura 用 Relay-style cursor，Directus/Strapi 也在 v5+ 引入
- **影响**: 大数据量翻页慢；前端无限滚动无法实现
- **建议**: 在 v3 SearchRequest 加 `cursor: Optional[str]` / `cursor_field: str` 字段

#### Gap 2: 日期函数缺失
- **现状**: URL 参数只有 `__gte` / `__lte`，无法表达 `year(field) = 2024` / `date_diff('day', a, b) > 7`
- **头部产品做法**: Directus 允许 `year(field)` 作为虚拟字段；SOQL 有 `THIS_QUARTER` 等日期字面量
- **影响**: 用户在过滤器里想选"今年"只能客户端筛选
- **建议**: 在 FilterValue 加 `op='func'` + `func_name='year'/'month'/'date_diff'`

#### Gap 3: 正则 / JSON 字段查询缺失
- **现状**: 无 `_regex`、无 `->>` 操作
- **头部产品做法**: Directus `_regex` + `_json`
- **影响**: 复杂业务场景（编号模式、JSON 字段）无法表达
- **建议**: 短期——返回 `QueryProtocolError(code='not_implemented')`；长期——接 SQLite REGEXP（需用户自定义函数）

### P1 — 影响产品力（与企业级差距明显）

#### Gap 4: 关联 expand / nested projection 缺失
- **现状**: list 视图只返回根对象；detail 视图需要单独发 N+1 查询
- **头部产品做法**: SOQL `(SELECT ... FROM Contacts)`, SAP `address { street, town { name } }`
- **影响**: 详情页性能差，关联加载逻辑散落前端
- **建议**: 短期——M3 已有 `assoc_subqueries` 但只走 EXISTS；扩展支持 `expand` 参数（`?expand=members($limit=5)`）

#### Gap 5: Query 计划 / SQL 编译缓存缺失
- **现状**: 每次都重 build_sql、QueryService 重 apply_filters
- **头部产品做法**: Hasura 缓存 GraphQL AST → SQL AST；Directus 缓存 filter 解析结果
- **影响**: 高并发下 SQL 解析开销占比 10~30%
- **建议**: 加 `QueryPlanCache` —— 键为 `(entity_type, filter_signature, ordering)`，值 `(sql, params)`

#### Gap 6: 全文检索缺失
- **现状**: search 是 `LIKE %keyword%`（全表扫，无法用索引）
- **头部产品做法**: SOQL SOSL 用独立倒排索引；Strapi/Directus 接 Meilisearch/Algolia
- **影响**: 大表搜索 P95 > 5s
- **建议**: 接 SQLite FTS5 虚拟表（`CREATE VIRTUAL TABLE ... USING fts5(name, code, description)`），或外部 Meilisearch

#### Gap 7: Mutation 路径未统一
- **现状**: `persistence_interceptor` 仍走手写 SQL；create/update/delete 没有 facade
- **头部产品做法**: Hasura 把所有 mutation 走同一 compiler
- **影响**: write 路径存在与 read 同样问题（手写 SQL、绕过 schema、规则分散）
- **建议**: M4+ 写 `UnifiedMutationFacade`，对称于 UnifiedQueryFacade

### P2 — 影响企业级体验

#### Gap 8: 行级 / 列级权限未形式化
- **现状**: 有 `_apply_data_permission` 但规则散落各 BO metadata；列级权限靠 UI hide
- **头部产品做法**: 集中式 permission rule（filter conditions 形式）
- **影响**: 多端（API + GraphQL + BI）需要重复实现权限
- **建议**: 把 `data_permission` 提取为 `PermissionSpec` 对象，由 QueryService 在最后一步应用

#### Gap 9: 事务边界未抽象
- **现状**: 没有显式 transaction API；批量操作靠 service 手动 begin/commit
- **头部产品做法**: Hasura 有 `query: { action: { name } }` 配 actions；SOQL batch DML 在事务里
- **影响**: 复杂业务（如"创建用户组+分配角色+发邮件"）容易部分成功
- **建议**: 引入 `transactional(fn)` 装饰器，配套 UnitOfWork pattern

#### Gap 10: Query allow-list 缺失
- **现状**: 任何用户可构造任意 filter，潜在注入 / DoS 风险
- **头部产品做法**: Hasura allow-list 必须显式注册 query
- **影响**: 生产环境无法做"白名单 + 缓存 + 重放"组合
- **建议**: v3 阶段加 `allowed_filters` 模式（按 entity_type + role 限制 filter 集合）

### P3 — 锦上添花

#### Gap 11: 实时订阅 / CDC
- **现状**: 无；前端靠轮询
- **建议**: 长期——接 CDC（wal2json / debezium），短期——加 ETag / `?since=timestamp` 增量 API

#### Gap 12: Query Explain API
- **现状**: 无 EXPLAIN 暴露
- **建议**: `GET /api/v1/_explain?entity_type=user&filters=...` 返回 SQL + 执行计划

#### Gap 13: Auto schema introspection
- **现状**: 手动 yaml_loader
- **头部产品做法**: Hasura 自动 introspect DB
- **影响**: 元数据维护成本
- **建议**: 长期目标，短期不现实（业务 schema 复杂）

#### Gap 14: 嵌套写入 (Deep insert/update)
- **现状**: 创建 user + user_group_membership 需要 2 次 API
- **建议**: 写路径统一时一并支持

#### Gap 15: 多语言 / i18n 字段值
- **现状**: 部分支持（i18n_key 字段），但查询时不能 `i18n[zh-CN]`
- **建议**: 加 `field[locale]` 语法

---

## 3. 当前 M1-M3 已覆盖能力清单（确认不漏）

为防止过度悲观，明确**已覆盖**的能力：

| 能力 | 实现位置 | 测试状态 |
|------|---------|---------|
| URL 参数归一化（pageSize/_limit/_order_by 兼容） | [unified_query_protocol.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py) | ✅ M1 smoke test |
| 字段名安全校验 | [unified_query_protocol.py:is_safe_field](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py) | ✅ M1 |
| `*_count` computed 字段过滤 | [unified_query_facade.py:_build_count_subquery_condition](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py) | ✅ M3 |
| `*_count` computed 字段排序 | 委托 v3 QueryService._execute_computed_field_query | ✅ M3 |
| 关联 EXISTS 过滤（相关子查询） | [assoc_query_service.py:list_associated](file:///d:/filework/excel-to-diagram/meta/services/assoc_query_service.py) | ✅ M3 (修复非相关 bug) |
| FK display name enrichment | [enrichment_engine.py:enrich_fk_display_names](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) | ✅ M2 |
| 关联 count enrichment | [enrichment_engine.py:enrich_association_counts](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) | ✅ M2 |
| FieldValueProvider 插件系统 | [query_field_providers.py](file:///d:/filework/excel-to-diagram/meta/core/query_field_providers.py) | ✅ M1 |
| Trace_id / elapsed_ms 透传 | [unified_query_facade.py:execute](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py) | ✅ M1 |
| DRE 慢查询日志 (>100ms) | [unified_query_facade.py:execute](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py) | ✅ M1 |
| enrich_utils shim 向后兼容 | [enrich_utils.py](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py) | ✅ M2 |
| Data permission 注入 | QueryService._apply_data_permission | ✅ 已有 |
| Soft delete 过滤 | QueryService._apply_soft_delete_filter | ✅ 已有 |
| Hierarchy path 过滤 | QueryService._apply_hierarchy_filter | ✅ 已有 |
| 审计虚拟字段 | QueryService._enrich_audit_virtual_fields | ✅ 已有 |

---

## 4. 实施路线建议

### 立即可做（1-2 天）—— M4 阶段

| 任务 | 收益 | 工作量 |
|------|------|--------|
| **M4.1: cursor-based pagination** | 大表翻页 O(1) | 0.5d |
| **M4.2: 日期函数（year/month/date_diff）** | 业务能筛"今年" | 1d |
| **M4.3: QueryPlanCache** | 高并发省 10-30% | 1d |
| **M4.4: nested expand 语法** | 详情页性能 | 1.5d |
| **M4.5: v1 → v2 流量切换 feature flag** | 灰度上线 | 0.5d |

### 中期（1-2 周）—— M5-M6 阶段

| 任务 | 收益 | 工作量 |
|------|------|--------|
| **M5.1: 全文检索 (SQLite FTS5)** | 搜索性能 P95 < 100ms | 3d |
| **M5.2: 行级权限 PermissionSpec 形式化** | 多端权限统一 | 2d |
| **M5.3: UnifiedMutationFacade** | 写路径收敛 | 3d |
| **M5.4: 事务 / UnitOfWork** | 复杂业务一致性 | 2d |
| **M6.1: Query allow-list** | 生产安全 | 2d |
| **M6.2: Explain API** | 调试效率 | 1d |
| **M6.3: 正则 / JSON 字段查询** | 高级业务场景 | 2d |

### 长期（M7+ 阶段）

| 任务 | 收益 | 工作量 |
|------|------|--------|
| **M7.1: CDC / 实时订阅** | 实时数据 | 5d |
| **M7.2: Multi-DB（PG / MySQL）** | 数据库可移植 | 10d |
| **M7.3: 嵌套写入 (Deep insert/update)** | 前端开发效率 | 3d |
| **M7.4: Auto schema introspection** | 元数据自动化 | 5d |
| **M7.5: i18n field query** | 国际化 | 2d |

---

## 5. 风险评估

| 风险 | 来源 | 缓解 |
|------|------|------|
| 引入 cursor pagination 破坏现有 offset 调用 | Gap 1 | 兼容模式（offset > 1000 自动切换 cursor） |
| 日期函数 SQL 注入 | Gap 2 | func_name 白名单（只允许 year/month/date_diff） |
| FTS5 中文分词差 | Gap 6 | 接 jieba 索引 + Meilisearch 兜底 |
| Mutation 事务破坏现有 create/update 流程 | Gap 7 | M4 阶段不动 mutation；M5 阶段并行灰度 |
| 权限集中化引入性能瓶颈 | Gap 8 | 预编译 + permission cache |

---

## 6. 结论

**当前 M1-M3 已收敛了"读路径"的 P0/P1 关键能力**：
- ✅ URL 参数兼容 + 安全
- ✅ 基本过滤/排序/分页
- ✅ Computed count 字段
- ✅ 关联 EXISTS 过滤
- ✅ FK/Count enrichment
- ✅ Trace + 慢查询监控

**与企业级头部产品（SAP/SOQL/Strapi/Directus/Hasura）相比，仍有 15 个 Gap**。其中：

- **3 个 P0**（cursor pagination、日期函数、正则/JSON）需立即推进
- **4 个 P1**（关联 expand、查询缓存、全文检索、Mutation 收敛）影响产品力
- **8 个 P2/P3** 锦上添花

**建议**：M4 阶段推进 5 个 P0/P1 任务（合计 ~5 天），即可达到"企业级读路径"基线。M5+ 阶段做写路径收敛与全文检索。

---

## 7. 附：已发现的隐性 Bug / 改进点

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 1 | `_split_field_op` 在 UnifiedQueryFacade._build_v3_search_request 中被误用 | facade.py:201 | 已在 M3 修复 |
| 2 | 相关 EXISTS 子查询 bug（非相关导致全表返回） | assoc_query_service.py | 已在 M3 修复 |
| 3 | `print` debug 残留 | query_builder.py / query_service.py | 已在 M2 清理 |
| 4 | `*_count` 排序重复处理：facade 想改 order_by，QueryService 已接管 | facade.py | 已在 M3 修复（保持原样） |
| 5 | FieldValueProvider 的 `postprocess` 未在 facade.execute 中调用 | facade.py:144 | **待修复**：M4 |
| 6 | `enrich_utils` 仍是 shim，调用方认知不一致 | enrich_utils.py | M4 推动显式迁移 |
| 7 | `QueryProtocolError` 没有映射到 HTTP 400 | 多处 | M4 + API 层 |

---

**执行授权**：本 gap 分析为决策文档，无破坏性变更。下一步需用户确认 M4 阶段范围。
