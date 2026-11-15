# -*- coding: utf-8 -*-
"""可打印清单（派生，不落库）。

依据: docs/specs/spec-print-platform-2026-11-15.md §4.0 / D-PR-15 / D-PR-17
清单定义::

    type_definitions(level='header', status='active')  × scope_bo
    ∩ registry 中存在、且具备 numbering 段或 doc_effect 段的 BO

为什么派生而不建注册表:
  · 手工注册必然漂移（新增 BO 忘登记 / BO 改名留死行），且 `code` 与 `bo_code` 双标识冗余；
  · 与附件平台 `resolve_allowed_targets()` 同一范式：白名单必须由元数据算出。

接入点只到 `(bo_code, header 类型)`：line 类型不单独出打印入口（D-PR-15），
主数据 BO 因无 numbering / doc_effect 段自然被排除。
"""

from typing import Any, Dict, List, Optional

#: 接入点层级：只有 header 类型是打印入口
PRINT_TYPE_LEVEL = 'header'

#: 参与派生的类型状态
PRINT_TYPE_STATUS = 'active'

#: 单据类 BO 的能力段（任一存在即可打印）
CAPABILITY_SECTIONS = ('numbering', 'doc_effect')

_data_source = None


# ------------------------------------------------------------------ datasource

def init_print_capability(data_source) -> None:
    global _data_source
    _data_source = data_source


def _ds():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_platform_data_source
        _data_source = get_platform_data_source()
    return _data_source


def _rows(cursor) -> List[Dict[str, Any]]:
    if cursor is None:
        return []
    rows = cursor.fetchall()
    cols = [d[0] for d in (cursor.description or [])]
    return [dict(zip(cols, row)) for row in rows]


# ------------------------------------------------------------------ BO 能力

def _bo_capabilities() -> Dict[str, Dict[str, Any]]:
    """BO → {bo_name, table_name, has_numbering, has_doc_effect}。

    能力判定与 `meta/tools/gen_capability_matrix.py` 同口径：段非空即具备。
    """
    from meta.core.models import registry

    result: Dict[str, Dict[str, Any]] = {}
    for bo_id, obj in registry.get_all().items():
        has_numbering = bool(getattr(obj, 'numbering', None))
        has_doc_effect = bool(getattr(obj, 'doc_effect', None))
        result[bo_id] = {
            'bo_name': getattr(obj, 'name', None) or bo_id,
            'table_name': getattr(obj, 'table_name', None),
            'has_numbering': has_numbering,
            'has_doc_effect': has_doc_effect,
        }
    return result


def _is_document_bo(cap: Dict[str, Any]) -> bool:
    return bool(cap.get('has_numbering') or cap.get('has_doc_effect'))


# ------------------------------------------------------------------ 派生清单

def list_printable_bo_types() -> List[Dict[str, Any]]:
    """全部可打印接入点，按 BO 再按类型 id 排序。

    返回项: bo_code / bo_name / table_name / type_id / type_code / type_name /
            document_category / direction / is_default_type /
            has_numbering / has_doc_effect

    `type_id` 供前端按单据的 `document_type_id` 精确匹配接入点（同一 BO
    可有多个 header 类型，见 D-PR-15）；派生口径不变。
    """
    caps = _bo_capabilities()
    rows = _rows(_ds().execute(
        'SELECT id, code, name, scope_bo, document_category, direction, '
        'is_default, number_sequence_id FROM type_definitions '
        'WHERE level = ? AND status = ? ORDER BY scope_bo, id',
        (PRINT_TYPE_LEVEL, PRINT_TYPE_STATUS)))

    result: List[Dict[str, Any]] = []
    for row in rows:
        bo_code = row.get('scope_bo')
        cap = caps.get(bo_code)
        if not cap or not _is_document_bo(cap):
            continue
        result.append({
            'bo_code': bo_code,
            'bo_name': cap['bo_name'],
            'table_name': cap['table_name'],
            'type_id': int(row['id']),
            'type_code': row.get('code') or '',
            'type_name': row.get('name') or '',
            'document_category': row.get('document_category'),
            'direction': row.get('direction'),
            'is_default_type': int(row.get('is_default') or 0),
            'has_numbering': cap['has_numbering'],
            'has_doc_effect': cap['has_doc_effect'],
        })
    return result


def printable_bo_codes() -> List[str]:
    """可打印的 BO 清单（去重，保持派生顺序）。"""
    seen: List[str] = []
    for item in list_printable_bo_types():
        if item['bo_code'] not in seen:
            seen.append(item['bo_code'])
    return seen


def printable_types(bo_code: str) -> List[Dict[str, Any]]:
    return [item for item in list_printable_bo_types()
            if item['bo_code'] == bo_code]


def is_printable(bo_code: str, type_code: Optional[str] = None) -> bool:
    """`type_code=None` 只判 BO 是否可打印；给了 type_code 则须命中该 header 类型。"""
    types = printable_types(bo_code)
    if not types:
        return False
    if type_code is None or type_code == '':
        return True
    return any(item['type_code'] == type_code for item in types)


def summary_by_bo() -> List[Dict[str, Any]]:
    """按 BO 汇总（取证用）：type_count / has_numbering / has_doc_effect。"""
    groups: Dict[str, Dict[str, Any]] = {}
    for item in list_printable_bo_types():
        group = groups.get(item['bo_code'])
        if group is None:
            group = groups[item['bo_code']] = {
                'bo_code': item['bo_code'],
                'bo_name': item['bo_name'],
                'type_count': 0,
                'has_numbering': item['has_numbering'],
                'has_doc_effect': item['has_doc_effect'],
            }
        group['type_count'] += 1
    return list(groups.values())