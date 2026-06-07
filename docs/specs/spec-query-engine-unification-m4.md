# M4 Spec: v3 查询引擎 — 企业级读路径基线

> **版本**: v4.0.0（M4 阶段）
> **日期**: 2026-06-05
> **状态**: ✅ Completed
> **前置**: M1-M3 已完成；[spec-query-engine-gap-analysis-v3-vs-head.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-query-engine-gap-analysis-v3-vs-head.md) Gap 1-5
> **范围**: UnifiedQueryFacade / ListService / QueryBuilder / 测试

---

## 1. 目标

按 gap 分析采纳建议，M4 阶段完成 **5 个 P0/P1 任务**：

| ID | 任务 | 优先级 | 工作量 |
|----|------|:-----:|--------|
| **M4.1** | Cursor-based pagination（替代 offset） | P0 | 0.5d |
| **M4.2** | 日期函数（year/month/date_diff） | P0 | 1d |
| **M4.3** | QueryPlanCache（SQL 编译缓存） | P1 | 1d |
| **M4.4** | 修复隐性 bug：FieldValueProvider.postprocess 未调用 | 隐性 | 0.5d |
| **M4.5** | v1→v2 流量切换 feature flag | 灰度 | 0.5d |

---

## 2. 详细设计

### 2.1 M4.1 Cursor-based pagination

**问题**：offset=10000 时 SQL `OFFSET 10000` 全表扫，O(n) 性能。

**设计**：
- URL 参数：
  - `?cursor=eyJpZCI6MTAwfQ==`（base64 JSON `{id: 100}`）
  - `?page_size=20`（替代 pageSize）
- SearchRequest 新增：
  - `cursor: Optional[str] = None`
  - `cursor_field: str = 'id'`（默认按 id 升序）
  - `cursor_direction: Literal['after', 'before'] = 'after'`
- QueryBuilder 内部：
  - 若 `cursor` 存在 → 添加 `WHERE id > ?`（after）或 `< ?`（before）条件
  - `limit + 1` 多取一条判断 `has_next`
- 响应：保留 `total / page / page_size` 兼容，新增 `next_cursor / prev_cursor`

**协议层**（[unified_query_protocol.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py)）：

```python
class UnifiedQueryRequest(BaseModel):
    # ... 既有 ...
    cursor: Optional[str] = None
    cursor_field: str = 'id'
    cursor_direction: str = 'after'  # 'after' | 'before'
```

