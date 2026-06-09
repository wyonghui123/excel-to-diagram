## 目录

1. [1. 背景](#1-背景)
2. [2. M3 目标](#2-m3-目标)
3. [3. 详细设计](#3-详细设计)
4. [4. 实施步骤（顺序执行，闭环验证）](#4-实施步骤（顺序执行，闭环验证）)
5. [5. 验证脚本](#5-验证脚本)
6. [6. 不在 M3 范围](#6-不在-m3-范围)
7. [7. 风险清单](#7-风险清单)

---
# M3 Spec: Query Engine Unification v3 — 关联查询与 computed count 接入

> **版本**: v3.0.0（M3 阶段）
> **日期**: 2026-06-05
> **状态**: ✅ 已完成（Completed）
> **前置**: [spec-query-engine-unification-v2.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-unification-v2.md) — M1/M2 已完成
> **范围**: v3 QueryBuilder、UnifiedQueryFacade、ListService、AssocQueryService

---

## 1. 背景

M1（2026-06-05 完成）：新增 `unified_query_protocol.py` / `query_field_providers.py` / `unified_query_facade.py` / `ListService` / `AssocQueryService`，不动 v1 路径。
M2（2026-06-05 完成）：enrich_utils 改为 shim，委托 `EnrichmentEngine.enrich_fk_display_names` / `enrich_association_counts`；修 `order_by` 字段名；computed `*_count` 字段在 v2 路径中**暂跳过**。

**M2 遗留**（本 M3 解决）：
1. **`*_count` computed 字段过滤 / 排序未接入 v2 路径** — `UnifiedQueryFacade._build_v3_search_request` 中跳过这些条件，导致 `member_count__gte=1` 在 v2 路径中失效
2. **AssocQueryService 关联查询未走 EXISTS 子查询** — v2 路径返回全集，不做关联过滤
3. **v3 QueryBuilder 缺少子查询条件支持** — 无法表达 `WHERE t.id IN (SELECT ...)` / `WHERE EXISTS (SELECT ...)` 形态

---

## 2. M3 目标

| 目标 | 衡量指标 | 验收 |
|------|---------|------|
| **G3.1** 接入 `*_count` computed 字段过滤到 v2 路径 | `ListService.list('user_group', {'member_count__gte': 1})` 返回正确计数结果 | smoke test |
| **G3.2** 接入 `*_count` computed 字段排序到 v2 路径 | `ListService.list('user_group', {'_order_by': '-member_count'})` 按计数降序 | smoke test |
| **G3.3** AssocQueryService 支持 EXISTS 关联过滤 | `list_associated(src_id=1)` 仅返回与 src 关联的 target 记录 | smoke test |
| **G3.4** 零回归 | `test.py --status` failed 数 ≤ M2 末值（7 个预先存在 mock 失败） | regression |

---

## 3. 详细设计

### 3.1 QueryBuilder 扩展：子查询条件

**M3 新增**：
- `where_exists(subquery_sql, subquery_params)` — `WHERE EXISTS (...)` 形态
- `where_not_exists(...)` — `WHERE NOT EXISTS (...)`
- `where_in_subquery(field, subquery_sql, subquery_params)` — `WHERE field IN (...)` 形态

**API 签名**（追加到 [query_builder.py](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py)）：

```python
def where_exists(self, subquery_sql: str, subquery_params: List[Any] = None) -> "QueryBuilder":
    """添加 WHERE EXISTS (subquery) 条件"""
    condition = QueryCondition(
        field="__exists__",
        operator=QueryOperator.EXISTS,
        value=None,
        values=[],
        raw_sql=subquery_sql,         # 新增字段
        raw_params=subquery_params or [],
    )
    self._spec.conditions.append(condition)
    return self

def where_not_exists(self, subquery_sql: str, subquery_params: List[Any] = None) -> "QueryBuilder":
    """添加 WHERE NOT EXISTS (subquery) 条件"""
    condition = QueryCondition(
        field="__not_exists__",
        operator=QueryOperator.NOT_EXISTS,
        value=None,
        values=[],
        raw_sql=subquery_sql,
        raw_params=subquery_params or [],
    )
    self._spec.conditions.append(condition)
    return self

def where_in_subquery(self, field: str, subquery_sql: str, subquery_params: List[Any] = None) -> "QueryBuilder":
    """添加 WHERE field IN (subquery) 条件"""
    condition = QueryCondition(
        field=self._get_db_column(field),
        operator=QueryOperator.IN_SUBQUERY,
        value=None,
        values=[],
        raw_sql=subquery_sql,
        raw_params=subquery_params or [],
    )
    self._spec.conditions.append(condition)
    return self
```

**QueryCondition 扩展**（在 [query_models.py](file:///d:/filework/excel-to-diagram/meta/services/query_models.py)）：

```python
class QueryCondition(BaseModel):
    field: str
    operator: str
    value: Any = None
    values: List[Any] = Field(default_factory=list)
    combine_mode: str = 'and'
    raw_sql: Optional[str] = None     # 新增：子查询 SQL
    raw_params: List[Any] = Field(default_factory=list)  # 新增：子查询参数
```

**QueryOperator 扩展**（在 [query_models.py](file:///d:/filework/excel-to-diagram/meta/services/query_models.py)）：

```python
class QueryOperator(str, Enum):
    # ... 既有 ...
    EXISTS = "EXISTS"
    NOT_EXISTS = "NOT_EXISTS"
    IN_SUBQUERY = "IN_SUBQUERY"
```

**QueryBuilder.build_sql 修改**（在 [query_builder.py](file:///d:/filework/excel-to-diagram/meta/core/query_builder.py#L418-L490)）：

在 WHERE 子句渲染逻辑中，识别 `raw_sql != None` 的 condition：

```python
for cond in self._spec.conditions:
    if cond.raw_sql is not None:
        # 子查询条件
        if cond.operator == QueryOperator.EXISTS:
            where_clauses.append(f"EXISTS ({cond.raw_sql})")
        elif cond.operator == QueryOperator.NOT_EXISTS:
            where_clauses.append(f"NOT EXISTS ({cond.raw_sql})")
        elif cond.operator == QueryOperator.IN_SUBQUERY:
            where_clauses.append(f"{cond.field} IN ({cond.raw_sql})")
        params.extend(cond.raw_params)
        continue
    # ... 既有渲染逻辑 ...
```

### 3.2 UnifiedQueryFacade 接入 computed count

**修改** [_build_v3_search_request](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py#L188-L246)：

将现有的「跳过 computed count 字段」逻辑改为「**转换为 WHERE EXISTS 子查询**」：

```python
for field_name, fv in req.filters.items():
    base_field, op = _split_field_op(field_name)
    v3_op = _map_op_to_v3(op)

    # [M3] 检查是否是 computed *_count 字段
    meta = registry.get(req.entity_type)
    if base_field.endswith('_count') and meta is not None:
        try:
            f = meta.get_field(base_field)
            if f is not None and getattr(f, 'computed', False):
                # 转为子查询条件
                _append_count_subquery_condition(
                    conditions, meta, base_field, v3_op, fv, target_alias=''
                )
                continue
        except Exception:
            pass

    # 既有路径
    cond = QueryCondition(...)
    conditions.append(cond)
```

**辅助函数** `_append_count_subquery_condition`（在 [unified_query_facade.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py)）：

复用 [enrich_utils.build_computed_count_filter_clause](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py) 的逻辑，但产出 v3 condition 形式：

```python
def _append_count_subquery_condition(
    conditions: List[QueryCondition],
    meta_object,
    field_name: str,
    v3_op: str,
    fv: 'FilterValue',
    target_alias: str = '',
):
    """把 computed *_count 字段过滤条件转为子查询 condition。"""
    base_name = field_name[:-6]
    through, source_key = _find_m2m_assoc_for_count(meta_object, base_name)
    if not through or not source_key:
        logger.warning(f"[M3] No m2m association for {field_name!r}, skipping")
        return

    table_name = meta_object.table_name
    if target_alias:
        source_ref = f"{target_alias}.id"
    else:
        source_ref = f"{table_name}.id"

    subquery = (
        f"SELECT COUNT(*) FROM {through} "
        f"WHERE {source_key} = {source_ref}"
    )

    # 翻译算子
    op_map = {
        'eq': '=', 'neq': '!=', 'gt': '>', 'lt': '<',
        'gte': '>=', 'lte': '<=',
        'in': 'IN', 'notin': 'NOT IN', 'like': 'LIKE',
    }
    sql_op = op_map.get(v3_op, '=')

    if sql_op in ('IN', 'NOT IN'):
        if not fv.values:
            return
        placeholders = ', '.join(['?'] * len(fv.values))
        raw_sql = f"{subquery} {sql_op} ({placeholders})"
        raw_params = list(fv.values)
    else:
        raw_sql = f"{subquery} {sql_op} ?"
        raw_params = [fv.value]

    # [M3 2026-06-05] 直接构造 QueryCondition 配合 raw_sql
    conditions.append(QueryCondition(
        field='__computed_count__',
        operator='CUSTOM',  # 不使用 enum，让 build_sql 看 raw_sql 即可
        value=None,
        values=[],
        combine_mode='and',
        raw_sql=raw_sql,
        raw_params=raw_params,
    ))
```

**注**：build_sql 的子查询识别逻辑与 3.1 同步——只看 `raw_sql != None`，不依赖 operator enum。

### 3.3 UnifiedQueryFacade 接入 computed count 排序

**修改** [_build_v3_search_request](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py#L188-L246) 排序生成：

```python
sort_by, sort_order = _parse_ordering(req.ordering)
if not sort_by:
    sort_by = 'updated_at'
    sort_order = 'desc'

# [M3] 检查是否是 computed *_count 字段排序
is_computed_count_sort = False
meta = registry.get(req.entity_type)
if sort_by.endswith('_count') and meta is not None:
    try:
        f = meta.get_field(sort_by)
        if f is not None and getattr(f, 'computed', False):
            is_computed_count_sort = True
    except Exception:
        pass

if is_computed_count_sort:
    # 复用 enrich_utils.build_computed_count_order_clause
    from meta.core.enrich_utils import build_computed_count_order_clause
    table_name = meta.table_name
    order_by = build_computed_count_order_clause(meta, sort_by, sort_order == 'desc', target_alias='')
    if order_by is None:
        order_by = f"updated_at desc"
else:
    order_by = f"{sort_by} {sort_order}".strip()
```

**注**：`build_computed_count_order_clause` 已经产出完整排序子句（含 `DESC/ASC`），直接赋给 `order_by` 即可。

### 3.4 AssocQueryService 接入 EXISTS 关联过滤

**修改** [list_associated](file:///d:/filework/excel-to-diagram/meta/services/assoc_query_service.py)：

```python
def list_associated(
    self,
    object_type: str,
    target_entity: str,
    src_id: Any,
    through: str,
    source_key: str,
    target_key: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """查询目标实体的关联记录（many_to_many）— M3 支持 EXISTS 关联过滤。"""
    # 构造过滤条件：target.id IN (SELECT target_key FROM through WHERE source_key = src_id)
    # 或: EXISTS (SELECT 1 FROM through WHERE source_key = src_id AND target_key = target.id)
    try:
        req = UnifiedQueryRequest.from_url_args(target_entity, params or {})
    except ValueError as e:
        raise QueryProtocolError(...)

    # [M3] 通过 filter_params 注入关联条件（raw 形式）
    # 这里采用更简单的方式：在 req.filters 注入一个特殊键
    if src_id is not None and through and source_key and target_key:
        target_meta = registry.get(target_entity)
        if target_meta:
            target_table = getattr(target_meta, 'table_name', target_entity)
            assoc_subquery = (
                f"SELECT {target_key} FROM {through} WHERE {source_key} = ?"
            )
            # 通过 filter_params 或新增字段传入
            req.assoc_subqueries.append({
                'field': 'id',
                'subquery_sql': assoc_subquery,
                'subquery_params': [src_id],
            })

    try:
        resp = self.facade.execute(req)
    except Exception as e:
        ...
```

**UnifiedQueryRequest 新增字段**（在 [unified_query_protocol.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py)）：

```python
class UnifiedQueryRequest(BaseModel):
    # ... 既有字段 ...
    assoc_subqueries: List[Dict[str, Any]] = Field(default_factory=list)
    # 每项: {'field': 'id', 'subquery_sql': '...', 'subquery_params': [...]}
```

**UnifiedQueryFacade 处理**（在 [unified_query_facade.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py)）：

```python
# 在 _build_v3_search_request 中追加：
for assoc in req.assoc_subqueries:
    cond = QueryCondition(
        field=self._get_db_column(assoc['field']),
        operator='IN_SUBQUERY',   # 复用 v3 的 IN_SUBQUERY
        value=None,
        values=[],
        combine_mode='and',
        raw_sql=assoc['subquery_sql'],
        raw_params=list(assoc.get('subquery_params', [])),
    )
    conditions.append(cond)
```

### 3.5 DRE 可观测性

继续走 UnifiedQueryFacade 既有 `elapsed_ms` / `trace_id` 通道，无需新增。

### 3.6 安全与兼容性

- `*_count` computed 字段名（`__computed_count__`）不与任何物理列冲突
- 关联子查询参数走 `?` 占位符，禁止字符串拼接
- v1 路径完全不动（向后兼容）
- v2 路径失败 → 抛 `QueryProtocolError` → 由调用方降级到 v1

---

## 4. 实施步骤（顺序执行，闭环验证）

| 步骤 | 内容 | 风险 | 回退 |
|------|------|------|------|
| **M3.1** | QueryBuilder + QueryCondition + QueryOperator 扩展 | 低 | 删除新增方法 |
| **M3.2** | UnifiedQueryFacade 接入 count 过滤 / 排序 | 中 | 改回 M2 跳过逻辑 |
| **M3.3** | UnifiedQueryRequest 新增 `assoc_subqueries` | 低 | 字段加 default=list，零侵入 |
| **M3.4** | AssocQueryService 注入关联子查询 | 中 | 关闭 if 分支 |
| **M3.5** | 跑 test.py + 写 smoke test | — | — |

---

## 5. 验证脚本

```python
# M3 smoke test
from meta.services.list_service import get_list_service
from meta.services.assoc_query_service import get_assoc_query_service

svc = get_list_service()
asvc = get_assoc_query_service()

# G3.1: count 过滤
r = svc.list('user_group', {'member_count__gte': 1})
assert all(r['items'][i].get('member_count', 0) >= 1 for i in range(len(r['items'])))

# G3.2: count 排序
r = svc.list('user_group', {'_order_by': '-member_count', 'pageSize': 5})
counts = [it.get('member_count', 0) for it in r['items']]
assert counts == sorted(counts, reverse=True)

# G3.3: EXISTS 关联
r = asvc.list_associated(
    object_type='user_group', target_entity='user', src_id=1,
    through='user_group_members', source_key='user_group_id', target_key='user_id',
)
# r['items'] 应只包含 user_group_id=1 的 user 关联
```

---

## 6. 不在 M3 范围

- v1 路径 `persistence_interceptor._do_list` / `association_engine._query_*` 切换到 v2 路径 — M4 阶段
- 删除 enrich_utils.py 兼容性 shim — M4 阶段
- 前端 layer 业务逻辑下沉 — 单独 spec（spec-ui-business-logic-downflow.md）

---

## 7. 风险清单

| 风险 | 概率 | 影响 | 缓解 |
|------|:---:|:---:|------|
| QueryCondition pydantic model 改动破坏序列化 | 低 | 中 | 字段加 `Optional`，default 保持不变 |
| QueryBuilder 新增子查询 SQL 注入 | 低 | 高 | 强制 `?` 占位符 + 参数化 |
| v2 路径 v1 路径结果不一致 | 中 | 中 | smoke test 对比 v1/v2 结果 |
| 关联子查询性能差（IN 子查询返回大量行） | 中 | 低 | pagination 限制 N=20 + trace_id 监控 |

---

**实施开始**: 本 spec 写完即执行（用户授权"直接执行到完成为止"）。
