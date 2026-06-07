# -*- coding: utf-8 -*-
"""
数据 enrichment 工具函数（兼容层）。

[v2 兼容层 2026-06-05]
原始的 `enrich_fk_display_names` / `enrich_association_counts` 已迁移到
`meta.core.enrichment_engine.EnrichmentEngine` 实例方法，
本文件保留为兼容 shim，委托给全局 EnrichmentEngine 实例。

新代码请直接使用 `EnrichmentEngine.enrich_fk_display_names()` /
`enrich_association_counts()`，或全局便捷函数
`enrichment_engine.enrich_batch()`。
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_engine():
    """惰性获取全局 EnrichmentEngine 实例，未初始化时回退创建。"""
    from meta.core.enrichment_engine import get_enrichment_engine, EnrichmentEngine
    engine = get_enrichment_engine()
    if engine is None:
        # 兜底：尝试从 bo_framework 拿 data_source
        try:
            from meta.core.bo_framework import bo_framework
            ds = getattr(bo_framework, '_data_source', None)
        except Exception:
            ds = None
        if ds is None:
            from meta.core.datasource import get_data_source
            import os
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            ds = get_data_source('sqlite', database=db_path)
        from meta.core.redundancy_registry import redundancy_registry
        engine = EnrichmentEngine(ds, redundancy_registry)
    return engine


def enrich_fk_display_names(meta_object, records_or_record, data_source=None):
    """为 FK 字段批量注入 {field}_display 字段（v1 兼容路径 → EnrichmentEngine）。

    新代码请直接调用 `EnrichmentEngine.enrich_fk_display_names(meta, records)`。
    保留 `data_source` 参数仅为兼容旧调用方，忽略该参数。
    """
    engine = _get_engine()
    return engine.enrich_fk_display_names(meta_object, records_or_record)


def enrich_association_counts(meta_object, records, data_source=None):
    """为记录批量注入 association count 字段（v1 兼容路径 → EnrichmentEngine）。

    新代码请直接调用 `EnrichmentEngine.enrich_association_counts(meta, records)`。
    保留 `data_source` 参数仅为兼容旧调用方，忽略该参数。
    """
    engine = _get_engine()
    return engine.enrich_association_counts(meta_object, records)


# ============================================================
# 保留：computed count filter / order 子句构造器
# 这些不依赖 data_source，是纯 SQL 模板，保留在 enrich_utils
# （M2 收敛时如需迁移到独立模块，可以单独抽出）
# ============================================================

def _is_computed_count_field(meta_object, field_name: str) -> bool:
    """检查字段是否是 computed *_count 字段（DB 中无物理列，必须走子查询）。"""
    if not meta_object or not field_name:
        return False
    if not field_name.endswith('_count'):
        return False
    try:
        field = meta_object.get_field(field_name)
    except Exception:
        field = None
    if field is None:
        return False
    if not getattr(field, 'computed', False):
        return False
    return True


def _find_m2m_assoc_for_count(meta_object, base_name: str):
    """根据 *_count 字段的 base_name 找匹配的 many_to_many 关联。

    Returns:
        (through, source_key) 元组，未找到返回 (None, None)。
    """
    if not meta_object:
        return None, None
    associations = getattr(meta_object, 'associations', None)
    if not associations:
        return None, None
    if isinstance(associations, dict):
        assoc_items = list(associations.values())
    else:
        assoc_items = list(associations)

    for assoc in assoc_items:
        if isinstance(assoc, str):
            assoc_name = assoc
            assoc_type = 'many_to_many'
            through = None
            source_key = None
        else:
            assoc_name = getattr(assoc, 'name', '')
            assoc_type = getattr(assoc, 'type', '')
            through = getattr(assoc, 'through', None)
            source_key = getattr(assoc, 'source_key', None)

        if assoc_type != 'many_to_many':
            continue
        # 匹配规则：member_count <-> members / member
        if (
            assoc_name == base_name
            or assoc_name == base_name + 's'
            or assoc_name.rstrip('s') == base_name
        ):
            if through and source_key:
                return through, source_key
    return None, None


def build_computed_count_filter_clause(meta_object, key: str, value: Any,
                                        target_alias: str = ''):
    """为 computed *_count 字段构造过滤子句。

    支持的操作符（按 key 后缀解析）：
      - __in / __notin: IN / NOT IN
      - __like:        LIKE
      - __gte:         >=
      - __lte:         <=
      - _start:        >=
      - _end:          <=
      - 精确匹配:      =

    target_alias: 子查询中对 source 表的引用（如 't'）；空串表示直接用 meta_object.table_name。

    Returns:
        (sql_clause, [params]) 或 (None, [])
    """
    if not meta_object or not key:
        return None, []

    if key.endswith('__in'):
        field_name = key[:-4]
        operator = 'IN'
        if isinstance(value, str):
            values = [v.strip() for v in value.split(',') if v.strip()]
        else:
            values = list(value) if hasattr(value, '__iter__') else [value]
    elif key.endswith('__notin'):
        field_name = key[:-7]
        operator = 'NOT IN'
        if isinstance(value, str):
            values = [v.strip() for v in value.split(',') if v.strip()]
        else:
            values = list(value) if hasattr(value, '__iter__') else [value]
    elif key.endswith('__like'):
        field_name = key[:-6]
        operator = 'LIKE'
        values = [f"%{value}%"]
    elif key.endswith('__gte'):
        field_name = key[:-5]
        operator = '>='
        values = [value]
    elif key.endswith('__lte'):
        field_name = key[:-5]
        operator = '<='
        values = [value]
    elif key.endswith('_start'):
        field_name = key[:-6]
        operator = '>='
        values = [value]
    elif key.endswith('_end'):
        field_name = key[:-4]
        operator = '<='
        values = [value]
    else:
        field_name = key
        operator = '='
        values = [value]

    if not _is_computed_count_field(meta_object, field_name):
        return None, []

    try:
        field = meta_object.get_field(field_name)
    except Exception:
        field = None
    if field is not None:
        field_type_attr = getattr(field, 'field_type', None)
        is_integer = (
            field_type_attr is not None
            and (str(field_type_attr).endswith('INTEGER') or str(field_type_attr).endswith('INT')
                 or str(field_type_attr) in ('integer', 'int', 'bigint', 'smallint'))
        )
        if is_integer and operator not in ('LIKE',):
            def _coerce(v):
                if isinstance(v, str):
                    try:
                        return int(v)
                    except (ValueError, TypeError):
                        return v
                return v
            values = [_coerce(v) for v in values]

    base_name = field_name[:-6]
    table_name = meta_object.table_name
    if target_alias:
        source_ref = f"{target_alias}.id"
    else:
        source_ref = f"{table_name}.id"

    through, source_key = _find_m2m_assoc_for_count(meta_object, base_name)
    if not through or not source_key:
        logger.warning(
            f"[build_computed_count_filter_clause] No m2m association for {field_name!r} "
            f"(base_name={base_name!r}) in {getattr(meta_object, 'id', '?')}"
        )
        return None, []

    subquery = (
        f"(SELECT COUNT(*) FROM {through} "
        f"WHERE {source_key} = {source_ref})"
    )

    if operator in ('IN', 'NOT IN'):
        if not values:
            return None, []
        placeholders = ', '.join(['?'] * len(values))
        return f"{subquery} {operator} ({placeholders})", list(values)
    return f"{subquery} {operator} ?", list(values)


def build_computed_count_order_clause(meta_object, field_name: str, is_desc: bool,
                                       target_alias: str = ''):
    """为 computed *_count 字段构造排序子句。

    Returns:
        完整排序子句（如 "(SELECT COUNT(*) FROM through WHERE ...) DESC"），
        不匹配时返回 None。
    """
    if not _is_computed_count_field(meta_object, field_name):
        return None

    base_name = field_name[:-6]
    table_name = meta_object.table_name
    if target_alias:
        source_ref = f"{target_alias}.id"
    else:
        source_ref = f"{table_name}.id"

    through, source_key = _find_m2m_assoc_for_count(meta_object, base_name)
    if not through or not source_key:
        return None

    direction = 'DESC' if is_desc else 'ASC'
    return (
        f"(SELECT COUNT(*) FROM {through} "
        f"WHERE {source_key} = {source_ref}) {direction}"
    )