**SearchRequest**（[query_models.py](file:///d:/filework/excel-to-diagram/meta/services/query_models.py)）：

```python
@dataclass
class SearchRequest:
    # ... 既有 ...
    cursor: Optional[str] = None
    cursor_field: str = 'id'
    cursor_direction: str = 'after'
```

**QueryBuilder 新增**：

```python
def where_cursor(self, field: str, value: Any, direction: str = 'after') -> "QueryBuilder":
    """添加 cursor 条件：WHERE field > value (after) 或 < value (before)"""
    op = QueryOperator.GT if direction == 'after' else QueryOperator.LT
    self._spec.conditions.append(QueryCondition(
        field=self._get_db_column(field),
        operator=op,
        value=value,
    ))
    return self
```

**QueryService.search 集成**：

```python
# 在 _apply_meta_driven_filters 之后
if request.cursor:
    decoded = _decode_cursor(request.cursor)
    if decoded and request.cursor_field:
        builder.where_cursor(request.cursor_field, decoded[request.cursor_field], request.cursor_direction)
        builder.page(1, request.page_size + 1)  # 多取一条
        # data[0:-1] 为结果，最后一条判断 has_next
```

**Response 扩展**（[unified_query_protocol.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py)）：

```python
class UnifiedQueryResponse(BaseModel):
    # ... 既有 ...
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
```

**安全**：
- `cursor` 是 base64(JSON)，用 `is_safe_field` 校验 field 名
- 解析失败 → 抛 `QueryProtocolError`

**回退兼容**：
- 同时传 `page=2&cursor=X` → `cursor` 优先
- 只传 `page` → 走旧 offset 路径

---

### 2.2 M4.2 日期函数

**问题**：业务无法表达 `year(field) = 2024` / `date_diff('day', a, b) > 7`。

**设计**：
- 协议层（[unified_query_protocol.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_protocol.py)）：

```python
class FilterValue(BaseModel):
    # ... 既有 ...
    op: Literal[  # 扩展
        'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'not_in', 'like', 'ilike',
        'between', 'is_null', 'is_not_null',
        # [M4] 日期函数
        'func_year', 'func_month', 'func_day',
        'func_date_diff',
    ] = 'eq'
    func_arg: Optional[str] = None  # date_diff 的单位（'day'/'hour'）
    func_arg2: Optional[str] = None  # date_diff 的第二字段
```

- URL 参数形式：
  - `?updated_at__func_year=2024`
  - `?created_at__func_date_diff=2024-01-01&func_arg=day`（diff from now）

- 算子映射（[unified_query_facade.py](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py)）：

```python
# SQLite 不支持 YEAR()，用 strftime
SQLITE_FUNCS = {
    'func_year':  "CAST(strftime('%Y', {field}) AS INTEGER)",
    'func_month': "CAST(strftime('%m', {field}) AS INTEGER)",
    'func_day':   "CAST(strftime('%d', {field}) AS INTEGER)",
}

# date_diff(field1, field2) = julianday(field1) - julianday(field2)
def _build_func_date_diff(field, unit, value):
    unit_map = {
        'day': 86400,  # seconds
        'hour': 3600,
        'minute': 60,
    }
    seconds = unit_map.get(unit, 86400)
    return f"((julianday({field}) - julianday({value})) * 86400 / {seconds})"
```

- QueryBuilder 不需要改；通过 raw conditions 注入：

```python
# unified_query_facade.py _build_v3_search_request 新增分支
if base_op.startswith('func_'):
    raw_sql, raw_params = _build_func_condition(meta, base_field, base_op, fv)
    if raw_sql:
        exists_conditions.append(('__raw__', (raw_sql, raw_params)))
        continue
```

- 白名单（SQL 注入防御）：`func_year/month/day/date_diff` 是 hardcode，不接受用户输入函数名

---

### 2.3 M4.3 QueryPlanCache

**问题**：每次 query 重 build_sql、QueryService 重 apply_filters，重复开销。

**设计**：
- 新增 [meta/core/query_plan_cache.py](file:///d:/filework/excel-to-diagram/meta/core/query_plan_cache.py)：

```python
class QueryPlanCache:
    """SQL 编译缓存。

    键: (entity_type, filter_signature, ordering_signature)
    值: (where_clause_sql, params_tuple, has_cursor)
    """
    def __init__(self, max_size: int = 1024, ttl_seconds: int = 60):
        self._cache: OrderedDict = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple) -> Optional[Dict[str, Any]]:
        if key not in self._cache:
            self.misses += 1
            return None
        entry = self._cache[key]
        if time.time() - entry['ts'] > self.ttl:
            del self._cache[key]
            self.misses += 1
            return None
        self._cache.move_to_end(key)
        self.hits += 1
        return entry['plan']

    def put(self, key: tuple, plan: Dict[str, Any]) -> None:
        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[key] = {'plan': plan, 'ts': time.time()}
```

- 集成在 QueryBuilder.build_sql 之后：

```python
# QueryService 内部
def _build_where_clause_cached(self, builder, meta_obj, filter_params):
    cache_key = (
        meta_obj.id,
        _signature_filters(filter_params),
        _signature_ordering(request.order_by),
    )
    plan = self.plan_cache.get(cache_key)
    if plan:
        # 直接把缓存的 where 子句加到 builder（不重新解析 filter）
        builder.where_raw(plan['sql'], plan['params'])
    else:
        # 走原 apply 路径，结果回填 cache
        ...
```

**注意**：cursor / 关联子查询 / computed count 不缓存（动态性强）

**M4.3 简化版**：仅缓存 `_apply_meta_driven_filters` 解析出的 (conditions list) —— 不缓存 SQL 本身（避免 builder 内部状态被破坏）。

```python
# 简化版签名缓存
parsed_filters_cache: Dict[Tuple, List[QueryCondition]]
```

**验收**：
- 同一 query 调用 100 次，第 2 次起 hits+1
- 命中率 = hits / (hits + misses)
- 通过 test.py 验证

---

### 2.4 M4.4 修复隐性 bug

#### Bug A: FieldValueProvider.postprocess 未实际调用

**位置**：[unified_query_facade.py:144](file:///d:/filework/excel-to-diagram/meta/core/unified_query_facade.py)

**现状**：
```python
# facade.execute 已注册 providers
providers = self._get_provider_registry()
# 但 providers.run_postprocess(meta, result.data, self.ds)  # ← 已调用
```

**验证**：检查 facade.execute 现状，确认实际是否调用。

**问题**：
- ComputedCountFieldProvider / AuditVirtualFieldProvider / RedundancyVirtualFieldProvider / RuleChainFieldProvider 各自实现 `postprocess` 方法
- 如果 `run_postprocess` 在 facade 中未调用 → 4 个 provider 的逻辑全部失效

**修复**（如确未调用）：
```python
# facade.execute 中
if result.data:
    providers = self._get_provider_registry()
    # [M4 修复] 真正调用
    providers.run_postprocess(meta, result.data, self.ds)
```

**注意**：providers 是 v3 引擎外的"附加层"，调用前需要确认不会与 QueryService 内置的 `_compute_list_computed_fields` 重复执行。

#### Bug B: QueryProtocolError → HTTP 400 映射缺失

**位置**：[api 层 manage_api.py](file:///d:/filework/excel-to-diagram/meta/api/)

**现状**：
- `QueryProtocolError` 在 facade / list_service 抛出
- API 层可能以 500 处理

**修复**：在 API 层 catch → 返回 400

#### Bug C: enrich_utils shim 调用方认知不一致

**位置**：[enrich_utils.py](file:///d:/filework/excel-to-diagram/meta/core/enrich_utils.py)

**现状**：shim 函数委托 EnrichmentEngine，但**部分 v3 新代码可能仍调老函数**

**修复**：在 shim 顶部加 deprecation warning（不是移除）。

---

### 2.5 M4.5 v1→v2 流量切换 feature flag

**问题**：v2 路径（ListService / AssocQueryService）目前是新增，v1（_do_list / _query_*）未切流量。

**设计**：
- 在 [meta/core/feature_flags.py](file:///d:/filework/excel-to-diagram/meta/core/feature_flags.py) 添加：
  ```python
  # Query engine v2 routing
  USE_V2_QUERY_LIST = os.getenv('USE_V2_QUERY_LIST', 'false').lower() == 'true'
  USE_V2_QUERY_ASSOC = os.getenv('USE_V2_QUERY_ASSOC', 'false').lower() == 'true'
  ```
- 在 [persistence_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/persistence_interceptor.py) `_do_list` 顶部：
  ```python
  if feature_flags.USE_V2_QUERY_LIST:
      from meta.services.list_service import get_list_service
      result = get_list_service().list(self.object_type, params)
      return _adapt_to_old_response_format(result)
  # 原 v1 逻辑...
  ```
- 灰度策略：
  - 默认 false（v1）
  - 测试环境用 `export USE_V2_QUERY_LIST=true`
  - 通过 DRE 慢查询对比 v1/v2 性能
  - 灰度通过后改默认 true

**安全**：
- v1 路径完全保留，不删除
- v2 失败 → 降级到 v1

---

## 3. 实施步骤

| 步骤 | 内容 | 风险 | 回退 |
|------|------|------|------|
| **S1** | M4.1 cursor pagination（protocol + builder + service） | 中 | 字段 default=None，零侵入 |
| **S2** | M4.2 日期函数（protocol + facade） | 中 | 协议层加新 op，老 op 不动 |
| **S3** | M4.3 QueryPlanCache | 低 | 失败 → cache miss，兜底原路径 |
| **S4** | M4.4 修复隐性 bug | 低 | 增量修复，每 bug 独立 |
| **S5** | M4.5 feature flag | 低 | 默认 false，零影响 |
| **S6** | 跑 smoke test + test.py | — | — |

---

## 4. 验收

```python
# M4.1 cursor
r = svc.list('user_group', {'cursor': 'eyJpZCI6MTAwfQ==', 'page_size': 5})
assert r['next_cursor'] is None or isinstance(r['next_cursor'], str)

# M4.2 日期函数
r = svc.list('user_group', {'created_at__func_year__eq': 2024})
assert isinstance(r['items'], list)

# M4.3 cache
for _ in range(100):
    svc.list('user_group', {'name__like': 'admin'})
assert plan_cache.hits > 0

# M4.4 bug 修复
# 验证 FieldValueProvider.postprocess 实际被调用
# 验证 QueryProtocolError → 400

# M4.5 feature flag
os.environ['USE_V2_QUERY_LIST'] = 'true'
# 触发 _do_list → 走 v2
```

**零回归**：`test.py --status` 失败数 ≤ M3 末值（7）。

---

## 5. 不在 M4 范围

- 全文检索（FTS5）— M5
- 关联 expand / nested projection — M5
- Mutation 路径统一（UnifiedMutationFacade）— M5
- 行级权限形式化 — M6
- 事务 / UnitOfWork — M6
- Query allow-list — M6

---

**执行开始**：本 spec 写完即执行。
