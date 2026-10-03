"""
Computed Field Subquery Builders (FR-Cleanup 2026-06-10)

集中管理 storage=virtual 字段的子查询 SQL 表达式, 避免在
sort / filter / enrichment 多处重复编写, 杜绝类似"count_children
在 sort 路径漏覆盖"的回归.

本模块是 **纯 SQL 字符串构造层**, 不直接执行查询, 调用方:
- query_service._execute_computed_field_query  (sort 路径)
- query_service._apply_count_relations_filter  (filter 路径)
- query_service._apply_count_children_filter   (filter 路径)

支持 computation.type:
- count_relations:  统计 relationships 行数
    * scope=self + business_object: source/target 二选一
    * scope=self + org:               org_members 行数 (原 user_group, Spec 16 迁移)
    * scope=descendants + domain/sub_domain/service_module:
      通过 business_objects 链路递归
- count_children:   统计子对象行数
    * service_module -> business_objects
    * sub_domain     -> service_modules
    * domain         -> sub_domains
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 合法 SQL 标识符 (表名/列名), 防注入. table_name 另由 validate_table_name 校验.
_SAFE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


# ─────────────────────────────────────────────────────────
# count_relations
# ─────────────────────────────────────────────────────────

def build_count_relations_expr(
    table_name: str,
    object_type: str,
    scope: str = "self",
    rel_table: str = "relationships",
) -> Optional[str]:
    """构造 count_relations 子查询表达式 (不包含 AS alias).

    Args:
        table_name: 当前主表表名 (用于 {table_name}.id 引用)
        object_type: 当前对象类型 (business_object / org /
            domain / sub_domain / service_module)
        scope: "self" (直接统计) 或 "descendants" (递归子节点统计)
        rel_table: 关系表名, 默认 relationships

    Returns:
        "(SELECT COUNT(*) FROM ...)" 字符串, 若不支持则返回 None.
    """
    if scope == "self" and object_type == "business_object":
        return (
            f"(SELECT COUNT(*) FROM {rel_table} "
            f"WHERE {rel_table}.source_bo_id = {table_name}.id "
            f"OR {rel_table}.target_bo_id = {table_name}.id)"
        )
    if scope == "self" and object_type == "org":
        # [Spec 16 2026-08-29] user_group → org, 字段 group_id → org_id
        # [FIX 2026-10-03] Spec 16 只改了表名/外键, 漏改 dispatch key, 导致 org 一直
        # 走不到本分支 (org.member_count 排序 400 / 过滤被静默丢弃)
        return (
            f"(SELECT COUNT(*) FROM org_members "
            f"WHERE org_members.org_id = {table_name}.id)"
        )
    if scope == "descendants":
        if object_type == "domain":
            inner = (
                f"SELECT bo.id FROM business_objects bo "
                f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                f"JOIN sub_domains sd ON sm.sub_domain_id = sd.id "
                f"WHERE sd.domain_id = {table_name}.id"
            )
        elif object_type == "sub_domain":
            inner = (
                f"SELECT bo.id FROM business_objects bo "
                f"JOIN service_modules sm ON bo.service_module_id = sm.id "
                f"WHERE sm.sub_domain_id = {table_name}.id"
            )
        elif object_type == "service_module":
            inner = (
                f"SELECT bo.id FROM business_objects bo "
                f"WHERE bo.service_module_id = {table_name}.id"
            )
        else:
            logger.warning(
                f"[ComputedSubqueries] count_relations descendants: "
                f"unsupported object_type={object_type}"
            )
            return None
        return (
            f"(SELECT COUNT(DISTINCT r.id) FROM {rel_table} r "
            f"WHERE r.source_bo_id IN ({inner}) "
            f"OR r.target_bo_id IN ({inner}))"
        )
    logger.warning(
        f"[ComputedSubqueries] count_relations: "
        f"unsupported scope/object scope={scope} object_type={object_type}"
    )
    return None


# ─────────────────────────────────────────────────────────
# count_children
# ─────────────────────────────────────────────────────────

# 层级映射: parent_type -> (child_table, child_parent_fk)
# [R0-3 2026-06-11] 扩展支持 product->version + enum_type->enum_value
# 必须与 meta/core/computed_field_query.py:_COUNT_CHILDREN_OBJECTS 同步
_COUNT_CHILDREN_MAP = {
    "version":        ("domains",         "version_id"),
    "domain":         ("sub_domains",     "domain_id"),
    "sub_domain":     ("service_modules", "sub_domain_id"),
    "service_module": ("business_objects", "service_module_id"),
    "product":        ("versions",        "product_id"),
    "enum_type":      ("enum_values",     "enum_type_id"),
}

# [R0-3 2026-06-11] 同步支持矩阵 (供 meta/core/computed_field_query.py 调用)
# 注意: 这个 list 必须与 _COUNT_CHILDREN_MAP 的 keys 完全一致
COUNT_CHILDREN_SUPPORTED = set(_COUNT_CHILDREN_MAP.keys())


def build_count_children_expr(
    table_name: str,
    object_type: str,
) -> Optional[str]:
    """构造 count_children 子查询表达式 (不包含 AS alias).

    Args:
        table_name: 当前主表表名 (用于 {table_name}.id 引用)
        object_type: 当前对象类型 (service_module / sub_domain / domain)

    Returns:
        "(SELECT COUNT(*) FROM ...)" 字符串, 若不支持则返回 None.
    """
    mapping = _COUNT_CHILDREN_MAP.get(object_type)
    if not mapping:
        logger.warning(
            f"[ComputedSubqueries] count_children: unsupported object_type={object_type}"
        )
        return None
    child_table, fk = mapping
    return (
        f"(SELECT COUNT(*) FROM {child_table} "
        f"WHERE {child_table}.{fk} = {table_name}.id)"
    )


# ─────────────────────────────────────────────────────────
# 取值聚合 (rollup): sum_field / avg_field / max_field / min_field
# ─────────────────────────────────────────────────────────

# computation.type → SQL 聚合函数. 本表是**唯一**权威来源,
# ComputationService.AGGREGATION_TYPES 直接引用本表 (避免两处漂移).
AGGREGATION_SQL_FUNCS = {
    "sum_field": "SUM",
    "avg_field": "AVG",
    "max_field": "MAX",
    "min_field": "MIN",
}

SQL_AGGREGATION_TYPES = tuple(AGGREGATION_SQL_FUNCS.keys())


def resolve_parent_aggregation(
    computation: dict,
) -> Optional[Tuple[str, str, str, str]]:
    """解析「按父外键分组取值聚合」所需参数 (rollup 唯一解析入口).

    声明方式与 count_children 对称: target_object / child_object 指向子对象,
    foreign_key 显式指定外键, 否则从层级配置推导 (HierarchyConfigLoader).

    Args:
        computation: 字段的 computation 配置 dict

    Returns:
        (child_table, fk_field, source_field, sql_func) 或 None (配置不完整)
    """
    if not computation:
        return None

    target_object = computation.get("target_object") or computation.get("child_object", "")
    if not target_object:
        return None

    from meta.core.models import registry
    meta_obj = registry.get(target_object)
    if not meta_obj:
        return None

    fk_field = computation.get("foreign_key", "")
    if not fk_field:
        from meta.services.cascade_service import HierarchyConfigLoader
        fk_field = HierarchyConfigLoader.get_foreign_key(target_object)
    if not fk_field:
        return None

    source_field = computation.get("source_field")
    if not source_field:
        return None

    sql_func = AGGREGATION_SQL_FUNCS.get(computation.get("type", ""))
    if not sql_func:
        return None

    return meta_obj.table_name, fk_field, source_field, sql_func


def build_aggregate_field_expr(
    table_name: str,
    child_table: str,
    fk_field: str,
    source_field: str,
    sql_func: str,
) -> Optional[str]:
    """构造「聚合子表 source_field」的相关子查询表达式.

    (SELECT SUM(child.amount) FROM child WHERE child.parent_id = parent.id)

    与 count_children 同构, 因此可参与 DB 侧 ORDER BY / WHERE,
    **不需要把聚合结果写入父行真实列**(单一事实源, 读时计算).

    Returns:
        "(SELECT {func}(...))" 字符串, 或 None (标识符非法 / 函数不在白名单)
    """
    if sql_func not in AGGREGATION_SQL_FUNCS.values():
        logger.warning(f"[ComputedSubqueries] aggregate: illegal sql_func={sql_func}")
        return None
    for label, ident in (
        ('child_table', child_table), ('fk_field', fk_field),
        ('source_field', source_field),
    ):
        if not ident or not _SAFE_IDENTIFIER.match(ident):
            logger.warning(
                f"[ComputedSubqueries] aggregate: illegal {label}={ident!r}"
            )
            return None
    return (
        f"(SELECT {sql_func}({child_table}.{source_field}) FROM {child_table} "
        f"WHERE {child_table}.{fk_field} = {table_name}.id)"
    )


# ─────────────────────────────────────────────────────────
# Unified dispatch
# ─────────────────────────────────────────────────────────

def build_count_subquery_expr(
    comp_type: str,
    table_name: str,
    object_type: str,
    scope: str = "self",
    computation: Optional[dict] = None,
) -> Optional[str]:
    """统一入口: 根据 comp_type 调用对应 builder.

    Args:
        comp_type: computation.type (count_relations / count_children / sum_field / ...)
        table_name: 主表表名
        object_type: 对象类型
        scope: 仅 count_relations 使用
        computation: 取值聚合 (rollup) 需要 child_object / foreign_key / source_field

    Returns:
        SQL 表达式字符串, 不支持则 None.
    """
    if comp_type == "count_relations":
        return build_count_relations_expr(table_name, object_type, scope)
    if comp_type == "count_children":
        return build_count_children_expr(table_name, object_type)
    if comp_type in SQL_AGGREGATION_TYPES:
        resolved = resolve_parent_aggregation(computation or {})
        if not resolved:
            return None
        child_table, fk_field, source_field, sql_func = resolved
        return build_aggregate_field_expr(
            table_name, child_table, fk_field, source_field, sql_func
        )
    logger.warning(f"[ComputedSubqueries] Unknown comp_type={comp_type}")
    return None


def is_supported(comp_type: str, object_type: str, scope: str = "self",
                 computation: Optional[dict] = None) -> bool:
    """判断 (comp_type, object_type, scope[, computation]) 组合是否被本模块支持."""
    if comp_type == "count_relations":
        if scope == "self" and object_type in ("business_object", "org"):
            return True
        if scope == "descendants" and object_type in (
            "domain", "sub_domain", "service_module"
        ):
            return True
        return False
    if comp_type == "count_children":
        return object_type in _COUNT_CHILDREN_MAP
    if comp_type in SQL_AGGREGATION_TYPES:
        return resolve_parent_aggregation(computation or {}) is not None
    return False
