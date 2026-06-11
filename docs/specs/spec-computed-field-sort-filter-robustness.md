# 计算字段 (computation/virtual field) Sorting/Filtering 健壮性 Spec

> **Spec ID**: SPEC-CF-2026-06-11
> **Status**: Draft (待评审)
> **Authors**: AI Coding Agent
> **Last Updated**: 2026-06-11
> **Target Version**: v3.19.0
> **Priority**: P0 (线上反复出问题)

---

## 1. 背景与目标

### 1.1 业务背景

`excel-to-diagram` 是元建模驱动的 Excel 导入工具, 通过 YAML schema 定义对象/字段/计算规则。其中 `storage=virtual` 的"计算字段" (computation.type in `count_relations` / `count_children` / `formula` / `hierarchy_scope` 等) **不在 DB 物理列中**, 必须由后端在 SQL 层或内存层动态生成。`relationship.category_label` (层级范围) 和 `service_module.relation_count` (关系数量) 是两个最常被用户使用、也最常出问题的计算字段。

### 1.2 现状

- 2026-06-04 至 06-11 已有 8+ 次针对该体系的修补 (SPR-01~08, T-S03-01~05, `_computed_count_clause` 抽取)
- 同一功能散落在 6 个实现层, 缺乏 SSOT (Single Source of Truth)
- v1 (`/api/v1/relationships`) 和 v2 (`/api/v2/bo/relationship`) 端点维护独立 SQL, 行为不一致风险高
- **silent fallback 模式** (失败时静默用默认排序/忽略过滤) 是核心不稳因素

### 1.3 目标

1. **统一 SSOT**: 收敛 sort/filter SQL 构造到 `meta/services/query/computed_subqueries.py` (单一模块)
2. **统一 v1/v2 端点**: 抽 `RelationshipListService` 作为唯一真值源
3. **fail-fast**: 启动时校验所有 computation 组合, 线上失败立即报 4xx
4. **次级稳定键**: 所有 `*_count` 排序追加 `, {table}.id ASC` 防翻页重复
5. **缓存一致性**: 接入 metadata reload 钩子, 清空所有模块级缓存
6. **测试矩阵覆盖**: 补全 14 个 ❌ 单元格, 至少包含 v1+v2 双向 ASC/DESC/filter/enrichment/跨页

### 1.4 非目标

- 不重构整个 `computation_service` 模块 (拆 count/formula/enrichment 三模块)
- 不做性能优化 (N+1 → 批量), 仅修复正确性
- 不改 YAML schema 规范

---

## 2. 现状深度分析 (6 层实现 + 4 套实现)

### 2.1 实现层分布

| 层 | 文件 | 职责 | 状态 |
|----|------|------|------|
| L1 YAML | `meta/schemas/*.yaml` | 声明 `computation.type/scope` 元数据 | ✅ 权威源 |
| L2A persistence_interceptor | `meta/core/interceptors/persistence_interceptor.py` | v2 端点 `crud_query` → `_do_list` 入口 | ⚠️ 重复实现 |
| L2B action_executor (legacy) | `meta/core/action_executor.py` | 历史 v2 路径, 现在被 interceptor 取代 | 🗑️ 待清理 |
| L3 QueryService | `meta/services/query_service.py` | 通用 search, 旧版被使用 | ⚠️ 重复实现 |
| L4A _computed_count_clause | `meta/core/_computed_count_clause.py` | 公共模块 (SPR-02 抽取) | ✅ SSOT 候选 |
| L4B computed_subqueries | `meta/services/query/computed_subqueries.py` | 纯 SQL 字符串构造 | ✅ SSOT 候选 |
| L5 computation_service | `meta/services/computation_service.py` | 内存层 count (N+1) | ⚠️ 与 SQL 层不一致 |
| L6 special_routes_api | `meta/api/special_routes_api.py:144-478` | v1 端点独立 SQL | ❌ 独立实现 |

### 2.2 风险点 (P0/P1/P2)

| ID | 严重度 | 位置 | 风险 | 历史 bug |
|----|--------|------|------|----------|
| **P0-1** | 严重 | `special_routes_api.py:144-478` vs `bo_api.py:201-413` | v1/v2 端点 SQL 拼装完全独立 | `relationship.category_label` 排序 6/10~11 |
| **P0-2** | 严重 | `persistence_interceptor.py:758,771,999,1085` 等 7 处 | silent fallback 不报错 | `relation_count` 主因 |
| **P0-3** | 严重 | `persistence_interceptor.py:503-513` | 走 `crud_query` 的 relationship 列表**不调** `compute_by_semantics` | 待修 (本 spec 修复) |
| **P0-4** | 严重 | `computed_subqueries.py:55-99,135-138` | `table_name` 拼 SQL 无 `validate_table_name` | 潜在 SQL 注入 |
| **P1-1** | 高 | `relationship.yaml:1637` | `api_param_key` vs `key` 映射错位 | — |
| **P1-2** | 高 | `computed_utils.py:79-81` 等 | NULL 排序位置跨实现不统一 | — |
| **P1-3** | 高 | `persistence_interceptor.py:985,998` 等 | `*_count` 排序**缺次级稳定键** | 翻页重复 |
| **P1-4** | 高 | `computed_utils.py:9-10` | 模块级缓存无失效机制 | — |
| **P2-1** | 中 | `computation_service.py:330-369` | N+1 性能问题 | — |
| **P2-2** | 中 | `special_routes_api.py:407-415` | `category_types` SQL 拼接技术债 | — |
| **P2-3** | 中 | 多处 | enum.value/label 翻译不统一 | — |
| **P2-4** | 中 | `persistence_interceptor.py:464-490` | 排序字段未严格校验 | 低危 |

