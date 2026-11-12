# -*- coding: utf-8 -*-
"""可编辑规则目标的唯一声明（spec §13.1 / F-13-05）。

来源适配器通过 ``links_for`` 下发 ``RuleDescriptor.links``；
配置发布服务通过 ``RULE_TARGETS`` 取得写入所需的表 / 字段契约。
前端不得再维护 ``source → 目标表`` 映射。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

RULE_TARGETS: Dict[str, Dict[str, Any]] = {
    'control_parameter_value': {
        'source': 'control_parameter',
        'table': 'control_parameter_values',
        'label': '控制参数取值',
        'key_fields': ('control_parameter_id', 'org_id', 'document_type_id',
                       'line_type_id', 'item_group_id'),
        'value_fields': ('specificity_rank', 'value', 'description'),
        'required': ('control_parameter_id', 'value'),
    },
    'line_type_assignment': {
        'source': 'line_type',
        'table': 'line_type_assignments',
        'label': '行类型确定规则',
        'key_fields': ('document_type_id', 'item_group_id'),
        'value_fields': ('specificity_rank', 'line_type_id', 'description'),
        'required': ('document_type_id', 'line_type_id'),
    },
}


def target_for_source(source: str) -> Optional[str]:
    for target, spec in RULE_TARGETS.items():
        if spec.get('source') == source:
            return target
    return None


def links_for(source: str,
              status: str = 'active') -> Optional[Dict[str, Dict[str, str]]]:
    """可编辑来源：``edit`` 恒下发；草稿态额外下发 ``publish`` / ``rollback``。"""
    target = target_for_source(source)
    if not target:
        return None
    links = {'edit': {'target': target}}
    if status == 'draft':
        links['publish'] = {'target': target}
        links['rollback'] = {'target': target}
    return links