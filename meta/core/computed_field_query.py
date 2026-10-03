"""
Computed Field Query (SSOT) — [R0-3 2026-06-11]

统一计算字段 (computation/virtual field) sort/filter 的 SQL 构造逻辑, 避免
history bug 模式 (silent fallback + 多套重复实现).

本模块是 **计算字段 sort/filter 行为的唯一入口**, 调用方:
- meta/core/interceptors/persistence_interceptor.py: _build_computed_count_sort_clause
- meta/core/interceptors/persistence_interceptor.py: _try_build_computed_filter
- meta/services/query_service.py: _apply_count_relations_filter (后续会重构)

[设计原则]
1. fail-fast: 不支持的组合立即 raise ComputationNotSupportedError, 不静默 fallback
2. SSOT: 唯一 SQL 构造入口, 4 套历史实现全部 thin adapter
3. 安全: table_name 走 validate_table_name, 防止 SQL 注入
4. 稳定: 次级稳定键 id DESC 防翻页重复

[支持矩阵]
- count_relations self:      business_object, org
- count_relations descendants: domain, sub_domain, service_module
- count_children:            version, domain, sub_domain, service_module
- sum_field / avg_field / max_field / min_field (rollup, 按父外键聚合子表 source_field):
                             取决于 computation 是否给出 child_object/target_object +
                             foreign_key(或可从层级推导) + source_field

[P1/P2 2026-10-03] "必须 DB 下推" 的字段集合 = PUSHDOWN_COMPUTATION_TYPES (按 type 判定,
不再依赖字段名 *_count 后缀). 族内字段的 sort/filter 要么生成子查询, 要么抛
ComputationNotSupportedError → 422; 绝不静默丢弃条件后返回未过滤结果.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple, List, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# 异常 + 支持矩阵
# ─────────────────────────────────────────────────────────

class ComputationNotSupportedError(Exception):
    """[FAIL-FAST] 计算字段在指定对象/作用域下不支持

    替代历史 silent fallback 行为。调用方捕获后:
    - API 层: 返 422 Unprocessable Entity + COMPUTATION_NOT_SUPPORTED error_code
    - 启动时: validate_all_computed_fields() 列出所有错误
    """
    def __init__(self, comp_type: str, object_type: str, scope: str = None,
                 reason: str = ''):
        self.comp_type = comp_type
        self.object_type = object_type
        self.scope = scope
        msg = f"Computation '{comp_type}' not supported for {object_type}"
        if scope:
            msg += f" (scope={scope})"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


# 支持矩阵 (comp_type, object_type, scope) — 与 computed_subqueries 同步
# [R0-3 2026-06-11] 直接 import computed_subqueries 的权威 set, 避免双源同步漂移
from meta.services.query.computed_subqueries import (
    _COUNT_CHILDREN_MAP,
    COUNT_CHILDREN_SUPPORTED,
    SQL_AGGREGATION_TYPES,
    resolve_parent_aggregation,
)

_COUNT_RELATIONS_SELF = {'business_object', 'org'}
_COUNT_RELATIONS_DESCENDANTS = {'domain', 'sub_domain', 'service_module'}

# [P1 2026-10-03] SQL 可下推 (DB 相关子查询) 计算字段族 — **类型级**声明。
#
# 语义: 声明为这些 computation.type 的字段, 其 sort/filter 必须由本模块生成子查询;
#       若 (type, object, scope) 组合不受支持, 抛 ComputationNotSupportedError,
#       调用方不得把条件降级为"静默忽略"。
# 与 is_supported 的区别: is_supported 判断"某个具体组合是否支持",
#       本集合判断"该字段是否属于必须下推的族"(决定 fail-fast 还是交给其他路径)。
#
# [为什么需要类型级判定] 历史调用方用字段名后缀 `*_count` 判定, 因此任何非 `_count`
# 命名的计算字段(如 rollup 的 total_amount)都会被判为"非计算字段"而静默丢弃
# sort/filter 条件 —— 返回未过滤的全量数据。改为按 type 判定后, 字段名不再影响语义。
PUSHDOWN_COMPUTATION_TYPES = (
    ('count_relations', 'count_children') + tuple(SQL_AGGREGATION_TYPES)
)


def is_supported(comp_type: str, object_type: str, scope: str = 'self',
                 computation: dict = None) -> bool:
    """判断 (comp_type, object_type, scope) 组合是否被支持

    单一权威矩阵, 与 computed_subqueries 中的实现同步。

    Args:
        computation: 取值聚合 (sum_field/avg_field/...) 必需 —— 其可支持性取决于
            child_object / foreign_key / source_field 是否可解析, 与 object_type 无关。
    """
    if comp_type == 'count_relations':
        if scope == 'self':
            return object_type in _COUNT_RELATIONS_SELF
        if scope == 'descendants':
            return object_type in _COUNT_RELATIONS_DESCENDANTS
        return False
    if comp_type == 'count_children':
        return object_type in COUNT_CHILDREN_SUPPORTED
    if comp_type in SQL_AGGREGATION_TYPES:
        return resolve_parent_aggregation(computation or {}) is not None
    # formula / hierarchy_scope / dimension_count 走其他路径 (不在本模块范围)
    return False


# ─────────────────────────────────────────────────────────
# 缓存失效 (R1-2)
# ─────────────────────────────────────────────────────────

def invalidate_caches():
    """[R1-2 2026-06-11] 清空所有计算字段相关缓存

    调用方:
    - MetaRegistry.reload() 自动 hook (见本模块 _register_hooks())
    - 测试 setup/teardown
    """
    from meta.services.query import computed_utils
    computed_utils._SCOPE_SORT_ORDER_CACHE.clear()
    computed_utils._SCOPE_SORT_ORDER_LOADED = False

    from meta.services.computation_service import computation_service
    computation_service.invalidate_cache()

    logger.info('[ComputedFieldQuery] caches invalidated')


def _register_hooks():
    """Monkey-patch MetaRegistry.invalidate_caches + reload, 自动清缓存

    [设计权衡] 用 monkey-patch 而不是暴露 register_cache_invalidator API,
    因为计算字段缓存的生命周期与 metadata reload 强绑定, 集成在模块加载时
    自动生效对调用方最简单。

    [FIX 2026-06-11] 链入 invalidate_caches 而非 reload.
    reload() 在 _schema_dir='' 时直接 return, hook 不会触发. 而
    invalidate_caches() 是显式入口, 总是会执行.
    """
    try:
        from meta.core.models import MetaRegistry
    except ImportError:
        return  # 测试环境无 registry
    if getattr(MetaRegistry.invalidate_caches, '_cf_hook_installed', False):
        return
    original_invalidate = MetaRegistry.invalidate_caches

    def new_invalidate(self, *args, **kwargs):
        result = original_invalidate(self, *args, **kwargs)
        invalidate_caches()
        return result

    new_invalidate._cf_hook_installed = True
    MetaRegistry.invalidate_caches = new_invalidate

    # 同时也 hook reload 以处理热重载场景
    original_reload = MetaRegistry.reload

    def new_reload(self, *args, **kwargs):
        result = original_reload(self, *args, **kwargs)
        invalidate_caches()
        return result

    new_reload._cf_hook_installed = True
    MetaRegistry.reload = new_reload
    logger.debug('[ComputedFieldQuery] MetaRegistry.invalidate_caches + reload hooks installed')


_register_hooks()


# ─────────────────────────────────────────────────────────
# 启动时校验 (R0-2)
# ─────────────────────────────────────────────────────────

def validate_all_computed_fields() -> List[str]:
    """[R0-2 2026-06-11] 启动时校验所有 yaml computation 配置

    Returns:
        errors: 错误信息列表, 为空表示通过
    """
    from meta.core.models import registry
    errors = []
    for meta_obj in registry.all():
        for field in getattr(meta_obj, 'fields', []):
            comp = getattr(field, 'computation', None)
            if not comp:
                continue
            comp_type = comp.get('type', '')
            scope = comp.get('scope', 'self')
            if not is_supported(comp_type, meta_obj.id, scope, comp):
                errors.append(
                    f"{meta_obj.id}.{field.id}: computation.type={comp_type} "
                    f"scope={scope} not supported"
                )
    return errors


# ─────────────────────────────────────────────────────────
# SSOT 入口: ComputedFieldQuery
# ─────────────────────────────────────────────────────────

class ComputedFieldQuery:
    """计算字段 sort/filter 统一查询构造器 (SSOT)

    Usage:
        query = ComputedFieldQuery(meta_object, field)

        # sort
        sql_clause = query.build_order_clause(is_desc=True)
        # → "(SELECT COUNT(*) FROM ... ) DESC, {table}.id DESC"

        # filter
        sql_expr, params = query.build_filter_clause('gte', 5)
        # → ("COALESCE((SELECT COUNT(*) FROM ...), -1) >= ?", [5])

    Raises:
        ComputationNotSupportedError: 构造时立即校验, 不支持直接抛
    """

    def __init__(self, meta_object, field):
        from meta.core.table_name_validator import validate_table_name
        self.meta_object = meta_object
        self.field = field
        self.computation = self._computation()
        self.comp_type = self._comp_type()
        self.scope = self._scope()

        # [R0-2 fail-fast] 不支持的组合在构造时就 raise, 而不是返回 None
        if not is_supported(self.comp_type, meta_object.id, self.scope, self.computation):
            raise ComputationNotSupportedError(
                comp_type=self.comp_type,
                object_type=meta_object.id,
                scope=self.scope,
                reason='unsupported combination'
            )

        # [R1-3] SQL 构造前 table_name 校验, 防注入
        self.table_name = validate_table_name(meta_object.table_name)

    def _computation(self) -> dict:
        return getattr(self.field, 'computation', {}) or {}

    def _comp_type(self) -> str:
        return self._computation().get('type', '')

    def _scope(self) -> str:
        return self._computation().get('scope', 'self')

    def _build_subquery_expr(self) -> Optional[str]:
        """委托给 computed_subqueries.build_count_subquery_expr (SSOT 候选)"""
        from meta.services.query.computed_subqueries import build_count_subquery_expr
        return build_count_subquery_expr(
            self.comp_type, self.table_name, self.meta_object.id, self.scope,
            self.computation,
        )

    def build_order_clause(self, is_desc: bool = False) -> Optional[str]:
        """构造 ORDER BY 子句

        Returns:
            "(count_expr) {DIR}, {table}.id DESC" 字符串, 或 None
            (formula / hierarchy_scope 走其他路径, 此处返 None)

        Raises:
            ComputationNotSupportedError: 子查询表达式返回 None 时
        """
        if self.comp_type not in PUSHDOWN_COMPUTATION_TYPES:
            return None

        expr = self._build_subquery_expr()
        if not expr:
            raise ComputationNotSupportedError(
                comp_type=self.comp_type,
                object_type=self.meta_object.id,
                scope=self.scope,
                reason='subquery expr returns None'
            )

        direction = 'DESC' if is_desc else 'ASC'
        # [R1-1 / 决策3] 次级稳定键 id DESC, 与系统默认排序一致
        return f"({expr}) {direction}, {self.table_name}.id DESC"

    def build_filter_clause(self, op: str, value: Any) -> Tuple[Optional[str], List[Any]]:
        """构造 WHERE 子句

        Returns:
            ("COALESCE((count_expr), -1) {op} ?", [value])
            或 IN/NOT IN: ("... IN (?, ?, ...)", [v1, v2, ...])
            或 (None, [])

        Raises:
            ComputationNotSupportedError: 子查询表达式返回 None 时
        """
        if self.comp_type not in PUSHDOWN_COMPUTATION_TYPES:
            return None, []

        expr = self._build_subquery_expr()
        if not expr:
            raise ComputationNotSupportedError(
                comp_type=self.comp_type,
                object_type=self.meta_object.id,
                scope=self.scope,
                reason='subquery expr returns None'
            )

        # [R1-2] NULL 排序策略: COALESCE 把 NULL 转 -1, 永远排最后
        # 注意: 解析器 (parse_operator from _computed_count_clause) 返回 SQL 操作符
        # 例如 __gte → '>='. 我们直接信任输入, 仅在白名单内防止注入.
        _ALLOWED_OPS = {'=', '!=', '>', '>=', '<', '<=', 'LIKE', 'IN', 'NOT IN'}
        if op not in _ALLOWED_OPS:
            raise ValueError(f"Unsupported filter op: {op}")

        # [R0-3] IN / NOT IN 需要展开成 (?, ?, ...) 多占位符
        if op in ('IN', 'NOT IN'):
            values = _normalize_in_values(value, op)
            if not values:
                return '', []
            placeholders = ', '.join(['?'] * len(values))
            coerced = [_coerce_for_field_type(v, getattr(self.field, 'field_type', None))
                       for v in values]
            return f"COALESCE(({expr}), -1) {op} ({placeholders})", coerced

        coerced = _coerce_for_field_type(value, getattr(self.field, 'field_type', None))
        return f"COALESCE(({expr}), -1) {op} ?", [coerced]


# ─────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────

def _coerce_for_field_type(value, field_type):
    """[FIX 2026-06-?] URL 参数始终是字符串, 按字段类型 coerce

    SQLite 在比较 TEXT 占位符与 INTEGER 子查询结果时 type affinity 行为不稳定,
    必须显式转 int/float/bool。
    """
    if field_type is None:
        return value
    type_value = getattr(field_type, 'value', str(field_type))
    if isinstance(value, str):
        if type_value in ('integer', 'int', 'bigint', 'smallint'):
            try:
                return int(value)
            except (ValueError, TypeError):
                return value
        if type_value in ('float', 'double', 'decimal', 'numeric'):
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        if type_value == 'boolean':
            if value.lower() in ('true', '1'):
                return 1
            if value.lower() in ('false', '0'):
                return 0
    return value


# 公开 parse_operator (供 filter URL 解析用)
def parse_filter_operator(key: str) -> Tuple[str, str]:
    """解析过滤字段名的 operator 后缀

    Examples:
        'relation_count__gte' → ('relation_count', 'gte')
        'category_type'      → ('category_type', 'eq')

    Returns:
        (field_name, operator)
    """
    if '__' in key:
        field_name, op = key.rsplit('__', 1)
        return field_name, op
    return key, 'eq'


def _normalize_in_values(value: Any, operator: str) -> List[Any]:
    """[R0-3] IN / NOT IN 值规范化 — 与 _computed_count_clause.normalize_values 同款.

    - string: 按 ',' 拆
    - iterable: 直接转 list
    - 其他:   包成 [value]
    """
    if operator in ('IN', 'NOT IN'):
        if isinstance(value, str):
            return [v.strip() for v in value.split(',') if v.strip()]
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            return list(value)
        return [value]
    return [value]