### 2.3 4 套独立实现详解

#### 套 1: `_build_computed_count_sort_clause` (persistence_interceptor.py:961-1002)

```python
# count_children 走 computed_subqueries.build_count_children_expr
# count_relations 走 computed_subqueries.build_count_relations_expr  [FIX 2026-06-11]
# 其他 (m2m/one_to_many/composition) 走 _computed_count_clause.build_order_clause
# silent fallback: build_order_clause 返回 None 时不报错
```

#### 套 2: `_try_build_computed_filter` (persistence_interceptor.py:1004-1156)

```python
# 同上, 委托给 _computed_count_clause.build_filter_clause
# 但 URL 字符串必须 coerce_for_field_type 转 int/float [FIX 2026-06-?]
# silent fallback: 不支持时返回 None, 字段被忽略
```

#### 套 3: `QueryService._apply_count_relations_filter/_apply_count_children_filter` (query_service.py:1282-1372)

```python
# 历史 API, 重复实现同一 SQL 构造
# silent fallback: unsupported scope/object_type 返回 False
```

#### 套 4: `ComputationService._count_relations/_count_children` (computation_service.py:310-440)

```python
# 内存层 N+1, 与 SQL 层并行
# 用于: 单条记录详情, 后端 enrichment
# silent fallback: exception 走 try/except return 0
```

**4 套实现的 root cause**:
- 套 1+2 是新增的 "v2 端点 _do_list 路径" (interceptor 架构)
- 套 3 是历史 "通用 search 路径" (QueryService 旧版)
- 套 4 是 "enrichment 路径" (ComputationService 详情页)
- 套 5 是 v1 端点独立 SQL
- **3 套没有互相同步, 任何修复只覆盖部分端点**

---

## 3. 架构设计

### 3.1 新增模块: `ComputedFieldQuery` 统一接口

**位置**: `meta/core/computed_field_query.py` (新建)

**职责**: 作为所有计算字段 sort/filter 行为的**唯一入口**, 接收 (meta_object, field_name, value, op) 返回 (sql_expr_or_none, params) 或 raise `ComputationNotSupportedError`.

