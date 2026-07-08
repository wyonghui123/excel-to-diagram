# -*- coding: utf-8 -*-
"""
[SPR-02 S-02] computed count clause 公共模块。

把以下 4 处重复实现的逻辑收敛：
  1. enrich_utils.build_computed_count_filter_clause      (110 行)
  2. enrich_utils.build_computed_count_order_clause       ( 27 行)
  3. persistence_interceptor._try_build_computed_filter   (257 行)
  4. persistence_interceptor._build_computed_count_sort_clause (152 行)

抽取的关键原语：
  - parse_operator(key)              key 后缀 → (field_name, operator)
  - normalize_values(value, op)      任意值 → 列表（IN/NOT IN 拆逗号 / LIKE 加 %）
  - coerce_for_field_type(field, op, values)  integer 字段 string → int
  - find_count_assoc(meta, base_name) 找匹配的 association (m2m / one_to_many / composition)
  - build_count_subquery(meta, base_name, target_alias='') 生成 COUNT subquery
  - apply_count_clause(subquery, op, values)  拼装完整 WHERE 子句

高阶便捷函数：
  - build_filter_clause(meta, key, value, target_alias='')  (sql, params)
  - build_order_clause(meta, field_name, is_desc, target_alias='')  '... DESC' | None
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 1. 操作符解析
# ============================================================

def parse_operator(key: str) -> Tuple[str, str]:
    """key 后缀 → (field_name, operator)。

    支持的 operator：__in / __notin / __like / __gte / __lte / __gt / __lt /
    _start / _end / 精确（无后缀）。
    """
    if key.endswith('__in'):
        return key[:-4], 'IN'
    if key.endswith('__notin'):
        return key[:-7], 'NOT IN'
    if key.endswith('__like'):
        return key[:-6], 'LIKE'
    if key.endswith('__gte'):
        return key[:-5], '>='
    if key.endswith('__lte'):
        return key[:-5], '<='
    if key.endswith('__gt'):
        return key[:-4], '>'
    if key.endswith('__lt'):
        return key[:-4], '<'
    if key.endswith('_start'):
        return key[:-6], '>='
    if key.endswith('_end'):
        return key[:-4], '<='
    return key, '='


def normalize_values(value: Any, operator: str) -> List[Any]:
    """value → list，按 operator 规范化。

    - IN / NOT IN: 字符串按 ',' 拆，列表直接包，其他单值包成 [value]
    - LIKE:        包成 [f"%{value}%"]
    - 其他:        包成 [value]
    """
    if operator in ('IN', 'NOT IN'):
        if isinstance(value, str):
            return [v.strip() for v in value.split(',') if v.strip()]
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            return list(value)
        return [value]
    if operator == 'LIKE':
        return [f"%{value}%"]
    return [value]


def coerce_for_field_type(field, operator: str, values: List[Any]) -> List[Any]:
    """integer 字段把 string 转 int（避免 SQLite type affinity 问题）。

    LIKE 不做转换。
    """
    if operator == 'LIKE' or field is None:
        return values
    field_type_attr = getattr(field, 'field_type', None)
    if field_type_attr is None:
        return values
    type_str = str(field_type_attr)
    is_integer = (
        type_str.endswith('INTEGER')
        or type_str.endswith('INT')
        or type_str in ('integer', 'int', 'bigint', 'smallint')
    )
    if not is_integer:
        return values

    def _coerce(v):
        if isinstance(v, str):
            try:
                return int(v)
            except (ValueError, TypeError):
                return v
        return v
    return [_coerce(v) for v in values]


# ============================================================
# 2. Association 匹配 + COUNT subquery
# ============================================================

@dataclass
class CountAssocInfo:
    """[SPR-02] 匹配到的 association 信息，用于构建 COUNT subquery。"""
    kind: str  # 'many_to_many' / 'one_to_many' / 'composition' / 'parent_child' / 'merged_one_to_many' / 'virtual_one_to_many'
    source_key: str  # 外键列名（在 through 表或 target 表）
    through: Optional[str] = None  # m2m 专属
    target_table: Optional[str] = None  # one_to_many / composition 专属
    target_key: Optional[str] = None  # 双向 COUNT 用（merged_one_to_many）


def _iter_associations(meta_object) -> list:
    """[SPR-02] 兼容 dict / list 两种 associations 形态。"""
    associations = getattr(meta_object, 'associations', None)
    if isinstance(associations, dict):
        return list(associations.values())
    if associations:
        return list(associations)
    return []


def _match_assoc_name(assoc_name: str, base_name: str) -> bool:
    """[SPR-02] 关联名匹配：支持复数 / 移除常见后缀 (ship/ies/es/s) / +ship。"""
    if assoc_name == base_name or assoc_name == base_name + 's':
        return True
    if re.sub(r'(ship$|ies$|es$|s$)', '', assoc_name) == base_name:
        return True
    if assoc_name == base_name + 'ship' or assoc_name == base_name + 'ship' + 's':
        return True
    return False


def _resolve_target_table(assoc, assoc_name: str) -> str:
    """[SPR-02] 推导 target_table：target_table > assoc_name 复数 > target_entity 复数。"""
    target_table = getattr(assoc, 'target_table', None)
    if target_table:
        return target_table
    pluralized = assoc_name if assoc_name.endswith('s') else assoc_name + 's'
    if pluralized:
        return pluralized
    target_entity = getattr(assoc, 'target_entity', None) or ''
    if target_entity:
        return target_entity + ('s' if not target_entity.endswith('s') else '')
    return ''


def find_count_assoc(
    meta_object, base_name: str, field_computation: Optional[dict] = None
) -> Optional[CountAssocInfo]:
    """[SPR-02] 找匹配的 association（含 m2m / one_to_many / composition / parent_child / merged_one_to_many / virtual_one_to_many）。

    匹配规则（按优先级）：
    1. assoc.name 与 base_name 匹配（见 _match_assoc_name）
    2. field.computation.child_object / target_object == assoc.target_entity
    """
    field_child_object = ''
    if field_computation:
        field_child_object = (
            field_computation.get('child_object')
            or field_computation.get('target_object')
            or ''
        )

    for assoc in _iter_associations(meta_object):
        if isinstance(assoc, str):
            # 历史格式：list of names
            assoc_name = assoc
            assoc_type = 'many_to_many'
            through = None
            source_key = None
            foreign_key_field = None
            target_table = None
            target_entity = ''
        else:
            assoc_name = getattr(assoc, 'name', '')
            assoc_type = getattr(assoc, 'type', '')
            through = getattr(assoc, 'through', None)
            source_key = getattr(assoc, 'source_key', None)
            foreign_key_field = (
                getattr(assoc, 'foreign_key_field', None) or source_key
            )
            target_entity = getattr(assoc, 'target_entity', None) or ''
            target_table = _resolve_target_table(assoc, assoc_name)

        # m2m 路径
        if assoc_type == 'many_to_many' and through and source_key:
            if not _match_assoc_name(assoc_name, base_name):
                # 检查 child_object
                if not (field_child_object and target_entity
                        and field_child_object == target_entity):
                    continue
            return CountAssocInfo(
                kind='many_to_many',
                source_key=source_key,
                through=through,
            )

        # one_to_many / composition / parent_child / merged / virtual
        if assoc_type in (
            'merged_one_to_many', 'one_to_many', 'virtual_one_to_many',
            'composition', 'parent_child',
        ) and foreign_key_field and target_table:
            if not _match_assoc_name(assoc_name, base_name):
                if not (field_child_object and target_entity
                        and field_child_object == target_entity):
                    continue
            return CountAssocInfo(
                kind=assoc_type,
                source_key=foreign_key_field,
                target_table=target_table,
                target_key=getattr(assoc, 'target_key', None) or '',
            )

    return None


def build_count_subquery(
    meta_object, base_name: str, target_alias: str = '',
    assoc_info: Optional[CountAssocInfo] = None,
) -> Optional[str]:
    """[SPR-02] 根据匹配的 association 生成 COUNT subquery。

    Args:
        meta_object: 业务对象定义
        base_name:   字段基础名（如 member_count → 'member'）
        target_alias: 源表的 SQL 别名（空串表示用 meta_object.table_name）
        assoc_info: 预解析的 assoc 信息；None 时自动 find_count_assoc

    Returns:
        subquery 字符串（如 '(SELECT COUNT(*) FROM members WHERE team_id = t.id)'）
        或 None（不匹配时）。
    """
    if assoc_info is None:
        field = None
        try:
            field = meta_object.get_field(f"{base_name}_count")
        except Exception:
            field = None
        field_computation = getattr(field, 'computation', None) if field else None
        assoc_info = find_count_assoc(meta_object, base_name, field_computation)

    if assoc_info is None:
        return None

    source_ref = f"{target_alias}.id" if target_alias else f"{meta_object.table_name}.id"

    if assoc_info.kind == 'many_to_many':
        return (
            f"(SELECT COUNT(*) FROM {assoc_info.through} "
            f"WHERE {assoc_info.through}.{assoc_info.source_key} = {source_ref})"
        )

    # one_to_many / composition / parent_child / merged / virtual
    if assoc_info.target_key and assoc_info.target_key != assoc_info.source_key:
        # 双向 COUNT (source FK = id OR target FK = id)
        return (
            f"(SELECT COUNT(*) FROM {assoc_info.target_table} "
            f"WHERE {assoc_info.target_table}.{assoc_info.source_key} = {source_ref} "
            f"OR {assoc_info.target_table}.{assoc_info.target_key} = {source_ref})"
        )
    return (
        f"(SELECT COUNT(*) FROM {assoc_info.target_table} "
        f"WHERE {assoc_info.target_table}.{assoc_info.source_key} = {source_ref})"
    )


def apply_count_clause(
    subquery: str, operator: str, values: List[Any]
) -> Tuple[str, List[Any]]:
    """[SPR-02] 把 subquery + operator 拼成完整 WHERE 子句。

    - IN / NOT IN: 生成 'subquery OP (?, ?, ...)' + params
    - 其他:       'subquery OP ?' + [value]
    """
    if not subquery:
        return '', list(values) if values else []
    if operator in ('IN', 'NOT IN'):
        if not values:
            return '', []
        placeholders = ', '.join(['?'] * len(values))
        return f"{subquery} {operator} ({placeholders})", list(values)
    if not values:
        return f"{subquery} {operator} ?", []
    return f"{subquery} {operator} ?", list(values)


# ============================================================
# 3. 高阶便捷函数
# ============================================================

def build_filter_clause(
    meta_object, key: str, value: Any, target_alias: str = ''
) -> Tuple[Optional[str], Optional[List[Any]]]:
    """[SPR-02] 完整 filter clause：解析 key + value，生成 (sql, params)。

    不匹配（字段非 computed、找不到 assoc 等）时返回 (None, None)。
    """
    if not meta_object or not key:
        return None, None

    field_name, operator = parse_operator(key)
    try:
        field = meta_object.get_field(field_name)
    except Exception:
        field = None
    if field is None or not getattr(field, 'computed', False):
        return None, None
    if not field_name.endswith('_count'):
        return None, None

    values = normalize_values(value, operator)
    values = coerce_for_field_type(field, operator, values)
    base_name = field_name[:-6]

    field_computation = getattr(field, 'computation', None) or {}
    assoc_info = find_count_assoc(meta_object, base_name, field_computation)
    if assoc_info is None:
        logger.warning(
            f"[build_filter_clause] No count association for {field_name!r} "
            f"(base_name={base_name!r}) in {getattr(meta_object, 'id', '?')}"
        )
        return None, None

    subquery = build_count_subquery(
        meta_object, base_name, target_alias=target_alias, assoc_info=assoc_info
    )
    if subquery is None:
        return None, None

    clause, params = apply_count_clause(subquery, operator, values)
    return clause, params


def build_order_clause(
    meta_object, field_name: str, is_desc: bool, target_alias: str = ''
) -> Optional[str]:
    """[SPR-02] 完整 sort clause：'(SELECT COUNT(*) FROM ...) DESC' 或 None。"""
    if not meta_object or not field_name:
        return None
    try:
        field = meta_object.get_field(field_name)
    except Exception:
        field = None
    if field is None or not getattr(field, 'computed', False):
        return None
    if not field_name.endswith('_count'):
        return None

    base_name = field_name[:-6]
    field_computation = getattr(field, 'computation', None) or {}
    assoc_info = find_count_assoc(meta_object, base_name, field_computation)
    if assoc_info is None:
        return None

    subquery = build_count_subquery(
        meta_object, base_name, target_alias=target_alias, assoc_info=assoc_info
    )
    if subquery is None:
        return None
    direction = 'DESC' if is_desc else 'ASC'
    return f"{subquery} {direction}"
