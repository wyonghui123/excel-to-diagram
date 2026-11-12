# -*- coding: utf-8 -*-
"""单据头契约只读派生（TBD-007 P0 / spec §9.3.11）。

单一事实约束：
  · 头/行归属只来自 BO YAML（``ui_view_config.child_sections`` / 字段
    ``ui.relation``），复用 :func:`doc_flow_node_groups.owner_header`。
  · ``required_missing`` 只来自目标头 YAML 的 required 存储字段，减去规则
    ``split_key`` 经 ``field_map`` 映射后的目标字段；主键、审计列、有 default
    的字段由框架/默认值填充，不计入契约缺口。

本模块只做 join，不落库、不缓存、不参与建头/下推与边写入；输出供规则目录以
``detail.header_contract`` 增量附加。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from meta.core.doc_flow_node_groups import REASON_MISSING_BO, owner_header
from meta.core.models_enums import FieldStorage

MODE_FLAT = 'flat'
MODE_RULE_HEADED = 'rule_headed'
MODE_SERVICE_HEADED = 'service_headed'

REASON_HEADER_FIELD_UNCOVERED = 'header_field_uncovered'

#: 框架自动填充 / 审计列，不参与头字段契约。
_AUTO_FIELD_IDS = ('id', 'created_at', 'updated_at')


def _field_id(field: Any) -> str:
    return str(getattr(field, 'id', '') or '')


def _fields(head_meta: Any) -> List[Any]:
    return list(getattr(head_meta, 'fields', None) or [])


def _resolve_field_id(head_meta: Any, name: str) -> str:
    """按字段 id 或 db_column 命中，返回规范字段 id。"""
    if not name:
        return ''
    for field in _fields(head_meta):
        if _field_id(field) == name or getattr(field, 'db_column', '') == name:
            return _field_id(field)
    return ''


def _is_stored(field: Any) -> bool:
    storage = getattr(field, 'storage', FieldStorage.STORED)
    return getattr(storage, 'value', storage) == FieldStorage.STORED.value


def _required_head_fields(head_meta: Any) -> List[str]:
    """目标头 required 且无 default 的存储字段（排除主键与审计列）。"""
    required: List[str] = []
    for field in _fields(head_meta):
        fid = _field_id(field)
        if not fid or fid in _AUTO_FIELD_IDS:
            continue
        if not getattr(field, 'required', False):
            continue
        if getattr(field, 'default', None) is not None:
            continue
        if not _is_stored(field):
            continue
        required.append(fid)
    return required


def _split_key_targets(rule: Dict[str, Any], head_meta: Any) -> List[str]:
    """split_key 经 field_map 改名后落在目标头上的字段 id。"""
    field_map = rule.get('field_map') or {}
    targets: List[str] = []
    for source_field in rule.get('split_key') or []:
        raw = str(field_map.get(source_field, source_field) or '')
        target = _resolve_field_id(head_meta, raw)
        if target and target not in targets:
            targets.append(target)
    return targets


def build_header_contract(
    rule: Dict[str, Any],
    registry_all: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """把一条 doc_flow_rule 转成 ``detail.header_contract`` 稳定视图。

    Args:
        rule: ``list_doc_flow_rules`` 口径的规则字典。
        registry_all: ``registry.get_all()``；缺省时内部读取。

    Returns:
        ``mode`` / ``head_bo`` / ``split_key`` / ``required_missing`` /
        ``service_owned_fields`` / ``degraded`` / ``reasons``。
    """
    rule = rule or {}
    if registry_all is None:
        from meta.core.models import registry
        registry_all = registry.get_all() or {}

    target_bo = str(rule.get('target_bo') or '')
    result: Dict[str, Any] = {
        'mode': MODE_FLAT,
        'head_bo': '',
        'split_key': [str(item) for item in (rule.get('split_key') or [])],
        'required_missing': [],
        'service_owned_fields': [],
        'degraded': False,
        'reasons': [],
    }
    if not target_bo or target_bo not in registry_all:
        result['degraded'] = True
        result['reasons'] = [REASON_MISSING_BO]
        return result

    line_bo = str(rule.get('target_line_bo') or '')
    if line_bo:
        # 两级模式：规则自己建头（head_overrides 运行时 > split_key 映射）。
        mode, head_bo = MODE_RULE_HEADED, target_bo
    else:
        head = owner_header(target_bo, registry_all)
        mode, head_bo = (MODE_SERVICE_HEADED, head) if head else (MODE_FLAT, '')

    result['mode'] = mode
    result['head_bo'] = head_bo
    if not head_bo:
        return result

    head_meta = registry_all.get(head_bo)
    if head_meta is None:
        result['degraded'] = True
        result['reasons'] = [REASON_MISSING_BO]
        return result

    covered = _split_key_targets(rule, head_meta)
    missing = [fid for fid in _required_head_fields(head_meta)
               if fid not in covered]
    result['required_missing'] = missing
    if mode == MODE_SERVICE_HEADED:
        # 服务建头：缺失字段即业务服务必须写入的最小集合（仅提示，不阻断）。
        result['service_owned_fields'] = list(missing)
    elif mode == MODE_RULE_HEADED and missing:
        result['degraded'] = True
        result['reasons'] = [REASON_HEADER_FIELD_UNCOVERED]
    return result