```python
# meta/core/computed_field_query.py

from typing import Optional, Tuple, List, Any
from enum import Enum

class ComputationOp(str, Enum):
    """计算字段支持的过滤操作符"""
    EQ = 'eq'
    GTE = 'gte'
    LTE = 'lte'
    GT = 'gt'
    LT = 'lt'
    IN = 'in'
    NOT_IN = 'notin'


class ComputationNotSupportedError(Exception):
    """[FAIL-FAST] 计算字段在指定对象/作用域下不支持
    
    替代历史 silent fallback 行为。
    启动时 validation 会捕获, 线上会返回 400 + 明确错误。
    """
    def __init__(self, comp_type: str, object_type: str, scope: str = None, reason: str = ''):
        self.comp_type = comp_type
        self.object_type = object_type
        self.scope = scope
        msg = f"Computation '{comp_type}' not supported for {object_type}"
        if scope:
            msg += f" (scope={scope})"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


def is_supported(comp_type: str, object_type: str, scope: str = 'self') -> bool:
    """判断 (comp_type, object_type, scope) 组合是否被支持
    
    is_supported 矩阵: 与 computed_subqueries 中的 _COUNT_CHILDREN_MAP 同步
    """
    if comp_type == 'count_relations':
        if scope == 'self':
            return object_type in ('business_object', 'user_group')
        if scope == 'descendants':
            return object_type in ('domain', 'sub_domain', 'service_module')
        return False
    if comp_type == 'count_children':
        return object_type in ('version', 'domain', 'sub_domain', 'service_module')
    if comp_type == 'formula':
        return True  # formula 通用, 但具体执行可能在 is_supported 之外
    if comp_type == 'hierarchy_scope':
        return object_type == 'relationship'
    return False


class ComputedFieldQuery:
    """计算字段 sort/filter 统一查询构造器 (SSOT)
    
    Usage:
        query = ComputedFieldQuery(meta_object, field)
        
        # sort
        sql_clause = query.build_order_clause(is_desc=True)
        # → "(SELECT COUNT(*) FROM ... ) DESC, {table}.id ASC"
        
        # filter
        sql_expr, params = query.build_filter_clause('gte', 5)
        # → ("(SELECT COUNT(*) FROM ...) >= ?", [5])
    """
    
    def __init__(self, meta_object, field):
        from meta.core.table_name_validator import validate_table_name
        self.meta_object = meta_object
        self.field = field
        # 启动时校验, 失败抛 ComputationNotSupportedError
        if not self._validate():
            raise ComputationNotSupportedError(
                comp_type=self._comp_type(),
                object_type=meta_object.id,
                scope=self._scope(),
                reason='unsupported combination'
            )
        # SQL 构造前 table_name 校验
        self.table_name = validate_table_name(meta_object.table_name)
    
    def _comp_type(self) -> str:
        comp = getattr(self.field, 'computation', {}) or {}
        return comp.get('type', '')
    
    def _scope(self) -> str:
        comp = getattr(self.field, 'computation', {}) or {}
        return comp.get('scope', 'self')
    
    def _validate(self) -> bool:
        return is_supported(self._comp_type(), self.meta_object.id, self._scope())
    
    def build_order_clause(self, is_desc: bool = False) -> Optional[str]:
        """构造 ORDER BY 子句, 返回 None 表示 SQL 层不排, 由内存排
        
        Returns:
            "(count_expr) {DIR}, {table}.id ASC" 字符串, 或 None
        """
        comp_type = self._comp_type()
        if comp_type not in ('count_relations', 'count_children'):
            return None  # formula / hierarchy_scope 走其他路径
        expr = build_count_subquery_expr(
            comp_type, self.table_name, self.meta_object.id, self._scope()
        )
        if not expr:
            raise ComputationNotSupportedError(
                comp_type=comp_type, object_type=self.meta_object.id,
                scope=self._scope(), reason='subquery expr returns None'
            )
        direction = 'DESC' if is_desc else 'ASC'
        # [FIX P1-3] 次级稳定键: id ASC 防止翻页重复
        return f"({expr}) {direction}, {self.table_name}.id ASC"
    
    def build_filter_clause(self, op: str, value: Any) -> Tuple[Optional[str], List[Any]]:
        """构造 WHERE 子句, 返回 (sql, params) 或 (None, []) 表示不支持
        
        Returns:
            ("(count_expr) >= ?", [5]) 或 (None, [])
        
        Raises:
            ComputationNotSupportedError: 当组合不被支持时
        """
        comp_type = self._comp_type()
        if comp_type not in ('count_relations', 'count_children'):
            return None, []  # formula / hierarchy_scope 走其他路径
        expr = build_count_subquery_expr(
            comp_type, self.table_name, self.meta_object.id, self._scope()
        )
        if not expr:
            raise ComputationNotSupportedError(
                comp_type=comp_type, object_type=self.meta_object.id,
                scope=self._scope(), reason='subquery expr returns None'
            )
        # [FIX P1-2] NULL 排序策略: COALESCE 把 NULL 转 -1 (永远排最后)
        op_map = {
            'eq':  '=', 'neq': '!=', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=',
        }
        sql_op = op_map.get(op)
        if not sql_op:
            raise ValueError(f"Unsupported op: {op}")
        # coerce value by field type
        coerced = coerce_for_field_type(value, getattr(self.field, 'field_type', None))
        return f"COALESCE(({expr}), -1) {sql_op} ?", [coerced]


# 模块级入口
def build_count_subquery_expr(comp_type: str, table_name: str, object_type: str, scope: str = 'self') -> Optional[str]:
    """委托给 computed_subqueries.build_count_subquery_expr (现有 SSOT 候选)"""
    from meta.services.query.computed_subqueries import build_count_subquery_expr as _impl
    return _impl(comp_type, table_name, object_type, scope)


def coerce_for_field_type(value, field_type):
    """URL 参数始终是字符串. 按字段类型转 int/float/bool, 避免 SQLite type affinity 问题."""
    # 现有 _computed_count_clause.coerce_for_field_type 同款
    from meta.core._computed_count_clause import coerce_for_field_type as _impl
    return _impl(value, field_type)
```

### 3.2 新增 `RelationshipListService` (R0-1)

**位置**: `meta/services/relationship_list_service.py` (新建)

