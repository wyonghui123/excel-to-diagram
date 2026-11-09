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
from meta.core.rule_scenarios import (
    DIMENSION_FIELDS as _SCENARIO_DIMENSION_FIELDS,
    NOT_INSTRUMENTED_SOURCES as _SCENARIO_NOT_INSTRUMENTED,
    SOURCES as _SCENARIO_SOURCES,
)

# 来源枚举（唯一声明在 meta/core/rule_scenarios.py；视图元数据必须与其双向等值）
RULE_SOURCES = _SCENARIO_SOURCES

# 暂无统一 trace 求值入口的来源：目录如实标记，不编造空结果冒充「已覆盖」。
NOT_INSTRUMENTED_SOURCES = _SCENARIO_NOT_INSTRUMENTED

# rule_type 白名单 = RuleType 8 值 + 已登记来源派生值
DERIVED_RULE_TYPES = (
    'control_parameter', 'line_type_assignment', 'doc_flow', 'approval', 'sourcing',
)
RULE_TYPES = tuple(item.value for item in RuleType) + DERIVED_RULE_TYPES

# 因子轴：场景注册表的只读并集投影（spec 2026-11-09 FR-004）
# 新代码必须按场景读取 rule_scenarios.SCENARIO_FACTOR_KEYS，本常量仅供旧代码兼容。
DIMENSION_FIELDS = _SCENARIO_DIMENSION_FIELDS
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


def sourcing_key(rule_code: Any) -> str:
    """供应来源规则的唯一身份键（目录 / trace / 详情 / 审计共用）。"""
    return f'sourcing:{rule_code}'


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