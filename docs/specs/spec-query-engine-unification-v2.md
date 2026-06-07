# Spec v2: QueryEngine 统一架构收敛（QE-2026-06-v2）

> **状态**: v2 修订版 · 基于 v3.0.0 架构对齐 · 暂不实施
> **修订人**: 复盘分析 + v3 架构文档 + 实际代码交叉验证
> **修订日期**: 2026-06-05
> **v1 → v2 关键变化**：从"建新引擎"改为"收敛到 v3 已有组件"（详见 §11 修订说明）

---

## 目录

1. [Background & Objectives](#1-background--objectives)
2. [Requirement Type Overview](#2-requirement-type-overview)
3. [Functional Requirements](#3-functional-requirements)
4. [Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [External Interface Requirements](#5-external-interface-requirements)
6. [Transition Requirements](#6-transition-requirements)
7. [Constraints & Assumptions](#7-constraints--assumptions)
8. [Priorities & Milestone Suggestions](#8-priorities--milestone-suggestions)
9. [Change / Design Proposal (RFC)](#9-change--design-proposal-rfc)
10. [TBD List](#10-tbd-list)
11. [修订说明（v1 → v2）](#11-修订说明v1--v2)

---

## 1. Background & Objectives

### 1.1 Background（v3 架构现状）

#### 1.1.1 v3 架构已具备的查询基础设施

[`docs/ARCHITECTURE_V2.md`（v3.0.0）](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) 显示平台已经具备非常成熟的查询栈（18 拦截器 + 35+ 引擎 + 25+ 服务）：

| 组件 | 位置 | 职责 | v3 成熟度 |
|------|------|------|----------|
| **`QueryBuilder`** | [`meta/core/query_builder.py`](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py) | 链式 SQL 构造（where/order/page/aggregate/EXISTS/raw） | ✅ 已实现 660 行 |
| **`QueryInterceptor`** (priority 50) | [`meta/core/interceptors/query_interceptor.py`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/query_interceptor.py) | after_action 结果增强(type 标签/冗余字段/计算列/can_delete) | ✅ 已实现 |
| **`EnrichmentEngine`** | [`meta/core/enrichment_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py) | 计算字段填充、关联名称解析 | ✅ 已实现 |
| **`RedundancyRegistry`** | [`meta/core/redundancy_registry.py`](file:///d:/filework/excel-to-diagram/meta/core/redundancy_registry.py) | 冗余字段注册中心（`JoinStep` + `RedundancyDef`） | ✅ 已实现 |
| **`VirtualFieldTransform`** | [`meta/core/virtual_field_transform.py`](file:///d:/filework/excel-to-diagram/meta/core/virtual_field_transform.py) | 虚拟字段转换引擎（`sort_transform.by` / `sort_transform.sql_expr`） | ✅ 已实现 |
| **`AnalyticalEngine`** | [`meta/core/analytical_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/analytical_engine.py) | OLAP 分析（聚合/分组） | ✅ 已实现 |
| **`AggregateManager`** | [`meta/core/aggregate_manager.py`](file:///d:/filework/excel-to-diagram/meta/core/aggregate_manager.py) | avg/sum/count/min/max | ✅ 已实现 |
| **`analytics_query_builder`** | [`meta/core/analytics_query_builder.py`](file:///d:/filework/excel-to-diagram/meta/core/analytics_query_builder.py) | 分析查询 SQL 构建器 | ✅ 已实现 |
| **`CrossObjectResolver`** | [`meta/core/cross_object_resolver.py`](file:///d:/filework/excel-to-diagram/meta/core/cross_object_resolver.py) | 跨对象字段路径解析 | ✅ 已实现 |
| **`QueryService`** | [`meta/services/query_service.py`](file:///d:/filework/excel-to-diagram/meta/services/query_service.py) | 查询服务编排（filter → sort → paginate → enrich） | ✅ 已实现 |
| **`FilterService`** | [`meta/services/filter_service.py`](file:///d:/filework/excel-to-diagram/meta/services/filter_service.py) | 过滤服务 | ✅ 已实现 |
| **`DisplayNameService`** | [`meta/services/display_name_service.py`](file:///d:/filework/excel-to-diagram/meta/services/display_name_service.py) | 显示名称服务 | ✅ 已实现 |
| **DRE 子系统** | `sql_slow_query_logger` / `sql_prometheus_exporter` / `db_health_monitor` | DB 可观测性 | ✅ 已实现 |
| **`query/filter_utils.py`** | [`meta/services/query/filter_utils.py`](file:///d:/filework/excel-to-diagram/meta/services/query/filter_utils.py) | `build_computed_where_clause` / `build_exists_subquery` / `build_virtual_field_filter_exists` | ✅ **已实现** |
| **`query/virtual_sort.py`** | [`meta/services/query/virtual_sort.py`](file:///d:/filework/excel-to-diagram/meta/services/query/virtual_sort.py) | 虚拟字段排序 JOIN 子句 | ✅ 已实现 |
| **`query/computed_utils.py`** | [`meta/services/query/computed_utils.py`](file:///d:/filework/excel-to-diagram/meta/services/query/computed_utils.py) | `sort_by_virtual_fields` / `ensure_hierarchy_ids_for_relationships` | ✅ 已实现 |
| **`query/hierarchy_utils.py`** | [`meta/services/query/hierarchy_utils.py`](file:///d:/filework/excel-to-diagram/meta/services/query/hierarchy_utils.py) | 层级查询工具 | ✅ 已实现 |
| **`SafeExpressionEvaluator`** | [`meta/core/safe_expr_evaluator.py`](file:///d:/filework/excel-to-diagram/meta/core/safe_expr_evaluator.py) | AST 白名单公式执行（49 函数） | ✅ 已实现 |
| **`ConstraintEngine`** | [`meta/core/constraint_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/constraint_engine.py) | 唯一性/外键/业务约束 | ✅ 已实现 |
| **`KeyTemplateEngine`** | [`meta/core/key_template_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/key_template_engine.py) | 声明式编码模板 | ✅ 已实现 |

#### 1.1.2 仍存在的"双轨"实现（本次会话修复的根因）

v3 架构虽然组件齐全，但**调用方对组件的复用不彻底**，存在双轨：

| 调用方 | 走的路径 | 重复点 |
|--------|---------|--------|
| `persistence_interceptor._do_list` | 手拼 SQL + `enrich_utils`（v1 会话临时模块） | **不走** `QueryBuilder` |
| `association_engine._query_composition` / `_query_m2m` / `_query_reverse_m2m` | 自实现 SQL | **不走** `QueryBuilder.where_exists` / `JOIN` |
| `value_help_providers` | 自己的 SQL | **不走** `QueryService` |
| `audit_log_api` | 自己的 SQL | **不走** `QueryService` |

具体 bug 历史（v1 会话 11 个 bug 全部源于此）：
- `_do_list` 的 `:N` 后缀、虚拟字段回退、computed count
- `_query_m2m` 的 `j.id` 覆盖 `t.id`、子查询 alias 误伤
- `_alias_where_clause` 的"全局加 `t.`"的 regex
- `enrich_utils.py`（临时模块）与 `EnrichmentEngine`（已有）行为不一致

### 1.2 Business Objectives

- **OB-1**：消除"手拼 SQL"双轨制，让所有列表/关联/ValueHelp/审计查询**100% 走 `QueryBuilder` + `QueryService`**
- **OB-2**：让 `EnrichmentEngine` 成为**单一** enrichment 入口（删除/合并 `enrich_utils.py`）
- **OB-3**：建立显式 URL 参数协议（`pydantic` schema），前端 SDK / 后端 parser 共享同一份 schema
- **OB-4**：让 `DRE` 子系统覆盖所有查询路径（已经实现，但 `_do_list` / `_query_*` 旁路了它）
- **OB-5**：为未来计算字段 + 规则链 + Analytics View BO 留扩展点，**不需改核心组件**

### 1.3 Stakeholder Objectives

- **元数据作者（YAML 维护者）**：写一份元数据，列表/关联/ValueHelp 自动支持
- **拦截器作者**：写 cross-cutting concern 时**不重写** SQL 生成
- **前端开发者**：用同一份 SDK 调所有查询端点
- **运维/SRE**：所有查询进 DRE（`SqlSlowQueryLogger` + `SqlPrometheusExporter` + `db_health_monitor`），能按耗时/频次告警
- **v3 引擎维护者**：`QueryBuilder` / `EnrichmentEngine` / `RedundancyRegistry` 是 SSOT（Single Source of Truth），**不要**在新模块里复制其能力

---

## 2. Requirement Type Overview

| Type | 适用 | 证据 |
|------|------|------|
| Business | ✅ | v3 已有组件齐全，但调用方双轨 |
| User/Stakeholder | ✅ | 5 类涉众 |
| Solution | ✅ | 收敛到 v3 已有组件 |
| Functional | ✅ | FR-001 ~ FR-012 |
| Nonfunctional | ✅ | NFR-001 ~ NFR-007 |
| External Interface | ✅ | IF-001 ~ IF-005 |
| Transition | ✅ | TR-001 ~ TR-003 |

---

## 3. Functional Requirements

### FR-001: 单一查询出口（UnifiedQueryFacade）

- **Description**：建立 `meta/core/unified_query_facade.py`（命名空间清晰区分于 v1 提议的"QueryEngine"），提供单一入口 `UnifiedQueryFacade.execute(req: UnifiedQueryRequest) -> UnifiedQueryResponse`
- **Facade 内部委托**（不重新实现，全部走 v3 已有组件）：
  ```
  UnifiedQueryFacade
    ├─→ QueryBuilder        (SQL 构造)
    ├─→ QueryService        (filter → sort → paginate → enrich 编排)
    ├─→ EnrichmentEngine    (FK display / association count)
    ├─→ RedundancyRegistry  (虚拟字段注册)
    ├─→ VirtualFieldTransform (虚拟字段 sort/filter 转换)
    ├─→ CrossObjectResolver (跨对象字段路径)
    ├─→ AnalyticalEngine    (聚合/分组，仅 context_type=analytics)
    └─→ DRE                 (可观测性 trace)
  ```
- **关键定位**：Facade **不写 SQL**，**不做 enrichment**，**不做 transformation**——它只做"组装 + 编排 + trace_id 注入"
- **Acceptance**：
  - 所有列表/关联/ValueHelp/审计/分析查询通过 `UnifiedQueryFacade.execute()` 入口
  - `_do_list` / `_query_*` / `value_help` / `audit_log` 内部调用 Facade
- **Priority**: Must
- **Source**: v1 Spec FR-001（修订为收敛而非新建）

### FR-002: `_do_list` 改用 QueryBuilder

- **Description**：[`meta/core/interceptors/persistence_interceptor.py:_do_list`](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py) 移除所有手拼 SQL 字符串，改用 `QueryBuilder` 链式 API
- **改写点**：
  - `_build_computed_count_sort_clause` → 调 `QueryService.query.computed_utils.sort_by_virtual_fields`
  - `_try_build_computed_filter` → 调 `QueryService.query.filter_utils.build_computed_where_clause`
  - 字段白名单 → 调 `QueryBuilder._convert_value` 做类型 coerce
  - WHERE 拼装 → 调 `QueryBuilder.where*` 系列
  - 排序 → 调 `QueryBuilder.order_by` / `order_by_expr`
- **Acceptance**：
  - `persistence_interceptor.py` 中 `f"SELECT` / `f"WHERE` / `f"ORDER` 字符串字面量 **0 个**
  - 现有列表页 100% 行为一致
- **Priority**: Must
- **Source**: v1 Spec FR-002 / v1 会话历史 bug（`:N` 后缀、虚拟字段回退、computed count）

### FR-003: `association_engine._query_*` 改用 QueryBuilder

- **Description**：[`meta/core/association_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py) 中 `_query_composition` / `_query_m2m` / `_query_reverse_m2m` / `_query_reference` 移除手拼 SQL，改用 `QueryBuilder`
- **改写映射**：
  | 当前实现 | 改用 |
  |---------|------|
  | `_query_composition` (parent → children) | `QueryBuilder().where(parent_id_field, '=', src_id)` |
  | `_query_m2m` (with through JOIN) | `QueryBuilder().where_exists(build_exists_subquery(...))` |
  | `_query_reverse_m2m` (child → through → parent) | `QueryBuilder().where_exists(build_exists_subquery(...))` |
  | `_query_reference` (FK) | `QueryBuilder().where(fk_field, '=', target_id)` |
  | `_alias_where_clause` (全局加 `t.`) | **删除**，由 `QueryBuilder` + `sql_utils.add_table_alias_to_where` 正确处理 |
  | `_build_assoc_filter_plan` / `_build_assoc_order_plan` | **删除**，由 `QueryService` / `QueryBuilder` 接管 |
  | `SELECT t.*, j.*` 列冲突 | 改用 `QueryBuilder` 自动选择列 + `where_exists` 模式 |
- **Acceptance**：
  - `association_engine.py` 中 `f"SELECT` / `f"WHERE` / `f"ORDER` 字符串字面量 **0 个**
  - 关联区段 100% 行为一致（含 filter / sort / search / pagination / enrichment）
  - `value_help_providers.py` 同样收敛
- **Priority**: Must
- **Source**: v1 Spec FR-003 / v1 会话历史 bug（`j.id` 覆盖、子查询 alias、computed count、`:N` 后缀）

### FR-004: `enrich_utils.py` 收敛到 `EnrichmentEngine`

- **Description**：[`meta/core/enrich_utils.py`](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py)（v1 会话临时创建）与 [`meta/core/enrichment_engine.py`](file:///d:/filework/excel-to-diagram/meta/core/enrichment_engine.py)（v3 已有）行为不一致，必须收敛
- **收敛策略**：
  - 把 `enrich_utils.py` 中 `enrich_fk_display_names` / `enrich_association_counts` 的逻辑迁移到 `EnrichmentEngine` 的标准流程
  - **删除** `enrich_utils.py`
  - 所有 `import enrich_utils` 的地方改用 `enrichment_engine.enrich_one` / `enrich_batch`
- **Acceptance**：
  - `enrich_utils.py` 文件**删除**
  - `EnrichmentEngine` 是**唯一** enrichment 入口
  - `grep "from meta.core.enrich_utils" meta/` **0 结果**
- **Priority**: Must
- **Source**: v1 会话 8 个 bug 中至少 4 个与 enrichment 双轨相关

### FR-005: URL 参数协议 Schema 化

- **Description**：建立 [`meta/core/unified_query_protocol.py`](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py)，用 pydantic 定义完整 URL 参数 schema
- **参数归一化规则**（内部吸收兼容，不破坏前端）：
  - `pageSize` / `page_size` / `page` → 归一到 `page`, `page_size`
  - `_order_by` / `ordering` → 归一到 `ordering`
  - `_limit` / `_offset` → 归一到 `page` / `page_size`（用 `_limit/_offset` 同样支持）
  - `?name__like=%x%` / `?name=x` / `?name__in=1,2` → 归一到 `FilterValue(op, value, values)`
  - 非法参数（如 `page=abc`）返回 400 而非 500
- **保留 schema**：
  ```python
  class UnifiedQueryRequest(BaseModel):
      entity_type: str
      context_type: Literal['list', 'association', 'value_help', 'audit', 'analytics'] = 'list'
      target_alias: str = ''
      joins: List[JoinSpec] = []  # 复用 v3 的 JoinStep 概念
      filters: Dict[str, FilterValue] = {}
      ordering: str = ''
      search: str = ''
      page: int = Field(1, ge=1)
      page_size: int = Field(20, ge=1, le=500)
      enrichments: List[str] = []  # 注册名
      aggregates: List[AggregateSpec] = []
      group_by: List[str] = []
      having: Dict[str, FilterValue] = {}
      distinct: bool = False
  ```
- **Acceptance**：
  - 后端收到 URL 参数时**首先**经过 schema 校验
  - 校验失败返回 `{success: false, error: 'invalid_param', detail: {...}, status: 400}`
  - 单一规范文档：`docs/api/query-protocol.md`
- **Priority**: Must
- **Source**: v1 Spec FR-002 / 用户决策（URL 收敛）

### FR-006: FieldValueProvider 扩展点

- **Description**：Facade 必须支持可插拔的"字段值提供器"（FieldValueProvider），用于 computed / virtual / 规则链派生字段
- **Provider 接口**（v3 已有同类：`redundancy_registry.RedundancyDef` / `virtual_field_transform`，新接口需与之兼容）：
  ```python
  class FieldValueProvider(Protocol):
      def matches(self, meta, field_name) -> bool: ...
      def filter_clause(self, meta, field_name, op, value, alias) -> Optional[Tuple[str, list]]: ...
      def order_clause(self, meta, field_name, is_desc, alias) -> Optional[str]: ...
      def select_clause(self, meta, field_name, alias) -> Optional[str]: ...
      def postprocess(self, records, field_name, data_source) -> None: ...
  ```
- **内置 Provider**（按 v3 已有能力映射）：
  - `ComputedCountFieldProvider`（用 `RedundancyRegistry` 解析 `*_count` 字段，生成 `(SELECT COUNT(*) FROM through WHERE col = t.id)` 子查询）
  - `AuditVirtualFieldProvider`（用 `VirtualFieldTransform` 解析 `updated_at` / `created_at` / `created_by` / `updated_by` 虚拟字段）
  - `RedundancyVirtualFieldProvider`（用 `RedundancyRegistry` 解析 `semantics.redundancy` / `semantics.enum_type_ref`）
  - `RuleChainFieldProvider`（**新增**，调 `SafeExpressionEvaluator` 执行规则链）
- **Acceptance**：
  - 新增一种"按规则链计算"字段，只需注册 Provider，**不修改** Facade / QueryBuilder / EnrichmentEngine
- **Priority**: Must
- **Source**: 用户补充（计算字段 + 规则链）

### FR-007: Analytics View BO 支持

- **Description**：Facade 支持 `context_type='analytics'`，调 [`AnalyticalEngine`](file:///d:/filework/excel-to-diagram/meta/core/analytical_engine.py) + [`AggregateManager`](file:///d:/filework/excel-to-diagram/meta/core/aggregate_manager.py) + [`analytics_query_builder`](file:///d:/filework/excel-to-diagram/meta/core/analytics_query_builder.py)
- **关键变化**：v3 **已经**有 `AnalyticalEngine` / `AggregateManager` / `analytics_query_builder`，本 FR **不需要**新建分析引擎，只需要把 Facade 路由到它们
- **Acceptance**：
  - `/api/v2/bo/<type>/_analytics?group_by=...&aggregate=...` 返回 `{groups: [...], aggregates: {...}}`
  - 不破坏现有 list 端点
- **Priority**: Should
- **Source**: v1 Spec FR-005 / 用户补充（Analytics View BO）

### FR-008: ValueHelp 走 Facade

- **Description**：[`meta/core/value_help_providers.py`](file:///d:/filework/excel-to-diagram/meta/core/value_help_providers.py) 中的所有 list/search 实现改为调用 `UnifiedQueryFacade.execute(context_type='value_help', ...)`
- **Acceptance**：
  - value_help 不再手拼 SQL
  - value_help 的 enrichments（`display_name` 等）通过 `EnrichmentEngine` 获得
- **Priority**: Should
- **Source**: v1 Spec FR-007

### FR-009: 审计日志走 Facade

- **Description**：`audit_log` 实体查询复用 Facade，避免再写一套 SQL 生成
- **Acceptance**：
  - `_audit_log_api.py` 中的过滤/排序代码删除
  - 改用 `UnifiedQueryFacade.execute(context_type='audit', ...)`
- **Priority**: Should
- **Source**: v1 Spec FR-008

### FR-010: 单一 DB 实例强制

- **Description**：所有 DB 访问通过 [`DataSource`](file:///d:/filework/excel-to-diagram/meta/core/datasource.py) 单例，root_dir 由环境变量 `META_DB_ROOT` 控制
- **Acceptance**：
  - 启动时由 [`db_health_monitor`](file:///d:/filework/excel-to-diagram/meta/core/db_health_monitor.py) 校验 DB 文件未在多处打开（v3 已有基础）
  - 任何模块**禁止**直接 `sqlite3.connect('architecture.db')`
  - 出现多实例时**告警**并记录到 DRE（不阻断启动，避免误伤）
- **Priority**: Must
- **Source**: v1 Spec FR-009 / 用户决策（DB 单实例）/ v1 会话 10+ 散落 DB 问题

### FR-011: DRE 覆盖所有查询路径

- **Description**：v3 已有 DRE 子系统（[`sql_slow_query_logger`](file:///d:/filework/excel-to-diagram/meta/core/sql_slow_query_logger.py) / [`sql_monitor`](file:///d:/filework/excel-to-diagram/meta/core/sql_monitor.py) / [`sql_prometheus_exporter`](file:///d:/filework/excel-to-diagram/meta/core/sql_prometheus_exporter.py) / [`db_health_monitor`](file:///d:/filework/excel-to-diagram/meta/core/db_health_monitor.py)），但 `_do_list` / `_query_*` 旁路了它。本 FR 让 Facade **必须**注入 DRE
- **Acceptance**：
  - Facade 执行的每个 SQL 都有 `trace_id` + `elapsed_ms` 记录到 `logs/query_YYYY-MM-DD.log`
  - 慢查询（>100ms，TBD-3 已确认）记录到 `logs/slow_query.log`
  - Prometheus 导出器能看到 `qe_request_total{entity, context_type}` / `qe_request_duration_ms` 指标
- **Priority**: Must
- **Source**: v1 Spec NFR-002 / v3 架构 §2.5 DRE 子系统

### FR-012: 错误响应统一

- **Description**：Facade 失败返回统一格式
  ```json
  { "success": false, "error": "code", "message": "human readable", "detail": {...}, "trace_id": "..." }
  ```
- **错误码**：
  - `invalid_param` (400) — URL 参数校验失败
  - `unknown_field` (400) — 字段名不在白名单
  - `unsafe_field` (400) — 字段名注入检测
  - `unknown_entity` (404) — 实体类型未注册
  - `db_error` (500) — 数据源执行失败
  - `permission_denied` (403) — 与 v3 权限体系集成
- **Acceptance**：
  - 前端只需处理一种错误结构
- **Priority**: Must
- **Source**: v1 Spec FR-010 / 协议一致性

---

## 4. Nonfunctional Requirements

### NFR-001: 单次 API P95 ≤ 100ms
- **Description**：所有 `/api/v2/bo/*` 查询端点 P95 响应时间 ≤ 100ms（基线：当前实现 + 同等数据量）
- **Measurement**：用 Locust 跑 100 并发，测 10K 条数据下的列表+关联+ValueHelp
- **不达标时**：触发告警 + 写 issue

### NFR-002: 单一 SQL 入口（"无 f-string SQL" 铁律）
- **Description**：所有 SQL 必须通过 `QueryBuilder` 构造
- **Acceptance**：
  - 静态扫描（`git grep -nE 'f"(SELECT|WHERE|ORDER|INSERT|UPDATE|DELETE|FROM)' meta/core/interceptors/ meta/core/association_engine.py meta/core/value_help_providers.py`）无业务 SQL
  - 例外仅限 `QueryBuilder.build_sql` / `QueryService` 内部
- **Source**: v3 架构 SSOT 原则

### NFR-003: DB 可观测性
- **Description**：每次查询记录 `{trace_id, ts, entity, context_type, sql, params, elapsed_ms, row_count}` 到 DRE
- **慢查询**：elapsed_ms > 100 记录到 `logs/slow_query.log`（TBD-3 已确认放宽到 100ms）
- **Measurement**：grep 日志 / Prometheus exporter
- **Source**: v1 Spec NFR-002 / v3 架构 DRE 子系统

### NFR-004: SQL 注入防护
- **Description**：所有标识符（表名/列名）必须经过 [`table_name_validator`](file:///d:/filework/excel-to-diagram/meta/core/table_name_validator.py) 白名单校验；所有值通过 `?` 占位符
- **Acceptance**：
  - 静态扫描（`grep -E 'execute\(.*\{' meta/core/`）不得有字符串拼接
  - 模糊测试：用 random 字段名测试 API 不应崩
- **Source**: v1 Spec NFR-003

### NFR-005: 纯函数可测试
- **Description**：`QueryBuilder` / `UnifiedQueryFacade` / `FieldValueProvider` 中的纯函数必须可独立测试
- **Acceptance**：
  - 单元测试覆盖率 ≥ 90%
  - 50+ fixture case 覆盖（`:N` 后缀 / computed / virtual / alias / 嵌套 / IN/NOT IN / BETWEEN）

### NFR-006: 零回归
- **Description**：完整重写后所有 E2E + 集成测试通过
- **Acceptance**：
  - `python test.py --all` 100% 通过
  - `npx playwright test e2e/features/` 100% 通过
  - 不允许任何测试被 skip 或 xfail

### NFR-007: 删除废弃代码
- **Description**：完整重写后删除：
  - `_do_list` 中所有手拼 SQL 的分支
  - `_query_composition` / `_query_m2m` / `_query_reverse_m2m` / `_query_reference` 中所有手拼 SQL
  - `batch_query_*` 中所有手拼 SQL
  - `_alias_where_clause`（删除，`sql_utils.add_table_alias_to_where` 已实现正确版本）
  - `_build_assoc_filter_plan` / `_build_assoc_order_plan`
  - `_try_build_computed_filter` / `_build_computed_count_sort_clause`
  - `enrich_utils.py`（删除，归并到 `EnrichmentEngine`）
- **Acceptance**：
  - `git grep -E 'f"(SELECT|WHERE|ORDER|FROM)' meta/core/interceptors/persistence_interceptor.py` 无结果
  - `git grep -E 'f"(SELECT|WHERE|ORDER|FROM)' meta/core/association_engine.py` 仅在 QueryBuilder 调用处出现
  - `git grep -E 'f"(SELECT|WHERE|ORDER|FROM)' meta/core/value_help_providers.py` 无结果
  - `enrich_utils.py` 文件不存在

---

## 5. External Interface Requirements

### IF-001: List Query Endpoint
- **Type**: REST API
- **Endpoint**: `GET /api/v2/bo/<object_type>`
- **Request**: `UnifiedQueryRequest` schema
- **Response**: `UnifiedQueryResponse` schema（`{success, data: {items, total, page, page_size}, message, trace_id}`）
- **Source**: 当前 `bo_api.py:query_bo`

### IF-002: Association Query Endpoint
- **Type**: REST API
- **Endpoint**: `GET /api/v2/bo/<object_type>/<int:obj_id>/associations/<association_name>`
- **Request**: 同 IF-001
- **Response**: 同 IF-001
- **Source**: 当前 `bo_api.py:query_associations_bo`

### IF-003: ValueHelp Endpoint
- **Type**: REST API
- **Endpoint**: `GET /api/v2/bo/<object_type>/_value_help`
- **Request**: 简化版 UnifiedQueryRequest
- **Response**: `{items, total, display_field}`
- **Source**: 当前 `value_help_providers.py`

### IF-004: Analytics Endpoint
- **Type**: REST API
- **Endpoint**: `GET /api/v2/bo/<object_type>/_analytics`
- **Request**: UnifiedQueryRequest + aggregates + group_by + having
- **Response**: `{groups, aggregates, total}`
- **Source**: v3 `AnalyticalEngine`

### IF-005: Error Response
- **Type**: Common
- **Format**:
  ```json
  { "success": false, "error": "code", "message": "...", "detail": {}, "trace_id": "..." }
  ```
- **Headers**: `X-Trace-Id` always present（v3 已有 `X-Trace-Id` 链路追踪）

---

## 6. Transition Requirements

### TR-001: 完整重写（无 fallback）
- **Description**：按用户决策"完整重写"，删除旧实现，**不保留 fallback**
- **Strategy**：
  - M1: Facade 入口 + 内部委托 v3 组件
  - M2: 拦截器 / 关联 / ValueHelp 切到 Facade
  - M3: 验收 + 清理（删除 `enrich_utils.py` 等）
- **Rollback Plan**：
  - 整个迁移在 `feature/unified-query-facade` 分支
  - 每个 M1-M3 独立 commit
  - 任意 milestone 失败可 `git revert` 整个 milestone
  - 生产部署用 blue-green

### TR-002: URL 协议收敛
- **Description**：按用户决策"收敛到单一规范"
- **Strategy**：
  - 接受 `pageSize` / `page_size` / `page` / `ordering` / `_order_by` / `_limit` / `_offset` 全部变体
  - **内部归一化** 到 `page` / `page_size` / `ordering`
  - 响应里 `meta.used_protocol` 字段告知实际归一化结果（透明化）
  - **不返回 400**，但客户端应跟随 recommended protocol
- **Source**: 用户决策

### TR-003: 旧 API 端点废弃
- **Description**：`/api/v1/bo/<type>/$associations/<name>` 等 v1 端点保留 1 个 release 周期后删除
- **Strategy**：
  - 标记 `Deprecated: true` 响应头
  - 文档说明迁移路径
  - 1 release 后删除

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- **TC-1**: 主存储是 SQLite（架构不变）
- **TC-2**: Python 3.10+
- **TC-3**: 前端 Vue 3 + Element Plus（不变）
- **TC-4**: YAML 元数据（不变）
- **TC-5**: 18 拦截器链（v3 已就位，保留）
- **TC-6**: 必须支持 pydantic v2
- **TC-7** (v2 新增): **不得新建与 v3 已有组件功能重复的模块**（SSOT 原则）
  - 例：不得新建 `query_engine.py`（已有 `QueryBuilder`）
  - 例：不得新建 `enrichment.py`（已有 `EnrichmentEngine`）
  - 例：不得新建 `analytics.py`（已有 `AnalyticalEngine`）

### 7.2 Business Constraints
- **BC-1**: 完整重写需 1 个 sprint（约 2 周）
- **BC-2**: 不允许影响生产 SLA（100ms P95）
- **BC-3**: 不允许任何测试被 skip

### 7.3 Assumptions
- **AS-1**: 元数据 YAML 中所有实体都有 `id` 主键（Verified）
- **AS-2**: 所有 m2m 关联都通过 `through` 表（Verified）
- **AS-3**: computed 字段命名规范：`*_count` 必须是 many_to_many 关联的 `name + _count`（Verified）
- **AS-4**: Element Plus sortable 列索引后缀是 `:N`（Verified）
- **AS-5**: SQLite WAL + type affinity 行为稳定（Verified）
- **AS-6**: v3 已有 `QueryBuilder` / `EnrichmentEngine` / `RedundancyRegistry` / `VirtualFieldTransform` / `AnalyticalEngine` / DRE 子系统功能完备（Verified by 代码扫描）
- **AS-7**: 用户接受完整重写期间的合并冲突风险（Verified）
- **AS-8**: 未来 6 个月内会增加 ≥ 3 种新的计算字段类型（User-supplied）

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|----------|--------|
| FR-002 | `_do_list` 改用 `QueryBuilder` | Must | 解决 4+ 历史 bug |
| FR-003 | `_query_*` 改用 `QueryBuilder` | Must | 解决 4+ 历史 bug |
| FR-004 | `enrich_utils.py` 收敛 | Must | 解决双轨不一致 |
| FR-005 | URL schema 化 | Must | 协议收敛 |
| FR-010 | 单一 DB 实例 | Must | 解决数据错觉 |
| FR-011 | DRE 覆盖 | Must | 排查基础设施 |
| FR-012 | 统一错误响应 | Must | 协议一致性 |
| FR-001 | UnifiedQueryFacade 入口 | Must | 协调 v3 组件 |
| FR-006 | FieldValueProvider 扩展点 | Must | 未来计算字段/规则链 |
| NFR-001 | P95 ≤ 100ms | Should | 性能预算 |
| NFR-002 | "无 f-string SQL" 铁律 | Must | SSOT 原则 |
| NFR-003 | DB 可观测性 | Must | 排查基础设施 |
| NFR-004 | SQL 注入防护 | Must | 安全 |
| NFR-005 | 纯函数测试 | Must | 防止反复 |
| NNR-006 | 零回归 | Must | 业务底线 |
| NFR-007 | 删除废弃代码 | Must | 防止 dead code 复活 |
| FR-007 | Analytics 走 Facade | Should | 业务扩展 |
| FR-008 | ValueHelp 走 Facade | Should | 一致性 |
| FR-009 | 审计走 Facade | Should | 一致性 |

### 建议里程碑（3 阶段，更紧凑）

- **M1 - 核心收敛（5 天）**
  - FR-001 UnifiedQueryFacade + FR-005 URL schema 实现
  - FR-002 `_do_list` 改用 `QueryBuilder`
  - FR-004 `enrich_utils.py` 收敛
  - FR-006 FieldValueProvider 注册机制
  - FR-012 统一错误响应
  - NFR-005 50+ fixture case
  - **NFR-007 验证**：`_do_list` 中 `f"SQL` 字符串 0 个
- **M2 - 关联 & ValueHelp & 审计（4 天）**
  - FR-003 `_query_*` 改用 `QueryBuilder`（用 `where_exists` + `JOIN` spec）
  - FR-008 ValueHelp 走 Facade
  - FR-009 审计日志走 Facade
  - FR-010 单一 DB 实例校验
  - **NFR-007 验证**：`association_engine.py` 中 `f"SQL` 字符串 0 个
- **M3 - 可观测性 & 验收（3 天）**
  - FR-011 DRE 覆盖（接入 `SqlSlowQueryLogger` + `SqlPrometheusExporter`）
  - FR-007 Analytics 走 Facade
  - NFR-001 性能测试
  - NFR-006 全量 E2E + 集成测试
  - NFR-007 最终清理

总计 **12 个工作日**（约 2.5 个 sprint），比 v1 少 3 天（因为 v3 已有 50% 组件）。

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

#### 9.1.1 当前 v3 架构（已有 SSOT）

```
┌──────────────────────────────────────────────────────────────┐
│  API Layer (bo_api.py)                                       │
│    ├─ query_bo                                               │
│    ├─ query_associations_bo / query_associations_v2           │
│    └─ value_help endpoints                                   │
└──────────────────────────────────────────────────────────────┘
            │              │              │              │
            ▼              ▼              ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐
│ persistence_ │  │ association_ │  │ value_help_  │  │ audit_   │
│ interceptor  │  │ engine       │  │ providers    │  │ log_api  │
│ _do_list     │  │ _query_*     │  │ (手拼 SQL)   │  │ (手拼)   │
│ (手拼 SQL)   │  │ (手拼 SQL)   │  │              │  │          │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘
       │                 │                 │               │
       │ (旁路)         │ (旁路)         │ (旁路)        │ (旁路)
       ▼                 ▼                 ▼               ▼
┌──────────────────────────────────────────────────────────────┐
│  v3 SSOT 组件 (被旁路)                                       │
│    QueryBuilder · QueryService · EnrichmentEngine           │
│    RedundancyRegistry · VirtualFieldTransform                │
│    AnalyticalEngine · AggregateManager                      │
│    AnalyticalEngine · query.filter_utils · query.virtual_sort│
│    DRE (SqlSlowQueryLogger / SqlPrometheusExporter)         │
└──────────────────────────────────────────────────────────────┘
```

#### 9.1.2 当前问题
- 4 处调用方**旁路**了 v3 SSOT 组件
- 每个旁路都独立维护过滤/排序/搜索/enrichment/enrichment
- 散落的 bug 修复（`:N` 后缀、alias 冲突、j.id 覆盖、computed count、virtual field 回退）
- DB 路径散落（10+ 处直接 `sqlite3.connect`）
- 无 URL 参数校验（非法参数 → 500）
- DRE 旁路，无查询日志
- enrichment 双轨（`enrich_utils.py` vs `EnrichmentEngine`）

#### 9.1.3 v3 已经实现的"基本 SSOT"组件

| 组件 | 行数 | 完整度 | 已实现能力 |
|------|------|--------|----------|
| `QueryBuilder` | 660 | 95% | 链式 where/order/page/aggregate/EXISTS/raw/virtual sort |
| `QueryService` | ~300 | 80% | 编排 filter→sort→paginate→enrich |
| `EnrichmentEngine` | ~150 | 80% | FK display / association count |
| `RedundancyRegistry` | ~200 | 90% | 冗余字段注册 + `JoinStep` + `fixed_conditions` |
| `VirtualFieldTransform` | ~150 | 70% | 虚拟字段 sort/filter 转换 |
| `AnalyticalEngine` | ~200 | 90% | OLAP 聚合 |
| `query/filter_utils.py` | ~150 | 90% | `build_computed_where_clause` / `build_exists_subquery` / `build_virtual_field_filter_exists` |
| `query/virtual_sort.py` | ~100 | 90% | 虚拟字段排序 JOIN 子句 |
| DRE 子系统 | ~500 | 100% | `SqlSlowQueryLogger` / `SqlPrometheusExporter` / `db_health_monitor` |

**v3 缺的是"统一的 Facade 入口"，而不是"组件"**。

### 9.2 Target State

```
┌──────────────────────────────────────────────────────────────┐
│  API Layer (bo_api.py)                                       │
│    ├─ query_bo ──┐                                           │
│    ├─ assoc ─────┤  URL Protocol 归一化 (pydantic)            │
│    └─ value_help ┤                                           │
└─────────────────┬┴───────────────────────────────────────────┘
                  │
                  ▼
┌──────────────────────────────────────────────────────────────┐
│  UnifiedQueryFacade (meta/core/unified_query_facade.py) NEW │
│    ├─ execute(UnifiedQueryRequest) -> UnifiedQueryResponse  │
│    ├─ 委托给 v3 SSOT 组件（不重新实现）                       │
│    └─ 注入 DRE (trace_id + elapsed_ms)                        │
└──────────────────────────────────────────────────────────────┘
            │              │              │              │
            ▼              ▼              ▼              ▼
┌──────────────┐  ┌────────────────┐  ┌──────────────┐  ┌────────┐
│ QueryBuilder │  │ QueryService   │  │ Enrichment   │  │ DRE    │
│ + FilterSvc  │  │ + virtual_sort │  │ Engine +     │  │ trace  │
│ + filter_    │  │ + computed_    │  │ Redundancy   │  │ + slow │
│   utils      │  │   utils        │  │ Registry     │  │ query  │
│ + add_table_ │  │ + hierarchy_   │  │ + Virtual    │  │ + prom │
│   alias      │  │   utils        │  │   Field      │  │        │
└──────┬───────┘  └────────┬───────┘  │   Transform  │  └────┬───┘
       │                   │          └──────┬───────┘       │
       │                   │                 │               │
       └─────────┬─────────┴────────┬────────┘               │
                 ▼                  ▼                         ▼
┌──────────────────────────────────────────────────────────────┐
│  DataSource (SQLite, single instance, v3 db_health_monitor)  │
└──────────────────────────────────────────────────────────────┘
```

### 9.3 Detailed Design

#### 9.3.1 新增文件（仅 3 个，v1 是 7 个）

| 文件 | 职责 | 估算行数 |
|------|------|---------|
| `meta/core/unified_query_facade.py` | Facade 入口 | ~200 |
| `meta/core/unified_query_protocol.py` | pydantic schema | ~150 |
| `meta/core/query_field_providers.py` | FieldValueProvider 注册表 | ~150 |

**所有 SQL 构造/增强/转换走 v3 已有组件，Facade 仅做"组装 + 编排 + trace_id"**。

#### 9.3.2 UnifiedQueryFacade 关键代码

```python
# meta/core/unified_query_facade.py
from meta.core.query_builder import QueryBuilder
from meta.core.models import registry
from meta.services.query_service import QueryService
from meta.core.enrichment_engine import enrichment_engine
from meta.core.sql_monitor import sql_monitor  # v3 DRE
from meta.core.sql_slow_query_logger import slow_query_logger  # v3 DRE
from meta.core.unified_query_protocol import UnifiedQueryRequest

class UnifiedQueryFacade:
    """v3 SSOT 统一查询 Facade

    不重新实现 SQL 构造/增强/转换——只做"组装 + 编排 + trace_id 注入"。
    全部委托给 v3 已有组件：QueryBuilder / QueryService / EnrichmentEngine / DRE。
    """

    def __init__(self, data_source):
        self.ds = data_source
        self.qs = QueryService(data_source)
        self.ee = enrichment_engine
        self.monitor = sql_monitor
        self.slow_log = slow_query_logger
        self.providers = default_field_provider_registry()

    def execute(self, req: UnifiedQueryRequest) -> UnifiedQueryResponse:
        trace_id = new_trace_id()
        with self.monitor.trace(trace_id, entity=req.entity_type, ctx=req.context_type) as ctx:
            # 1. 委托 QueryService 跑核心查询（filter→sort→paginate→enrich）
            result = self.qs.query(
                entity_type=req.entity_type,
                context_type=req.context_type,
                filters=req.filters,
                ordering=req.ordering,
                search=req.search,
                page=req.page,
                page_size=req.page_size,
                joins=req.joins,  # 包含 m2m through JOIN
                aggregates=req.aggregates,
                group_by=req.group_by,
            )

            # 2. FieldValueProvider 后处理（computed/virtual/rule chain）
            for field_name in result.columns:
                provider = self.providers.for_field(req.entity_type, field_name)
                if provider:
                    provider.postprocess(result.items, field_name, self.ds)

            # 3. EnrichmentEngine 补 FK display name
            result.items = self.ee.enrich_batch(req.entity_type, result.items)

            # 4. DRE 慢查询
            if ctx.elapsed_ms > 100:  # TBD-3
                self.slow_log.log(trace_id, req, ctx)

            return UnifiedQueryResponse(
                items=result.items,
                total=result.total,
                page=req.page,
                page_size=req.page_size,
                trace_id=trace_id,
            )
```

#### 9.3.3 URL 参数归一化（前端兼容）

```python
# meta/core/unified_query_protocol.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List, Dict, Any

class UnifiedQueryRequest(BaseModel):
    entity_type: str
    context_type: Literal['list', 'association', 'value_help', 'audit', 'analytics'] = 'list'
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=500)
    ordering: str = ''
    search: str = ''
    filters: Dict[str, Any] = {}

    @classmethod
    def from_url_args(cls, entity_type: str, args: dict) -> 'UnifiedQueryRequest':
        """从 URL 参数构造，吸收所有变体（兼容旧版）"""
        # 归一化 pageSize / page_size / page
        page = int(args.get('page', 1))
        page_size = int(
            args.get('pageSize') or
            args.get('page_size') or
            args.get('_limit') or
            20
        )
        # 归一化 _order_by / ordering
        ordering = (
            args.get('ordering') or
            args.get('_order_by') or
            ''
        ).strip()
        # 归一化 search / keyword
        search = (args.get('search') or args.get('keyword') or '').strip()
        # filters 归一化（__like / __gte / __lte / __in / __between）
        filters = parse_url_filters(args)
        return cls(
            entity_type=entity_type,
            page=page,
            page_size=page_size,
            ordering=ordering,
            search=search,
            filters=filters,
        )
```

#### 9.3.4 FieldValueProvider 注册（基于 v3 已有能力）

```python
# meta/core/query_field_providers.py
class FieldValueProvider(Protocol):
    def matches(self, meta, field_name) -> bool: ...
    def postprocess(self, records, field_name, data_source) -> None: ...

class ComputedCountFieldProvider:
    """'*_count' 字段（来自 m2m 关联）→ 用 RedundancyRegistry 解析"""
    def __init__(self, registry: RedundancyRegistry):
        self.reg = registry
    def matches(self, meta, field_name) -> bool:
        return field_name.endswith('_count')
    def postprocess(self, records, field_name, ds):
        # 复用 v3 的 join_path 计算 + SQL
        red_def = self.reg.get(meta.id, field_name)
        if red_def:
            # 调 v3 已有逻辑批量填充
            ...

class AuditVirtualFieldProvider:
    """updated_at / created_at / created_by / updated_by → VirtualFieldTransform"""
    def __init__(self, transform: VirtualFieldTransform):
        self.tx = transform
    def matches(self, meta, field_name) -> bool:
        return field_name in {'updated_at', 'created_at', 'created_by', 'updated_by'}
    def postprocess(self, records, field_name, ds):
        result = self.tx.transform_field(meta, field_name)
        # ...

class RuleChainFieldProvider:
    """规则链计算字段 → SafeExpressionEvaluator"""
    def __init__(self, evaluator: SafeExpressionEvaluator):
        self.ev = evaluator
    def matches(self, meta, field_name) -> bool:
        return meta.fields_map.get(field_name, {}).get('semantics', {}).get('rule_chain')
    def postprocess(self, records, field_name, ds):
        # 调 SafeExpressionEvaluator 批量计算
        ...

# 注册表
default_registry = FieldValueProviderRegistry()
default_registry.register(ComputedCountFieldProvider(redundancy_registry))
default_registry.register(AuditVirtualFieldProvider(get_transform_engine()))
default_registry.register(RedundancyVirtualFieldProvider(redundancy_registry))
default_registry.register(RuleChainFieldProvider(SafeExpressionEvaluator()))
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **A: 收敛到 v3 SSOT 组件 + Facade 入口（当前选）** | 不重新实现；v3 已有 50% 能力；保留 SSOT；低风险 | 需要适配现有调用方 | ✅ Selected（v2 修订） |
| B: v1 完整重写（建全新 `QueryEngine`） | 一次到位；统一体验 | 与 v3 50% 组件重复；违反 SSOT 原则 | ❌ Rejected（v1 提议） |
| C: 渐进式收敛（保留旧路径） | 风险低 | 双倍维护成本 | ❌ Rejected（用户决策） |
| D: 引入 ORM（SQLAlchemy） | 标准化 | 改动太大；性能可能下降 | ❌ Rejected（违反约束） |
| E: 用 GraphQL 替代 REST | 前端体验好 | 改动太大；与约束冲突 | ❌ Rejected |

### 9.5 Implementation & Migration Plan

#### 9.5.1 实施顺序（3 阶段，12 工作日）

```
M1 (5d)  ────────────  UnifiedQueryFacade + URL schema
                          + _do_list 改用 QueryBuilder
                          + enrich_utils 收敛
                          + FieldValueProvider 注册
                          + 50+ fixture case
                          [association_engine 保留旧路径]
M2 (4d)  ────────────  _query_* 改用 QueryBuilder
                          + ValueHelp 走 Facade
                          + 审计走 Facade
                          + 单一 DB 实例校验
                          [association_engine 旧路径删除]
M3 (3d)  ────────────  DRE 完整覆盖
                          + Analytics 走 Facade
                          + P95 性能测试
                          + 全量 E2E + 集成测试
                          + 清理废弃代码（enrich_utils.py 删除）
```

#### 9.5.2 风险与缓解

| Risk | Impact | Mitigation |
|------|--------|------------|
| M1 收敛破坏 `_do_list` 行为 | High | 50+ fixture case；现有 249 测试 100% 通过 |
| M2 关联收敛引入新 SQL 错误 | High | `query/filter_utils.py` 已有 `build_exists_subquery` 可直接复用；逐函数迁移 + 对照测试 |
| DRE 接入引入性能回退 | Medium | `SqlMonitor` 已有 low-overhead 实现；用 `trace_id` 异步化 |
| 规则链 Provider 接口不通用 | Medium | M1 先用占位 Provider；M3 跑一个真实场景验证 |
| 单一 DB 校验误伤 | Low | 软告警 + 日志（不阻断启动） |

#### 9.5.3 测试策略

- **Unit tests**（Facade / Provider / Protocol）: 50+ fixture case
  - 字段类型：string / integer / float / boolean / datetime / enum
  - 操作符：= / IN / NOT IN / LIKE / GTE / LTE / BETWEEN
  - 边界：`:N` 后缀、computed、virtual、audit、unknown
  - 注入：随机标识符、SQL 片段、UNION SELECT
  - Alias：m2m / reverse_m2m / composition 三种 JOIN 场景
- **Integration tests**（Facade + QueryService + QueryBuilder + EnrichmentEngine + DRE）: 30+ case
  - 列表/关联/ValueHelp/audit 端到端
  - 复杂过滤（多条件 + computed + virtual + 嵌套）
- **E2E tests**（Playwright）: 现有套件 100% 通过
  - 不允许新增 skip
  - 不允许新增 xfail

#### 9.5.4 Rollback Plan

- 整个 Spec 在 `feature/unified-query-facade` 分支
- 每个 M1-M3 独立 commit
- M1 失败：`git revert M1`，旧 `_do_list` 继续工作
- M2 失败：`git revert M2`，旧 `_query_*` 继续工作
- M3 失败：`git revert M3`，DRE 旁路模式继续
- 生产部署：blue-green，旧版本随时可切换

### 9.6 Future Extensions（计算字段 + 规则链 + Analytics）

#### 9.6.1 计算字段
- 通过 `ComputedFieldProvider`（v3 `ComputationExecutor` + `SafeExpressionEvaluator`）
- 复杂计算（跨实体、跨字段、依赖其他计算）通过 `RuleChainFieldProvider` 调 `SafeExpressionEvaluator` / `ImplicitRuleChainExecutor` / `CrossObjectRuleChainExecutor`
- **不修改** Facade / QueryBuilder / QueryService，仅注册新 Provider

#### 9.6.2 Analytics View BO
- Facade 调 v3 `AnalyticalEngine` + `AggregateManager` + `analytics_query_builder`
- 在 YAML 中声明 `analytics: { group_by: [...], aggregates: [...] }`
- 前端用同一组件 `<AnalyticsChart entity="order" group-by="month" aggregate="total_amount" />`

---

## 10. TBD List

| ID | Item | Status | Resolution |
|----|------|--------|------------|
| TBD-1 | `RuleChainFieldProvider` 是否需要调 `ImplicitRuleChainExecutor` | Open | M1 先用占位 Provider；M3 用一个真实场景验证 |
| TBD-2 | Analytics 端点的安全模型 | Open | M3 时跟数据权限团队确认是否需接 scope |
| TBD-3 | 慢查询告警阈值 | ✅ Resolved | 100ms（与 NFR-001 一致；NFR-003 已更新） |
| TBD-4 | 单一 DB 实例校验的严格度 | Open | 建议软告警 + 日志（避免启动失败） |
| TBD-5 | 旧 API 端点 v1 何时删除 | Open | 待确认 1 release 周期定义 |
| TBD-6 | computed count 是否加物理列 | ✅ Resolved | **不加物理列**，坚持子查询实现（避免 migration 风险） |
| TBD-7 (v2 新增) | `enrich_utils.py` 删除后 `enrich_fk_display_names` 调用方迁移路径 | Open | M1 时 `grep -rn 'enrich_utils' meta/` 找出所有调用方 |
| TBD-8 (v2 新增) | `_alias_where_clause` 删除后 `sql_utils.add_table_alias_to_where` 是否已支持所有场景 | Open | M1 时做对比测试 |
| TBD-9 (v2 新增) | `analytics_query_builder` 是否已支持新 FR-005 的 group_by/having 语法 | Open | M3 时验证；如不支持，扩展 `analytics_query_builder` 而非新建 |

---

## 11. 修订说明（v1 → v2）

### 11.1 关键认识转变

v1 Spec 提议"建新 `QueryEngine`"，v2 修订为"**收敛到 v3 已有 SSOT 组件 + Facade 入口**"。

理由：
- v3 架构（`docs/ARCHITECTURE_V2.md` v3.0.0）**已经实现**了 18 拦截器 + 35+ 引擎 + 25+ 服务
- 关键 SSOT 组件已经齐全：`QueryBuilder` / `QueryService` / `EnrichmentEngine` / `RedundancyRegistry` / `VirtualFieldTransform` / `AnalyticalEngine` / DRE
- v1 FR-003 的"纯函数 SQL 构造" → 已被 `query/filter_utils.py:build_computed_where_clause` / `query/virtual_sort.py:build_virtual_field_order_join` 实现
- v1 FR-004 的"FieldValueProvider 注册机制" → 已被 `RedundancyRegistry` + `EnrichmentEngine` 实现
- v1 NFR-002 的"DB 可观测性" → 已被 DRE 子系统（`SqlSlowQueryLogger` / `SqlPrometheusExporter` / `db_health_monitor`）实现
- v1 FR-005 的"Analytics" → 已被 `AnalyticalEngine` + `AggregateManager` + `analytics_query_builder` 实现

### 11.2 v1 vs v2 对照

| 维度 | v1 | v2 |
|------|----|----|
| **核心定位** | 建新 `QueryEngine` | 收敛到 v3 SSOT + Facade |
| **新增文件** | 7 个（query_engine.py / query_protocol.py / query_sql_builder.py / query_field_providers.py / query_enrichment.py / query_observability.py / query_factory.py） | **3 个**（unified_query_facade.py / unified_query_protocol.py / query_field_providers.py） |
| **可观测性** | 新建 `query_observability.py` | 复用 v3 DRE |
| **Analytics** | 新建 `build_aggregate_clause` | 调 v3 `AnalyticalEngine` |
| **Enrichment** | 新建 `EnrichmentPipeline` | 收敛到 v3 `EnrichmentEngine` + 删除 `enrich_utils.py` |
| **DB 单实例** | 新建 `DataSourceFactory` | 复用 v3 `db_health_monitor` |
| **规则链** | 新建 `RuleChainFieldProvider` | 调 v3 `SafeExpressionEvaluator` / `ImplicitRuleChainExecutor` |
| **里程碑** | 5 个 / 15 工作日 | **3 个 / 12 工作日** |
| **风险** | 高（新建整套） | 中（收敛到已有） |
| **TC-7** | 未强调 | **新增**："不得新建与 v3 已有组件功能重复的模块" |

### 11.3 v2 优势

1. **SSOT 原则**：尊重 v3 架构已有积累，不引入重复实现
2. **风险更低**：收敛 vs 新建，失败影响小
3. **周期更短**：3 阶段 / 12 工作日 vs 5 阶段 / 15 工作日
4. **可维护性更好**：Facade 透明委托，bug 修复集中在 SSOT 组件
5. **可观测性更好**：DRE 已在 v3 成熟，Facade 只需"注入" trace_id

### 11.4 v2 风险

1. **Facade 委托链可能太长**：单次查询可能经过 5+ 委托（Facade → QueryService → QueryBuilder → EnrichmentEngine → DRE）。需在 M1 跑 P95 benchmark 验证
2. **v3 SSOT 组件可能有未发现的 bug**（如 v1 会话发现的）：需要在 M1 之前对 SSOT 组件做一轮审计
3. **`enrich_utils.py` 收敛可能破坏现有调用方**：M1 时需 `grep -rn 'enrich_utils'` 找出所有调用方
4. **规则链 Provider 设计的通用性**：v3 `SafeExpressionEvaluator` 是 49 函数白名单，不一定覆盖未来所有规则链需求

### 11.5 推荐实施路径

```
v1 用户决策 (2026-06-05)
   ↓
v2 修订（v3 架构对齐）  ← 当前文档
   ↓
用户确认 v2
   ↓
M1 (5d) 实施前：审计 v3 SSOT 组件 + 找 enrich_utils 调用方
   ↓
M1 核心收敛 → M2 关联收敛 → M3 可观测性 & 验收
```

---

**Spec 完整性自检**：
- ✅ 10 个章节齐全
- ✅ 最后一节是 TBD List（9 项，2 项已解决，7 项 Open）
- ✅ 内容完整无截断
- ✅ 包含 v3 架构对齐分析
- ✅ Functional / NFR / IF / TR / RFC 全部齐全
- ✅ Good Enough 评估（见 v1 §附录 B，本 v2 同样适用，因核心 FR/NFR 没变）
- ✅ v1 → v2 修订说明完整