```python
# meta/services/relationship_list_service.py

from typing import Dict, Any, Optional, List, Tuple
from meta.core.computed_field_query import ComputationNotSupportedError


class RelationshipListService:
    """[R0-1] relationship 列表查询的 SSOT, v1/v2 端点共享.
    
    替代:
    - special_routes_api._list_relationships_impl (v1)
    - bo_api._query_relationship_with_scope (v2 scope 专用)
    - bo_api.query_bo (v2 crud_query 路径)
    
    v1/v2 端点变成 thin adapter:
    - v1: list_relationships() → RelationshipListService.list(sort_by='category_label', sort_order='asc', filters={...})
    - v2 query_bo: query_bo() → RelationshipListService.list(ordering='category_label', ...)
    """
    
    # sort 字段映射: v1 风格 (sort_by=category_type) ↔ v2 风格 (ordering=category_label)
    _SORT_FIELD_ALIASES = {
        'category_label': 'category_label',
        'category_type': 'category_type',
    }
    
    # filter 字段映射: 前端列 prop (category_label) ↔ DB 实际列 (category_type)
    _FILTER_FIELD_ALIASES = {
        'category_label': 'category_type',  # 翻译: 中文 label → enum code
    }
    
    def __init__(self, ds):
        self.ds = ds
        from meta.services.query.computed_subqueries import build_count_subquery_expr
        from meta.core.virtual_field_transform import load_scope_rules_from_ref
        from meta.services.query.computed_utils import (
            ensure_hierarchy_ids_for_relationships,
        )
        from meta.services.computation_service import computation_service
        from meta.core.enrichment_engine import enrich_records
        # 注入依赖 (替代 hard import)
        self._build_count_expr = build_count_subquery_expr
        self._load_scope_rules = lambda: load_scope_rules_from_ref('hierarchies.hierarchy_scopes')
        self._ensure_hierarchy = ensure_hierarchy_ids_for_relationships
        self._compute_semantics = computation_service.compute_by_semantics
        self._enrich_records = enrich_records
    
    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        ordering: Optional[str] = None,      # v2 风格: '-category_label' or 'category_type'
        sort_by: Optional[str] = None,      # v1 风格: 'category_type'
        sort_order: Optional[str] = 'asc',
        clean_filters: Optional[Dict[str, Any]] = None,
        extra_conditions: Optional[List[Tuple[str, List[Any]]]] = None,  # 外部传 WHERE 子句
        include_hierarchy_enrichment: bool = True,  # 关系专用 enrichment
    ) -> Dict[str, Any]:
        """统一的 relationship 列表查询.
        
        Returns:
            {'success': True, 'data': {'items': [...], 'total': N, 'page': 1, ...}}
        
        Raises:
            ComputationNotSupportedError: 计算字段不被支持
        """
        # 1. 解析排序参数 (兼容 v1/v2 风格)
        actual_sort_by, actual_sort_order = self._resolve_sort(ordering, sort_by, sort_order)
        
        # 2. 构造 ORDER BY 子句
        order_clause = self._build_order_clause(actual_sort_by, actual_sort_order)
        
        # 3. 构造 WHERE 子句 (统一处理 category_type(s)/category_label 等语义过滤)
        where_sql, bind_params = self._build_where(clean_filters or {}, extra_conditions or [])
        
        # 4. count + data 查询
        total = self._count(where_sql, bind_params)
        data = self._select(where_sql, bind_params, order_clause, page, page_size)
        
        # 5. [FIX P0-3] enrichment 顺序: 先 ensure hierarchy ids, 再 compute semantics
        if include_hierarchy_enrichment:
            self._ensure_hierarchy(self.ds, data)
            self._compute_semantics('relationship', data, self.ds)
        
        return {
            'success': True,
            'data': {
                'items': data,
                'total': total,
                'page': page,
                'page_size': page_size,
            }
        }
    
    def _resolve_sort(self, ordering, sort_by, sort_order):
        """v1 风格 (sort_by, sort_order) 与 v2 风格 (ordering) 互转"""
        if ordering is not None:
            is_desc = ordering.startswith('-')
            field = ordering.lstrip('-')
            return field, ('desc' if is_desc else 'asc')
        if sort_by is not None:
            return sort_by, (sort_order or 'asc').lower()
        return None, None
    
    def _build_order_clause(self, sort_by, sort_order):
        if sort_by in ('category_label', 'category_type'):
            rules = self._load_scope_rules()
            if not rules:
                # [R0-2] fail-fast: 之前是 fallback to 'r.created_at', 现在 raise
                raise ComputationNotSupportedError(
                    comp_type='hierarchy_scope', object_type='relationship',
                    reason='hierarchy_scopes rules not loaded'
                )
            scope_sql = _build_relationship_scope_sort_sql(rules, sort_by)
            direction = 'DESC' if sort_order == 'desc' else 'ASC'
            # [FIX P1-3] 次级稳定键
            return f"({scope_sql}) {direction}, r.id ASC"
        # 普通列
        direction = 'DESC' if sort_order == 'desc' else 'ASC'
        col = _VALID_SORT_FIELDS.get(sort_by)
        if not col:
            return None
        return f"{col} {direction}"
    
    # _build_where, _count, _select 方法省略 (委托给现有的 _build_relationship_filter_clause)
```

### 3.3 新增启动时校验 (R0-2)

**位置**: `meta/core/startup_validators.py` (新建)

