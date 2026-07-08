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
    * scope=self + user_group:        user_group_members 行数
    * scope=descendants + domain/sub_domain/service_module:
      通过 business_objects 链路递归
- count_children:   统计子对象行数
    * service_module -> business_objects
    * sub_domain     -> service_modules
    * domain         -> sub_domains
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
        object_type: 当前对象类型 (business_object / user_group /
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
    if scope == "self" and object_type == "user_group":
        return (
            f"(SELECT COUNT(*) FROM user_group_members "
            f"WHERE user_group_members.group_id = {table_name}.id)"
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
# Unified dispatch
# ─────────────────────────────────────────────────────────

def build_count_subquery_expr(
    comp_type: str,
    table_name: str,
    object_type: str,
    scope: str = "self",
) -> Optional[str]:
    """统一入口: 根据 comp_type 调用对应 builder.

    Args:
        comp_type: computation.type (count_relations / count_children / ...)
        table_name: 主表表名
        object_type: 对象类型
        scope: 仅 count_relations 使用

    Returns:
        SQL 表达式字符串, 不支持则 None.
    """
    if comp_type == "count_relations":
        return build_count_relations_expr(table_name, object_type, scope)
    if comp_type == "count_children":
        return build_count_children_expr(table_name, object_type)
    logger.warning(f"[ComputedSubqueries] Unknown comp_type={comp_type}")
    return None


def is_supported(comp_type: str, object_type: str, scope: str = "self") -> bool:
    """判断 (comp_type, object_type, scope) 组合是否被本模块支持."""
    if comp_type == "count_relations":
        if scope == "self" and object_type in ("business_object", "user_group"):
            return True
        if scope == "descendants" and object_type in (
            "domain", "sub_domain", "service_module"
        ):
            return True
        return False
    if comp_type == "count_children":
        return object_type in _COUNT_CHILDREN_MAP
    return False
