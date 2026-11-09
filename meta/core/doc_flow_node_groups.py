# -*- coding: utf-8 -*-
"""单据节点组只读派生（FR-013 / M4）。

单一事实约束：
  · 父子关系只来自 BO YAML 元数据（``ui_view_config.child_sections`` /
    ``hierarchy.parent_field`` / 字段 ``ui.relation``）。
  · 边只来自 ``doc_flow_rule``（唯一规则载体）。

本模块只做 join，不落库、不缓存、不参与下推与边写入；输出供规则目录与
trace 以 ``detail.node_group`` 增量附加。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROLE_HEADER = 'header'
ROLE_LINE = 'line'
ROLE_SCHEDULE = 'schedule'
ROLES = (ROLE_HEADER, ROLE_LINE, ROLE_SCHEDULE)

REASON_PARENT_FK_UNRESOLVED = 'parent_fk_unresolved'
REASON_MISSING_BO = 'missing_bo'
REASON_AMBIGUOUS = 'group_ambiguous'


def _section_field(section: Any, key: str) -> str:
    if isinstance(section, dict):
        return str(section.get(key) or '')
    return str(getattr(section, key, '') or '')


def _child_sections(meta_obj: Any) -> List[Any]:
    config = getattr(meta_obj, 'ui_view_config', None)
    sections = getattr(config, 'child_sections', None) or []
    return [s for s in sections if _section_field(s, 'child_object')]


def _child_ids(meta_obj: Any) -> List[str]:
    return [_section_field(section, 'child_object')
            for section in _child_sections(meta_obj)]


def _first_ui_relation(meta_obj: Any) -> str:
    """子 BO 的首个 ui.relation，即主父关系（字段顺序）。"""
    for field in getattr(meta_obj, 'fields', None) or []:
        relation = getattr(getattr(field, 'ui', None), 'relation', '')
        if relation:
            return str(relation)
    return ''


def _field_id(meta_obj: Any, name: str) -> str:
    """按字段 id 或 db_column 命中，返回规范字段 id。"""
    if not name:
        return ''
    for field in getattr(meta_obj, 'fields', None) or []:
        if getattr(field, 'id', '') == name or getattr(field, 'db_column', '') == name:
            return str(getattr(field, 'id', '') or name)
    return ''


def _resolve_parent_fk(child_meta: Any, header_bo: str) -> str:
    """父键解析：显式 hierarchy → ui.relation → <header>_id 命名兜底。"""
    hierarchy = getattr(child_meta, 'hierarchy', None) or {}
    if isinstance(hierarchy, dict):
        declared = str(hierarchy.get('parent_field') or '')
        resolved = _field_id(child_meta, declared)
        if resolved:
            return resolved

    for field in getattr(child_meta, 'fields', None) or []:
        ui = getattr(field, 'ui', None)
        if getattr(ui, 'relation', '') == header_bo:
            return str(getattr(field, 'id', '') or '')

    return _field_id(child_meta, f'{header_bo}_id')


def _node_role(child_bo: str, section: Any) -> str:
    declared = _section_field(section, 'role')
    if declared in ROLES:
        return declared
    if child_bo.endswith('_schedule'):
        return ROLE_SCHEDULE
    return ROLE_LINE


def _rule_view(rule: Dict[str, Any], source_group: str,
               target_group: str) -> Dict[str, Any]:
    return {
        'rule_id': rule.get('rule_id'),
        'source_bo': rule.get('source_bo'),
        'target_bo': rule.get('target_bo'),
        'source_group': source_group,
        'target_group': target_group,
    }


def _active_rules(rules: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rules
            if str(r.get('status') or 'active') == 'active']


def _owner_header(child_bo: str, registry_all: Dict[str, Any],
                  header_ids: Iterable[str]) -> str:
    """确定子 BO 的唯一归属组，避免 360 视图（project）抢走真实父组。"""
    child_meta = registry_all.get(child_bo)
    if child_meta is None:
        return ''
    header_set = set(header_ids)

    relation = _first_ui_relation(child_meta)
    if relation in header_set:
        return relation

    candidates = sorted(
        header for header in header_set
        if child_bo in _child_ids(registry_all[header])
    )
    if len(candidates) == 1:
        return candidates[0]
    return candidates[0] if candidates else ''


def build_node_groups(
    rules: Iterable[Dict[str, Any]],
    registry_all: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """从 BO 元数据 + doc_flow 规则派生节点组。

    Args:
        rules: ``list_doc_flow_rules`` 口径的规则字典。
        registry_all: ``registry.get_all()``；缺省时内部读取。

    Returns:
        ``{group_id: group}``，按 group_id 排序；group 字段顺序固定。
    """
    if registry_all is None:
        from meta.core.models import registry
        registry_all = registry.get_all() or {}

    active = _active_rules(list(rules or []))
    touched = set()
    for rule in active:
        for key in ('source_bo', 'target_bo'):
            value = str(rule.get(key) or '')
            if value:
                touched.add(value)

    headers: Dict[str, Any] = {}
    for bo_id in sorted(registry_all):
        sections = _child_sections(registry_all[bo_id])
        if not sections:
            continue
        node_ids = {bo_id} | {_section_field(s, 'child_object') for s in sections}
        if node_ids & touched:
            headers[bo_id] = sections

    # 归属先于建组：一个子 BO 只能属于一个组（360 视图不算父组）。
    owner = {}
    for header_bo, sections in headers.items():
        for section in sections:
            child_bo = _section_field(section, 'child_object')
            if child_bo not in owner:
                owner[child_bo] = _owner_header(child_bo, registry_all, headers)

    groups: Dict[str, Dict[str, Any]] = {}
    for header_bo in sorted(headers):
        group: Dict[str, Any] = {
            'group_id': header_bo,
            'header_bo': header_bo,
            'nodes': [{'bo': header_bo, 'role': ROLE_HEADER, 'parent_fk': ''}],
            'subflows': [],
            'outbound': [],
            'inbound': [],
            'degraded': False,
            'reasons': [],
            'unmodeled_bo': [],
        }
        seen = {header_bo}
        for section in headers[header_bo]:
            child_bo = _section_field(section, 'child_object')
            if child_bo in seen:
                continue
            child_meta = registry_all.get(child_bo)
            if child_meta is None:
                group['degraded'] = True
                group['reasons'].append(f'{REASON_MISSING_BO}:{child_bo}')
                continue
            # 子 BO 自身也是候选头时，以 subflow 表达，避免同一 BO 双身份重复。
            if child_bo in headers:
                group['subflows'].append(child_bo)
                seen.add(child_bo)
                continue
            # 只挂到主父组；其它头（如 project 360 视图）不重复挂节点。
            if owner.get(child_bo, header_bo) != header_bo:
                continue
            parent_fk = _resolve_parent_fk(child_meta, header_bo)
            if not parent_fk:
                group['degraded'] = True
                group['reasons'].append(
                    f'{REASON_PARENT_FK_UNRESOLVED}:{child_bo}')
                continue
            group['nodes'].append({
                'bo': child_bo,
                'role': _node_role(child_bo, section),
                'parent_fk': parent_fk,
            })
            seen.add(child_bo)
        groups[header_bo] = group

    bo_to_group: Dict[str, str] = {}
    # 头身份优先于 subflow，避免 sales_order 被 project 组抢走。
    for group_id in sorted(groups):
        bo_to_group.setdefault(group_id, group_id)
    for group in groups.values():
        for node in group['nodes']:
            bo_to_group.setdefault(node['bo'], group['group_id'])
    for group in groups.values():
        for subflow in group['subflows']:
            bo_to_group.setdefault(subflow, group['group_id'])

    unmodeled: Dict[str, set] = {group_id: set() for group_id in groups}
    for rule in active:
        source_bo = str(rule.get('source_bo') or '')
        target_bo = str(rule.get('target_bo') or '')
        source_group = bo_to_group.get(source_bo, '')
        target_group = bo_to_group.get(target_bo, '')
        view = _rule_view(rule, source_group, target_group)
        if source_group:
            groups[source_group]['outbound'].append(view)
        if target_group:
            groups[target_group]['inbound'].append(view)
        if source_group and target_bo and not target_group:
            unmodeled[source_group].add(target_bo)
        if target_group and source_bo and not source_group:
            unmodeled[target_group].add(source_bo)

    for group in groups.values():
        group['outbound'].sort(key=lambda item: str(item.get('rule_id') or ''))
        group['inbound'].sort(key=lambda item: str(item.get('rule_id') or ''))
        group['subflows'] = sorted(group['subflows'])
        group['unmodeled_bo'] = sorted(unmodeled[group['group_id']])
        group['reasons'] = sorted(group['reasons'])

    return {group_id: groups[group_id] for group_id in sorted(groups)}


def owner_header(bo_id: str,
                 registry_all: Optional[Dict[str, Any]] = None) -> str:
    """返回子 BO 的直属单头 BO；未建模或自身即头返回 ``''``。

    只读 BO YAML（全部 ``child_sections``），不依赖 doc_flow_rule 的 active
    状态——规则目录对 deprecated 规则也要给出稳定契约。
    """
    if not bo_id:
        return ''
    if registry_all is None:
        from meta.core.models import registry
        registry_all = registry.get_all() or {}

    meta_obj = registry_all.get(bo_id)
    # 自身即头（有 child_sections）时不算任何组的子节点，避免 360 视图抢父。
    if meta_obj is not None and _child_sections(meta_obj):
        return ''

    headers = sorted(
        header for header, header_meta in registry_all.items()
        if header != bo_id and bo_id in _child_ids(header_meta)
    )
    if not headers:
        return ''
    relation = _first_ui_relation(meta_obj)
    if relation in headers:
        return relation
    return headers[0]


def group_for_bo(groups: Dict[str, Dict[str, Any]],
                 bo_id: str) -> Tuple[str, str]:
    """返回 ``(group_id, role)``；未建模返回 ``('', '')``。"""
    for group_id, group in groups.items():
        if group.get('header_bo') == bo_id:
            return group_id, ROLE_HEADER
        for node in group.get('nodes') or []:
            if node.get('bo') == bo_id:
                return group_id, str(node.get('role') or '')
    return '', ''


def node_group_detail(groups: Dict[str, Dict[str, Any]],
                      bo_id: str) -> Optional[Dict[str, Any]]:
    """把 BO 所属节点组转成 ``detail.node_group`` 的稳定视图。"""
    group_id, role = group_for_bo(groups, bo_id)
    if not group_id:
        return None
    group = groups[group_id]
    return {
        'group_id': group_id,
        'node_role': role,
        'header_bo': group.get('header_bo'),
        'nodes': group.get('nodes') or [],
        'subflows': group.get('subflows') or [],
        'outbound': group.get('outbound') or [],
        'inbound': group.get('inbound') or [],
        'degraded': bool(group.get('degraded')),
        'reasons': group.get('reasons') or [],
        'unmodeled_bo': group.get('unmodeled_bo') or [],
    }