```python
# meta/core/startup_validators.py

from meta.core.models import registry
from meta.core.computed_field_query import (
    is_supported, ComputationNotSupportedError
)


def validate_all_computed_fields() -> List[str]:
    """[R0-2] 启动时校验所有 yaml computation 配置.
    
    Returns:
        errors: 错误信息列表, 为空表示通过
    """
    errors = []
    for meta_obj in registry.all():
        for field in getattr(meta_obj, 'fields', []):
            comp = getattr(field, 'computation', None)
            if not comp:
                continue
            comp_type = comp.get('type', '')
            scope = comp.get('scope', 'self')
            if not is_supported(comp_type, meta_obj.id, scope):
                errors.append(
                    f"{meta_obj.id}.{field.id}: computation.type={comp_type} "
                    f"scope={scope} not supported"
                )
    return errors


def register_startup_validators(app):
    """注册到 Flask app startup hook"""
    @app.before_request
    def _check_lazy():
        # 首次请求时校验, 不阻塞启动
        from threading import Lock
        if not hasattr(app, '_cf_validated'):
            app._cf_validated = True
            app._cf_lock = Lock()
        with app._cf_lock:
            if not app._cf_validated:
                return
            app._cf_validated = True
            errors = validate_all_computed_fields()
            if errors:
                logger.error(f"[StartupValidator] computed field errors: {errors}")
                # 不 raise, 记录到 metrics, 让请求仍然能跑
                # 但返回警告头, 方便 admin 排查
```

### 3.4 新增缓存失效钩子 (R1-2)

**位置**: `meta/core/computed_field_query.py` 内部, 注册到 `MetaRegistry.reload()`

```python
def invalidate_caches():
    """[R1-2] 清空所有计算字段相关缓存.
    
    调用方: MetaRegistry.reload() 钩子, 启动时 reload, 测试 setup/teardown
    """
    from meta.services.query import computed_utils
    computed_utils._SCOPE_SORT_ORDER_CACHE.clear()
    computed_utils._SCOPE_SORT_ORDER_LOADED = False
    
    from meta.services.computation_service import computation_service
    computation_service.invalidate_cache()
    
    logger.info('[ComputedFieldQuery] caches invalidated')


# 自动注册到 reload 钩子
def _register_hooks():
    from meta.core.models import MetaRegistry
    original_reload = MetaRegistry.reload
    def new_reload(self, *args, **kwargs):
        result = original_reload(self, *args, **kwargs)
        invalidate_caches()
        return result
    MetaRegistry.reload = new_reload
_register_hooks()
```

---

## 4. 详细实现计划

### Phase 1: 紧急修复 (P0, 1 周)

#### 4.1.1 R0-2: 删除 silent fallback (4 处)

**Step 1**: 改 `persistence_interceptor.py:758,771`

```python
# OLD:
if field_storage == FieldStorage.VIRTUAL:
    logger.warning(f"[_do_list] Ignoring filter for virtual field: {key}")
else:
    ...
# else branch keeps filter
if not field:
    logger.warning(f"[_do_list] Ignoring unknown filter field: {key}")

# NEW:
if not field:
    # [R0-2] 未知字段 → 400 而非静默忽略
    raise BadRequest(f"Unknown filter field: {key}")
if getattr(field, 'storage', None) == FieldStorage.VIRTUAL:
    # 区分两种 virtual: 走 computed_subqueries vs 走 hierarchy_scope vs 完全不支持
    from meta.core.computed_field_query import ComputedFieldQuery
    try:
        cfq = ComputedFieldQuery(meta_object, field)
        # ... 走 computed 路径
    except ComputationNotSupportedError as e:
        raise BadRequest(str(e))
```

**Step 2**: 改 `persistence_interceptor.py:999`

```python
# OLD:
if count_expr:
    return f"{count_expr} {direction}"
logger.warning(...)
# (fallback through to next branch)

# NEW:
if count_expr:
    return f"({count_expr}) {direction}, {meta_object.table_name}.id ASC"
# [R0-2] 不再 silent fallback 到 build_order_clause 的 m2m 等
# (那种场景需要显式声明, 不能从 count_relations 偷偷降级)
```

**Step 3**: 改 `query_service.py:344,472` (同模式)

**Step 4**: 改 `special_routes_api.py:288-291`

```python
# OLD:
if rules:
    scope_sql = _build_relationship_scope_sort_sql(rules, sort_by)
    order_field = scope_sql
else:
    order_field = 'r.created_at'  # silent fallback

# NEW:
if not rules:
    # [R0-2] fail-fast
    raise ComputationNotSupportedError(
        comp_type='hierarchy_scope', object_type='relationship',
        reason='hierarchy_scopes rules not loaded'
    )
```

#### 4.1.2 R0-3: 统一 SSOT 到 `computed_subqueries` + `ComputedFieldQuery`

**Step 1**: `persistence_interceptor._build_computed_count_sort_clause` 改为薄封装:

```python
def _build_computed_count_sort_clause(self, meta_object, field_name, is_desc):
    from meta.core.computed_field_query import ComputedFieldQuery, ComputationNotSupportedError
    try:
        field = meta_object.get_field(field_name)
    except Exception:
        return None
    if not field or not getattr(field, 'computed', False):
        return None
    try:
        cfq = ComputedFieldQuery(meta_object, field)
        return cfq.build_order_clause(is_desc=is_desc)
    except ComputationNotSupportedError:
        # [R0-2] 委托到 caller 决定 (raise or fallback)
        raise
```

**Step 2**: `_try_build_computed_filter` 同模式改造

**Step 3**: 删除 `_computed_count_clause.py` (除 `coerce_for_field_type` 等工具函数), 全部委托到 `ComputedFieldQuery`

