# -*- coding: utf-8 -*-
"""规则键（rule_key）唯一生成与解析入口（spec §13.2 / F-13-04）。

规则键格式全平台只在此处定义：

    {source}:{natural_key}

目录、试算、推导、配置发布审计必须 import 本模块，禁止自行拼接前缀。
来源枚举与 ``rule_type`` 白名单同样以本模块为唯一事实源。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple

from meta.core.models_enums import RuleType

# 来源枚举（视图元数据 sources 必须与此处双向等值，见 spec §13.4）
RULE_SOURCES = (
    'bo_yaml', 'doc_flow', 'approval', 'control_parameter',
    'line_type', 'state_machine', 'numbering', 'validation',
)

# 暂无统一只读入口的来源：目录如实标记，不编造空结果冒充「已覆盖」。
NOT_INSTRUMENTED_SOURCES = ('state_machine', 'numbering')

# rule_type 白名单 = RuleType 8 值 + 已登记来源派生值
DERIVED_RULE_TYPES = ('control_parameter', 'line_type_assignment', 'doc_flow', 'approval')
RULE_TYPES = tuple(item.value for item in RuleType) + DERIVED_RULE_TYPES

# 因子轴唯一声明（spec §13.1 / F-13-12）：推导、试算、控制参数、视图元数据共用。
DIMENSION_FIELDS = (
    'org_id', 'document_type_id', 'line_type_id', 'item_group_id',
)
# 控制参数的四个因子维度（发布审计键同源，保留别名避免重复声明）
CONTROL_PARAMETER_DIM_FIELDS = DIMENSION_FIELDS


def _natural(value: Any) -> str:
    """维度取值 → 键片段；空维度统一写 ``*``，不写 ``None`` / 空串。"""
    return '*' if value is None or value == '' else str(value)


def bo_yaml_key(bo_id: str, rule_id: str) -> str:
    return f'bo_yaml:{bo_id}.{rule_id}'


def control_parameter_key(code: str) -> str:
    return f'control_parameter:{code}'


def control_parameter_codes_key(codes: Iterable[str]) -> str:
    return 'control_parameter:' + ','.join(str(code) for code in codes)


def line_type_key(document_type_id: Any, item_group_id: Any = None) -> str:
    return f'line_type:{_natural(document_type_id)}.{_natural(item_group_id)}'


def doc_flow_key(rule_id: Any) -> str:
    return f'doc_flow:{rule_id}'


def approval_key(bo_id: Any) -> str:
    return f'approval:{bo_id}'


def split_key(rule_key: Optional[str]) -> Optional[Tuple[str, str]]:
    """拆成 ``(source, natural_key)``；前缀未知返回 None，不猜。"""
    source, sep, natural = str(rule_key or '').partition(':')
    if not sep or source not in RULE_SOURCES:
        return None
    return source, natural


def control_parameter_value_key(code: str, row: Dict[str, Any]) -> str:
    """发布审计键的天然部分：``{code}|{org}|{doc_type}|{line_type}|{item_group}``。"""
    dims = '|'.join(_natural(row.get(field)) for field in CONTROL_PARAMETER_DIM_FIELDS)
    return f'{code}|{dims}'


def line_type_assignment_key(document_type_id: Any, item_group_id: Any = None) -> str:
    """行类型发布审计键的天然部分：``{doc_type}.{item_group}``。"""
    return f'{_natural(document_type_id)}.{_natural(item_group_id)}'