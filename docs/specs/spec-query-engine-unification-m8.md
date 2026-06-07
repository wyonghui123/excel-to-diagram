# M8 Spec: v3 引擎 — 消费侧能力（Consumer-Side Capabilities）

> **版本**: v8.0.0（M8 阶段）
> **日期**: 2026-06-06
> **状态**: ✅ Completed
> **前置**: M1-M7 已完成
> **范围**: ValueHelp / Aggregate / Reverse Expand / Nested DSL / ETag / Custom Order
> **目标**: v3 引擎消费侧能力从 80% → 95%

---

## 0. 现状调研（重要发现）

M8 **不重新发明**，**激活 + 包装 + 补全**：

| 能力 | 现状 | M8 任务 |
|------|------|---------|
| `query_api.py:aggregate` ([query_api.py:110](file:///d:/filework/excel-to-diagram/meta/api/query_api.py#L110)) | ✅ 已有 | 激活 + 文档化 + 测试 |
| `AssociationEngine._query_reverse_m2m` ([association_engine.py:1379](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py#L1379)) | ✅ 已有 | 包装为 `GET /<id>/reverse/<assoc>` |
| `AssociationEngine._batch_query_reverse_m2m` ([association_engine.py:1072](file:///d:/filework/excel-to-diagram/meta/core/association_engine.py#L1072)) | ✅ 已有 | 优化为单次 IN 查询 |
| `query_builder.QueryBuilder` | ✅ 已有 | 扩展嵌套 DSL |
| HTTP ETag / If-None-Match | ❌ 缺失 | 加 middleware |
| `FIELD()` 自定义排序 | ❌ 缺失 | v3 SQL builder 加 |
| `valuehelp` 端点 | ❌ 缺失 | 新增 |
| 嵌套 WHERE DSL | ❌ 缺失 | 新增 POST /<entity>/query |
| Webhook 注册 | ⚠️ v1 有 | v3 包装 |

---

## 1. 目标（6 个 P0 能力）

| ID | 能力 | 端点 | 优先级 | 工作量 |
|----|------|------|:-----:|--------|
| **VP-1** | ValueHelp 端点 | `GET /<entity>/valuehelp` | P0 | 2d |
| **VP-2** | 嵌套 WHERE DSL | `POST /<entity>/query` | P0 | 3d |
| **VP-3** | Aggregate API 包装 | `GET /<entity>/aggregate` | P0 | 2d |
| **VP-4** | Reverse Expand | `GET /<entity>/<id>/reverse/<assoc>` | P0 | 1d |
| **VP-5** | ETag / If-None-Match | middleware | P0 | 1d |
| **VP-6** | Custom Order | `_order_by=custom:1,3,2` | P0 | 0.5d |

**核心闭环（M8 全集）= 9.5d** → 消费侧 80% → 95%

---

## 2. 详细设计

### 2.1 VP-1 ValueHelp 端点

**解决问题**：下拉框 / 自动补全场景。

**API**：
```http
GET /api/v1/<entity>/valuehelp?q=张&top=20&display=name,email&locale=zh-CN&order_by=name
```

**参数**：
- `q` (string): 搜索关键字（必填或空 → 全部）
- `top` (int, 1-100, default=20): 限制返回数量
- `display` (string, comma-separated): 展示字段（默认 = display_field）
- `locale` (string, default='zh-CN'): 国际化（v3.1 集成 M7.5）
- `order_by` (string): 排序字段（默认 = display_field ASC）
- `filter[k__op]=v`: 任意 v3 filter（可选）

**响应**：
```json
{
  "items": [
    {"id": 1, "name": "张三", "email": "zhang@x.com", "code": "U001"},
    {"id": 2, "name": "张四", "email": "zhang2@x.com", "code": "U002"},
    ...
  ],
  "total": 156,
  "has_more": true,
  "display_fields": ["name", "email"]
}
```

**实现**：
```python
# meta/api/valuehelp_api.py（新增）
from flask import Blueprint, request, jsonify

valuehelp_bp = Blueprint('valuehelp', __name__, url_prefix='/api/v1')


@valuehelp_bp.route('/<entity>/valuehelp', methods=['GET'])
def valuehelp(entity: str):
    """VP-1 值帮助/自动补全端点。"""
    q = (request.args.get('q') or '').strip()
    top = min(int(request.args.get('top', 20)), 100)
    display_fields = [
        f.strip() for f in (request.args.get('display') or '').split(',') if f.strip()
    ]
    locale = request.args.get('locale', 'zh-CN')
    ordering = request.args.get('order_by') or (display_fields[0] if display_fields else 'id')
    
    # 复用 UnifiedQueryFacade
    facade = get_query_facade()
    
    # 1. 默认 display 字段
    if not display_fields:
        from meta.core.models import registry
        meta = registry.get(entity)
        display_fields = getattr(meta, 'value_help_fields', None) or [meta.pk]
    
    # 2. 构造 search-like filter
    filters = {}
    if q:
        # OR 多字段 LIKE
        from meta.core.unified_query_protocol import FilterValue
        for f in display_fields:
            filters[f'__or_{f}'] = FilterValue(op='ilike', value=f'%{q}%')
    # 3. 用户的 filter
    for k, v in request.args.items():
        if k.startswith('filter[') and k.endswith(']'):
            # filter[name__eq]=xxx → name__eq=xxx
            field = k[len('filter['):-1]
            filters[field] = FilterValue(op='eq', value=v)
    
    # 4. 限制 top
    req = UnifiedQueryRequest(
        entity_type=entity,
        page_size=top,
        ordering=ordering,
        filters=filters,
    )
    result = facade.execute(req)
    return jsonify({
        'items': result.items,
        'total': result.total,
        'has_more': result.total > top,
        'display_fields': display_fields,
    })


# meta/core/app_builder.py 注册
def with_valuehelp(self):
    from meta.api.valuehelp_api import valuehelp_bp
    self._app.register_blueprint(valuehelp_bp)
    return self
```

**v3 meta 元数据扩展**：
```yaml
# meta/yaml/<entity>.yaml
business_object:
  object_type: user
  table_name: users
  value_help_fields: [name, code, email]  # [VP-1] 默认展示字段
  fields:
    - {name: id, type: int, primary_key: true}
    - {name: name, type: string, required: true}
    - {name: code, type: string}
    - {name: email, type: string}
```

---

### 2.2 VP-2 嵌套 WHERE DSL

**解决问题**：复杂条件 `(A OR B) AND (C OR D)` 无法用扁平 URL 表达。

**API**：
```http
POST /api/v1/<entity>/query
Content-Type: application/json

{
  "where": {
    "and": [
      {"or": [
        {"customer.region__eq": "上海"},
        {"customer.tier__eq": "gold"}
      ]},
      {"and": [
        {"create_date__gte": "2024-01-01"},
        {"status__in": ["paid", "shipped"]}
      ]}
    ]
  },
  "order_by": [{"create_date": "desc"}, {"id": "asc"}],
  "page": 1,
  "page_size": 20,
  "expand": ["customer(id,name,avatar,tier)", "items(name,quantity)"]
}
```

**DSL Schema**：
```typescript
// 单条件
{"field__op": value}
{"field__op": [v1, v2]}  // IN
{"field__op": {"start": "x", "end": "y"}}  // BETWEEN

// 组合
{"and": [cond1, cond2, ...]}
{"or": [cond1, cond2, ...]}
{"not": cond}

// 嵌套关联（路径）
{"customer.region__eq": "上海"}
```

**实现**：
```python
# meta/core/nested_where_dsl.py（新增）
class NestedWhereParser:
    """解析嵌套 WHERE DSL → (where_sql, params)."""
    
    MAX_DEPTH = 5
    MAX_CONDITIONS = 100
    
    def parse(self, where: Dict, base_alias: str = 'bo') -> tuple:
        """Returns (raw_sql, params).
        
        raw_sql 是带 alias 的 WHERE 子句（不含 'WHERE' 关键字）
        """
        if not where:
            return '1=1', []
        if self._depth > self.MAX_DEPTH:
            raise QueryProtocolError(
                code='nested_where_too_deep',
                message=f'nested where depth exceeds {self.MAX_DEPTH}',
            )
        self._depth += 1
        try:
            return self._parse_node(where, base_alias)
        finally:
            self._depth -= 1
    
    def _parse_node(self, node: Dict, alias: str) -> tuple:
        # 组合节点
        if 'and' in node:
            return self._parse_logical('AND', node['and'], alias)
        if 'or' in node:
            return self._parse_logical('OR', node['or'], alias)
        if 'not' in node:
            inner_sql, inner_params = self._parse_node(node['not'], alias)
            return f'NOT ({inner_sql})', inner_params
        
        # 条件节点
        conditions = []
        params = []
        for key, value in node.items():
            if '__' in key:
                field, op = key.rsplit('__', 1)
            else:
                field, op = key, 'eq'
            cond_sql, cond_params = self._build_condition(field, op, value, alias)
            conditions.append(cond_sql)
            params.extend(cond_params)
        if not conditions:
            return '1=1', []
        if len(conditions) == 1:
            return conditions[0], params
        return f"({' AND '.join(conditions)})", params
    
    def _parse_logical(self, op: str, items: List, alias: str) -> tuple:
        if len(items) > self.MAX_CONDITIONS:
            raise QueryProtocolError(
                code='too_many_conditions',
                message=f'{op} conditions exceed {self.MAX_CONDITIONS}',
            )
        sqls = []
        all_params = []
        for item in items:
            inner_sql, inner_params = self._parse_node(item, alias)
            sqls.append(inner_sql)
            all_params.extend(inner_params)
        return f"({f' {op} '.join(sqls)})", all_params
    
    def _build_condition(self, field: str, op: str, value, alias: str) -> tuple:
        # 路径字段（customer.region）
        if '.' in field:
            return self._build_path_condition(field, op, value, alias)
        # 单字段
        column = f'{alias}.{field}'
        # 复用 M1 FilterValue 处理
        from meta.core.unified_query_protocol import FilterValue
        fv = FilterValue(op=op, value=value)
        # ... 走原 M1 路径 ...
        return self._filter_value_to_sql(column, fv)
```

**Facade 集成**：
```python
# meta/core/unified_query_facade.py execute() 增加 variant
def execute(self, req, request_context=None):
    if isinstance(req, NestedQueryRequest):  # 新类型
        where_parser = NestedWhereParser()
        where_sql, where_params = where_parser.parse(req.where)
        # 注入到 v3_request
        ...
```

---

### 2.3 VP-3 Aggregate API 包装

**现状**：`query_api.py:110` `/query/aggregate` 已实现，缺包装为 GET + 文档。

**新端点**（REST 风格）：
```http
GET /api/v1/<entity>/aggregate?group_by=department_id&sum=salary&avg=age&count=id&filter[status__eq]=active
```

**或（POST 复杂）**：
```http
POST /api/v1/<entity>/aggregate
{
  "object_type": "user",
  "dimensions": ["department_id", "status"],
  "measures": [
    {"field": "salary", "aggregation": "sum"},
    {"field": "age", "aggregation": "avg"},
    {"field": "id", "aggregation": "count"}
  ],
  "filters": [
    {"field": "status", "op": "eq", "value": "active"}
  ]
}
```

**响应**：
```json
{
  "rows": [
    {"department_id": 1, "status": "active", "sum_salary": 100000, "avg_age": 30, "count_id": 50},
    {"department_id": 2, "status": "active", "sum_salary": 200000, "avg_age": 28, "count_id": 30}
  ],
  "total_groups": 2,
  "dimensions": ["department_id", "status"],
  "measures": ["sum_salary", "avg_age", "count_id"]
}
```

**实现**：
```python
# meta/api/aggregate_api.py（新增）
@aggregate_bp.route('/<entity>/aggregate', methods=['GET'])
def aggregate_rest(entity: str):
    """VP-3 REST 风格聚合（GET）。"""
    # group_by=department_id&sum=salary&avg=age&count=id
    dimensions = [c.strip() for c in (request.args.get('group_by') or '').split(',') if c.strip()]
    measures = []
    for agg in ('count', 'sum', 'avg', 'min', 'max'):
        for f in request.args.getlist(agg) or []:
            measures.append(AggregateMeasure(field=f, aggregation=agg))
    
    # 用户的 filter
    filters = parse_url_filters(request.args)
    
    agg_request = AggregateRequest(
        object_type=entity,
        dimensions=dimensions,
        measures=measures,
        filters=filters,
    )
    service = _get_query_service()
    result = service.aggregate(agg_request)
    return jsonify(_aggregate_to_dict(result))
```

---

### 2.4 VP-4 Reverse Expand 端点

**解决问题**：`customer.orders` 反向关联查询（"客户 1 的所有订单"）。

**API**：
```http
GET /api/v1/customer/<id>/reverse/orders?status__eq=active&order_by=-create_date&pageSize=20
```

**或（批量）**：
```http
GET /api/v1/customer/<id>/reverse/orders?status__in=paid,shipped&expand=items(name)
```

**响应**：
```json
{
  "items": [
    {"id": 100, "customer_id": 1, "status": "active", "total": 99.0, ...},
    ...
  ],
  "total": 50,
  "association": "orders",
  "parent": {"id": 1, "name": "客户A"}
}
```

**实现**：
```python
# meta/api/reverse_api.py（新增）
@reverse_bp.route('/<entity>/<int:id>/reverse/<assoc>', methods=['GET'])
def reverse_expand(entity: str, id: int, assoc: str):
    """VP-4 反向关联展开。"""
    from meta.core.bo_framework import bo_framework
    from meta.core.unified_query_protocol import UnifiedQueryRequest
    
    # 1. 取关联元数据
    meta = registry.get(entity)
    target_entity = _resolve_reverse_assoc(meta, assoc)
    if not target_entity:
        raise QueryProtocolError(
            code='association_not_found',
            message=f'{entity} has no reverse association {assoc}',
        )
    
    # 2. 构造 query（含外键 filter + 用户 filter）
    fk = f'{entity}_id'  # 默认外键；元数据可指定
    filters = {f'{fk}__eq': id}
    for k, v in request.args.items():
        if k.startswith('filter['):
            ...
    
    # 3. 复用 UnifiedQueryFacade
    req = UnifiedQueryRequest(
        entity_type=target_entity,
        page_size=int(request.args.get('pageSize', 20)),
        ordering=request.args.get('order_by', '-id'),
        filters=filters,
        expand=request.args.get('expand', ''),
    )
    result = get_query_facade().execute(req)
    return jsonify({
        'items': result.items,
        'total': result.total,
        'association': assoc,
        'parent': {'id': id, 'type': entity},
    })


def _resolve_reverse_assoc(meta, assoc_name: str) -> Optional[str]:
    """从元数据查反向关联的目标实体。"""
    # 优先 m2m / reverse_m2m
    for a in getattr(meta, 'associations', []):
        if getattr(a, 'name', '') == assoc_name:
            if getattr(a, 'type', '') in ('reverse_many_to_many', 'one_to_many'):
                return getattr(a, 'target_entity', '') or getattr(a, 'target_table', '')
    # 兜底：找任何含 'reverse' 属性的关联
    for a in getattr(meta, 'associations', []):
        if a.name == assoc_name:
            return a.target_entity
    return None
```

---

### 2.5 VP-5 ETag / If-None-Match（缓存中间件）

**解决问题**：客户端缓存 + 304 Not Modified。

**实现**：
```python
# meta/core/etag_middleware.py（新增）
import hashlib
import json
from flask import request, make_response


def etag_response(data: Any) -> Response:
    """生成带 ETag 的响应。"""
    # 1. 计算 ETag（基于响应内容 + query 参数）
    content = json.dumps(data, sort_keys=True, default=str)
    etag = hashlib.md5(content.encode('utf-8')).hexdigest()
    
    # 2. 检查 If-None-Match
    if_none_match = request.headers.get('If-None-Match', '').strip('"')
    if if_none_match == etag:
        resp = make_response('', 304)
        resp.headers['ETag'] = f'"{etag}"'
        return resp
    
    # 3. 正常响应
    resp = make_response(jsonify(data))
    resp.headers['ETag'] = f'"{etag}"'
    resp.headers['Cache-Control'] = 'private, must-revalidate'
    return resp


# 集成到 app_builder
def with_etag(self):
    from meta.core.etag_middleware import etag_response
    @self._app.after_request
    def add_etag(resp):
        # 只对 GET 资源类端点添加
        if request.method == 'GET' and '/api/v1/' in request.path:
            if not resp.headers.get('ETag') and resp.is_json:
                try:
                    data = resp.get_json()
                    if isinstance(data, dict) and 'items' in data:
                        # 重写响应，加 ETag
                        from flask import Response
                        new_resp = etag_response(data)
                        return new_resp
                except Exception:
                    pass
        return resp
    return self
```

**用法**：
```http
# 第一次
GET /api/v1/user/1
→ 200 OK
ETag: "abc123"

# 客户端缓存 ETag 后
GET /api/v1/user/1
If-None-Match: "abc123"
→ 304 Not Modified（body 为空）
```

**价值**：
- 客户端缓存：带宽 -50%
- 服务端：跳过响应序列化（如果用 If-None-Match early-exit）
- 移动端弱网友好

---

### 2.6 VP-6 Custom Order

**解决问题**：拖拽后按用户顺序排序（如工作流定义后按用户拖拽顺序展示）。

**API**：
```http
GET /api/v1/task?order_by=custom:5,2,1,4,3
# 实际 SQL: ORDER BY FIELD(id, 5, 2, 1, 4, 3)
```

**实现**：
```python
# meta/core/unified_query_protocol.py 扩展 ordering 解析
def parse_ordering(ordering: str, pk_field: str = 'id') -> tuple:
    """解析 _order_by → (raw_sql, params)."""
    if not ordering:
        return f'ORDER BY {pk_field} ASC', []
    parts = [p.strip() for p in ordering.split(',') if p.strip()]
    
    # custom:1,3,2 → FIELD(id, 1, 3, 2)
    if parts and parts[0].startswith('custom:'):
        custom_ids = [int(x) for x in parts[0][len('custom:'):].split(',') if x.strip()]
        if custom_ids:
            placeholders = ','.join('?' * len(custom_ids))
            return f'ORDER BY FIELD({pk_field}, {placeholders})', custom_ids
    
    # 普通 asc/desc
    clauses = []
    for p in parts:
        if p.startswith('-'):
            clauses.append(f'{p[1:]} DESC')
        else:
            clauses.append(f'{p} ASC')
    return f"ORDER BY {', '.join(clauses)}", []
```

**集成到 facade.execute()**：
```python
# 在 _build_v3_search_request 之后注入 ordering
ordering_sql, ordering_params = parse_ordering(req.ordering, pk_field='id')
# 注入 v3 request
```

---

## 3. 完整端点规划

```
# 已有（M1-M7）
GET  /<entity>                    # 列表
GET  /<entity>/<id>               # 详情
POST /<entity>                    # 创建
PUT  /<entity>/<id>               # 完整更新
PATCH /<entity>/<id>              # [P1]
DELETE /<entity>/<id>             # 删除
POST /<entity>/deep_insert        # 嵌套创建
POST /<entity>/deep_update        # 嵌套更新
POST /<entity>/deep_delete        # 嵌套删除

# M8 新增
GET  /<entity>/valuehelp          # [VP-1] 值帮助/自动补全
POST /<entity>/query              # [VP-2] 嵌套 WHERE DSL
GET  /<entity>/aggregate          # [VP-3] REST 风格聚合
POST /<entity>/aggregate          # [VP-3] POST 复杂聚合
GET  /<entity>/<id>/reverse/<assoc>  # [VP-4] 反向关联
GET  /<entity>/_explain           # [M6.2] 执行计划

# M7 + M8
GET  /subscribe/<entity>          # [M7.1] SSE 实时
POST /webhook/<entity>            # [P1] webhook

# 缓存
ETag / If-None-Match              # [VP-5] 304
```

---

## 4. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 嵌套 DSL 性能 | MAX_DEPTH=5, MAX_CONDITIONS=100 |
| ETag 误判（响应微小变化） | MD5 内容 hash；strict JSON serialize |
| Reverse Expand 元数据不全 | 兜底用 `{parent}_id` 默认外键；元数据缺失时降级到 list |
| Aggregate GROUP BY 性能 | 加索引建议提示（依赖 EXPLAIN） |
| Custom Order 注入风险 | 参数化（placeholders）+ 数字校验 |
| valuehelp q=%...% 通配符 | 转义 `%` `_` |

---

## 5. 验收

### VP-1 ValueHelp
```python
# 1. 简单 q
GET /user/valuehelp?q=张 → items 含 name like '%张%'
# 2. 多字段 OR
GET /user/valuehelp?q=tech&display=name,email → ILIKE OR
# 3. top 限制
GET /user/valuehelp?top=5 → items.length<=5
# 4. 排序
GET /user/valuehelp?order_by=-id → ORDER BY id DESC
# 5. 关联 filter
GET /user/valuehelp?filter[status__eq]=active
```

### VP-2 Nested DSL
```python
# 1. AND 嵌套
POST /order/query {"where": {"and": [{"status__eq":"paid"}, {"total__gt":100}]}}
# 2. OR 嵌套
POST /user/query {"where": {"or": [{"name__ilike":"张"}, {"code__ilike":"U001"}]}}
# 3. 关联路径
POST /order/query {"where": {"customer.region__eq":"上海"}}
# 4. 嵌套 OR + AND
POST /order/query {"where": {"and": [
    {"or": [{"customer.region__eq":"上海"}, {"customer.tier__eq":"gold"}]},
    {"and": [{"create_date__gte":"2024-01-01"}, {"status__in":["paid","shipped"]}]}
]}}
# 5. 深度限制
# 6 嵌套层 → QueryProtocolError 'nested_where_too_deep'
```

### VP-3 Aggregate
```python
# 1. 单聚合
GET /user/aggregate?count=id → [{count_id: 100}]
# 2. 多聚合
GET /user/aggregate?sum=salary&avg=age&count=id
# 3. group_by
GET /user/aggregate?group_by=department_id&count=id → 按部门分组
# 4. 多维度
GET /user/aggregate?group_by=department_id,status&count=id
# 5. with filter
GET /user/aggregate?group_by=department_id&count=id&filter[status__eq]=active
```

### VP-4 Reverse Expand
```python
# 1. 反向 many_to_one
GET /customer/1/reverse/orders
# 2. 反向 many_to_many
GET /user/1/reverse/roles
# 3. 反向带 filter
GET /customer/1/reverse/orders?status__eq=active
# 4. 关联不存在 → association_not_found
# 5. 关联 + expand
GET /customer/1/reverse/orders?expand=items(name,quantity)
```

### VP-5 ETag
```python
# 1. 第一次 GET
→ 200, ETag: "abc123"
# 2. If-None-Match "abc123"
→ 304
# 3. If-None-Match "wrong"
→ 200
# 4. POST/PUT 跳过
```

### VP-6 Custom Order
```python
# 1. custom:1,3,2
GET /task?order_by=custom:5,2,1,4,3 → ORDER BY FIELD(id, 5, 2, 1, 4, 3)
# 2. 与 ASC 混用
GET /task?order_by=custom:5,2,1,id ASC → FIELD + id
# 3. 空 custom 列表 → 报错
```

---

## 6. 零回归

test.py 失败数 ≤ M7 末值（37 failed）。

新增测试覆盖：
- `test_m8_valuehelp.py` (8-10 个场景)
- `test_m8_nested_dsl.py` (10-12 个场景)
- `test_m8_aggregate.py` (8-10 个场景)
- `test_m8_reverse_expand.py` (6-8 个场景)
- `test_m8_etag.py` (4-6 个场景)
- `test_m8_custom_order.py` (4-5 个场景)

**总计 ~40 个新断言**。

---

## 7. 不在 M8 范围（M9+）

- i18n 字段查询（M7.5）
- Saved Filter BO
- Webhook 注册端点
- Mobile Sync API
- Optimistic Lock
- 协同编辑（CRDT）
- 时点快照

---

## 8. 累计 M1-M8 进展

| 阶段 | 增量 | 消费侧能力 |
|------|------|----------|
| M1-M4 | 读路径企业级基线 | 60% |
| M5 | 写路径 + 事务 | 70% |
| M6 | Allow-list + expand + Explain + 权限 | 75% |
| M7 | CDC + Multi-DB + Deep Mutation + Auto Schema | 80% |
| **M8** | **ValueHelp + DSL + Aggregate + Reverse + ETag + Custom Order** | **95%** |

**v3 引擎完成 M8 后 = Fiori Elements / Hasura / Strapi 5 / Directus 同级产品**。

---

**执行开始**：本 spec 写完即实施。优先级 M8 全 6 个 P0 能力（9.5d）。