#### 4.1.3 R0-4: 修 v2 普通 relationship 列表 enrichment 缺失

**位置**: `meta/core/interceptors/persistence_interceptor.py:503-513`

```python
def _post_process_records(self, meta_object, records, registry, order_by, virtual_sort):
    records = self._enrich_audit_virtual_fields(meta_object, records, registry.ds)
    engine = EnrichmentEngine.for_data_source(registry.ds)
    records = engine.enrich_association_counts(meta_object, records)
    records = engine.enrich_fk_display_names(meta_object, records)
    
    # [FIX 2026-06-11 R0-4] relationship 列表必须 enrichment
    #   路径与 v2 专用 _query_relationship_with_scope 对齐
    if meta_object.id == 'relationship':
        from meta.services.query.computed_utils import ensure_hierarchy_ids_for_relationships
        from meta.services.computation_service import computation_service
        ensure_hierarchy_ids_for_relationships(registry.ds, records)
        computation_service.compute_by_semantics('relationship', records, registry.ds)
    
    if order_by and not virtual_sort:
        records = self._sort_by_virtual_fields(meta_object, records, order_by)
    return records
```

### Phase 2: 高优修复 (P1, 1-2 周)

#### 4.2.1 R0-1: 抽 `RelationshipListService` (3 天)

1. 新建 `meta/services/relationship_list_service.py`, 实现 `list()` 方法
2. 改 `special_routes_api.list_relationships` (v1 端点) 委托给 `RelationshipListService.list(sort_by=..., sort_order=..., filters=...)`
3. 改 `bo_api.query_bo` 当 `object_type == 'relationship'` 时委托给 `RelationshipListService.list(ordering=..., clean_filters=...)`
4. 删除 `bo_api._query_relationship_with_scope` (功能并入 service)
5. 改 `bo_api._build_relationship_filter_clause` 改为 `RelationshipListService._build_where` 内部方法

#### 4.2.2 R1-1: 所有 `*_count` 排序加次级稳定键

`ComputedFieldQuery.build_order_clause` 已加 `, {table}.id ASC`. 验证 `_do_list` 实际拼装.

#### 4.2.3 R1-2: 缓存失效钩子

新建 `meta/core/computed_field_query.py: invalidate_caches()`, hook 到 `MetaRegistry.reload()`. 同 `computed_utils._SCOPE_SORT_ORDER_CACHE.clear()`.

#### 4.2.4 R1-3: `validate_table_name` 兜底

`ComputedFieldQuery.__init__` 已调 `validate_table_name(self.table_name)`. 旧路径 (`_build_computed_count_sort_clause`) 通过调 `ComputedFieldQuery` 自动获得.

### Phase 3: 测试矩阵补全 (1 周)

#### 4.3.1 补 ❌ 单元格 (按优先级)

| 缺口 | 优先级 | 测试 |
|------|--------|------|
| user_group count_relations self sort | P2 | `test_user_group_member_count_sort_*.py` |
| 全部 v1 端点 filter (count_*) | P2 | `test_v1_filter_count_*.py` |
| 跨页"无重复" + "无丢失" | P1 | 扩 `test_relation_count_pagination_consistent` |
| formula 字段 ASC + 跨页 | P2 | `test_bo_density_sort_asc.py` |
| 非法 sort/filter fail-fast | P0 | `test_sort_invalid_raises_400.py`, `test_filter_invalid_raises_400.py` |
| 缓存失效 on YAML reload | P1 | `test_cache_invalidates_on_yaml_reload.py` |
| NULL 排序永远在末 | P1 | `test_null_count_sort_always_last.py` |

---

## 5. 测试用例模板

### 5.1 P0 必测 (silent fallback 已禁)

```python
# meta/tests/test_computed_field_robustness.py

import pytest


class TestFailFastOnInvalidSort:
    """[R0-2] 计算字段 sort/filter 配置错误 → 400, 不静默 fallback."""

    def test_sort_by_unknown_count_raises_400(self, admin_session):
        """未知 *_count 字段 → 400"""
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/service_module',
            params={'ordering': 'mystery_count'},
        )
        assert r.status_code in (400, 422), f"Expected 4xx, got {r.status_code}"
        body = r.json()
        assert 'message' in body or 'error' in body
        assert 'unknown' in str(body).lower() or 'invalid' in str(body).lower()

    def test_filter_by_unknown_count_raises_400(self, admin_session):
        """未知 *_count 字段过滤 → 400"""
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/service_module',
            params={'mystery_count__gte': 5},
        )
        assert r.status_code in (400, 422)

    def test_filter_by_virtual_unsupported_field_raises_400(self, admin_session):
        """不支持的 virtual 字段过滤 → 400 (v1 + v2)"""
        # relation_count 在 version 对象上不应被支持
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/version',
            params={'relation_count__gte': 5},
        )
        assert r.status_code in (400, 422)


class TestSecondaryStableKey:
    """[R1-1] *count 排序跨页单调性 + 无重复."""

    @pytest.mark.parametrize("object_type", ["domain", "sub_domain", "service_module"])
    def test_relation_count_pagination_no_duplicates(self, admin_session, object_type):
        """翻页: 总记录数等于所有页记录数之和, 无重复"""
        r1 = admin_session.get(
            f'{BASE_URL}/api/v2/bo/{object_type}',
            params={'ordering': '-relation_count', 'page': 1, 'page_size': 5},
        )
        r2 = admin_session.get(
            f'{BASE_URL}/api/v2/bo/{object_type}',
            params={'ordering': '-relation_count', 'page': 2, 'page_size': 5},
        )
        items1 = r1.json().get('data', {}).get('items', [])
        items2 = r2.json().get('data', {}).get('items', [])
        ids1 = {it.get('id') for it in items1}
        ids2 = {it.get('id') for it in items2}
        assert ids1.isdisjoint(ids2), f"Page 1 and 2 overlap: {ids1 & ids2}"


class TestCacheInvalidation:
    """[R1-2] YAML reload 后缓存清空."""

    def test_scope_sort_order_cache_invalidated_on_reload(self, admin_session):
        from meta.core.models import MetaRegistry
        from meta.services.query import computed_utils
        # 第一次加载, 缓存有数据
        _ = computed_utils._get_scope_sort_order()
        assert computed_utils._SCOPE_SORT_ORDER_LOADED is True
        # 模拟 reload
        MetaRegistry().reload()
        # 缓存应清空
        assert computed_utils._SCOPE_SORT_ORDER_LOADED is False
        assert len(computed_utils._SCOPE_SORT_ORDER_CACHE) == 0


class TestNullCountSortAlwaysLast:
    """[R1-4] NULL 计算值永远排最后."""

    def test_null_relation_count_sort_asc_last(self, admin_session):
        """ASC 排序: NULL relation_count 应在末尾"""
        # 通过 mock 一个 service_module 没有 BO, 其 relation_count 应为 0 (而非 NULL)
        # COALESCE 兜底让 NULL 变 -1 排最后
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/service_module',
            params={'ordering': 'relation_count', 'page_size': 100},
        )
        items = r.json().get('data', {}).get('items', [])
        # 最后一个 item 的 relation_count 应该是 0 或 None, 永远 <= 第一个
        counts = [it.get('relation_count') or 0 for it in items]
        assert counts == sorted(counts), f"counts not ascending: {counts}"
```

### 5.2 跨端点统一测试

```python
# meta/tests/test_relationship_v1_v2_parity.py

class TestV1V2RelationshipParity:
    """[R0-1] v1 端点 /api/v1/relationships 与 v2 /api/v2/bo/relationship 行为一致."""
    
    @pytest.mark.parametrize("sort_by,sort_order", [
        ("category_label", "asc"), ("category_label", "desc"),
        ("category_type", "asc"), ("category_type", "desc"),
        ("created_at", "desc"),
    ])
    def test_v1_v2_return_same_ordering(self, admin_session, sort_by, sort_order):
        """v1 风格 sort_by=category_label 与 v2 风格 ordering=category_label 返回一致"""
        r1 = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'sort_by': sort_by, 'sort_order': sort_order, 'pageSize': 200},
        )
        r2 = admin_session.get(
            f'{BASE_URL}/api/v2/bo/relationship',
            params={'ordering': sort_by, 'page_size': 200},
        )
        items1 = r1.json().get('data', [])
        items2 = r2.json().get('data', {}).get('items', [])
        ids1 = [it.get('id') for it in items1]
        ids2 = [it.get('id') for it in items2]
        assert ids1 == ids2, (
            f"v1 vs v2 order differ for {sort_by} {sort_order}: "
            f"v1={ids1[:5]}... v2={ids2[:5]}..."
        )
```

---

## 6. 风险评估与回滚

### 6.1 实施风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 删除 silent fallback 暴露历史隐藏 bug | 高 | 中 (线上 4xx 增加) | 启动时 validation 提前发现, 灰度发布 |
| RelationshipListService 重构破坏 v1 兼容性 | 中 | 高 | 保留 v1 query param 解析, 内部统一; 端到端测试覆盖 |
| 启动时校验拖慢冷启动 | 低 | 低 | 校验 < 100ms (YAML 解析后遍历) |
| 缓存清空导致 N+1 雪崩 | 低 | 中 | 灰度期间观察 P99 延迟 |

### 6.2 回滚策略

每阶段独立 commit, 单独 revert:
- Phase 1: 4.1.1~4.1.3 三个独立 commit
- Phase 2: 4.2.1~4.2.4 四个独立 commit
- Phase 3: 测试 commit

灰度发布顺序:
1. 内部测试环境 (1 天)
2. UAT (1 天)
3. 灰度 10% (1 天)
4. 灰度 50% (1 天)
5. 全量 (与产品协商)

### 6.3 监控指标

- `[_do_list] error_code=400/422` 计数 (silent fallback 改为 4xx 后会增加)
- `[_do_list] latency p99` (新增 SQL 校验不阻塞请求)
- `[ComputedFieldQuery] cache_miss_rate` (缓存命中率)
- `[RelationshipListService] call_count` by v1/v2 端点

---

## 7. 文档与迁移

### 7.1 API 文档更新

- 公开 `relationship_list_service.py` 文档
- 在 `docs/api/relationships.md` 中标注 v1 端点 deprecation 时间表
- 在 YAML schema `relationship.yaml` 的 `computation` 字段增加"支持矩阵"注释

### 7.2 数据库迁移

不需要 schema 变更, 但需要:
- 在 `meta/schemas/relationship.yaml` 的 `category_label` 字段增加 `computation.scope: descendants` 注释, 明确支持矩阵
- 在所有 `*_count` 字段增加 `computation.validated_at: <日期>` 标记 (供 `validate_all_computed_fields` 使用)

### 7.3 团队沟通

- Slack #engineering: 提前 1 周通知 v1 端点将被 deprecate (但仍然兼容)
- 文档: 内部 wiki 更新"计算字段规范", 强调"**禁止**在 persistence_interceptor / action_executor 写 sort/filter 逻辑, 必须走 ComputedFieldQuery"

---

## 8. 设计决策 (已判断)

### 决策 1: v1 端点 deprecate 时间表

**结论**: **推迟, 不在 v3.20 范围**
- **依据**: 项目已有 `deprecate_v1_crud` (`server.py:718-735`) 把非豁免 v1 CRUD 路由返 410 Gone + 迁移提示; `V1_SPECIAL_PREFIXES` (`server.py:701-716`) 把 `relationships` / `business_object` 等业务路由保留
- **行动**: 本 spec 暂不触动 v1 端点, 但 `RelationshipListService` 设计已为 v1/v2 统一做好准备, 后续 v1 deprecate 时只需 thin adapter 替换

### 决策 2: `field is None` 时 fail-fast 严格度

**结论**: **400 Bad Request** (与项目 18+ 处既有用法一致)

- **依据**: `bo_api.py:506,538,637,667,688,692,694,699` 全部用 400 返回"参数缺失/格式错误"
- **统一错误格式**: `{success: False, error_code: "UNKNOWN_FIELD", message: "Unknown field: X", details: {valid_fields: [...]}}`
- **理由**: silent fallback 让前端拼写错字段名时"看似成功"但结果错误, 比 400 更难排查

### 决策 3: tiebreaker 方向

**结论**: **`id DESC`** (新记录优先, 与项目默认排序一致)

- **依据**:
  - `persistence_interceptor.py:841,843,908,910` 全部 `ORDER BY id DESC`
  - `persistence_interceptor.py:624,700` 默认 `order_by = '-updated_at'`
  - 用户期望"按 X 排序时, 同 X 值里最新记录在前" 与系统默认行为一致
- **统一**: 把 `id DESC` 也加入 `_build_order_by_clause` 主路径 (不只在 computed 路径)

### 决策 4: 启动时校验的位置

**结论**: **`before_request` (首次请求触发) + 独立 CLI 入口**

- **依据**:
  - Flask 项目无 `app.startup` 钩子, 当前用 `before_request` 数组 (`server.py:507,532,718`)
  - 启动阻塞校验在 SQLite 启动慢的场景下不友好
- **实现**:
  - 生产: `before_request` 首次请求时校验 + 用 `_cf_validated: bool` flag 缓存结果
  - 运维: 新增 `python -m meta.core.startup_validators` CLI 入口, CI/CD 部署前调用
  - 双轨: 启动期发现 (CI 早失败) + 运行期兜底 (线上配置漂移)

### 决策 5: `ComputationNotSupportedError` HTTP 状态码

**结论**: **422 Unprocessable Entity**

- **对比**:
  - 400: 项目惯用, 但语义是"参数格式错误" (e.g. `target_id is required`)
  - 501: 暗示"将来会实现", 与本 spec "明确不支持" 冲突
  - 422: **语义最准** —— 请求格式正确但语义无法处理 (computation 配错对象类型)
- **统一响应格式**:
  ```json
  {
    "success": false,
    "error_code": "COMPUTATION_NOT_SUPPORTED",
    "message": "count_relations descendants not supported for user_group",
    "details": {
      "comp_type": "count_relations",
      "object_type": "user_group",
      "scope": "descendants"
    }
  }
  ```

### 全局统一错误响应模板

`ComputedFieldQuery` 在 4 处 raise `ComputationNotSupportedError`, 调用方统一拦截:

```python
# meta/api/bo_api.py: 新增 errorhandler
from meta.core.computed_field_query import ComputationNotSupportedError

@bo_bp.errorhandler(ComputationNotSupportedError)
def handle_computation_error(e: ComputationNotSupportedError):
    return jsonify({
        'success': False,
        'error_code': 'COMPUTATION_NOT_SUPPORTED',
        'message': str(e),
        'details': {
            'comp_type': e.comp_type,
            'object_type': e.object_type,
            'scope': e.scope,
        }
    }), 422
```

---

**End of Spec**
