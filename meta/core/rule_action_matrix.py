# -*- coding: utf-8 -*-
"""规则处置动作词表与 ``rule_type × action`` 封闭矩阵（spec-rule-model §9.5）。

全平台只在 本模块 声明：
  - 7 个处置动作词（``block / warn_ack / hold / route / notify / default / lock``）
  - 每个 ``rule_type`` 允许的动作集合（矩阵）
  - 单条规则的动作校验入口

新增动作或调整组合只改这里；配置加载与保存校验必须 import 本模块，
禁止在别处复制词表或矩阵。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional

from meta.core.models_enums import RuleType

BLOCK = 'block'
WARN_ACK = 'warn_ack'
HOLD = 'hold'
ROUTE = 'route'
NOTIFY = 'notify'
DEFAULT = 'default'
LOCK = 'lock'

#: 处置动作封闭词表（顺序即报错文案中的列举顺序）
RULE_ACTIONS = (BLOCK, WARN_ACK, HOLD, ROUTE, NOTIFY, DEFAULT, LOCK)

#: 审批策略是独立来源（``rule_keys.approval_key``），不在 RuleType 枚举内，
#: 但同样受矩阵约束。
APPROVAL_RULE_TYPE = 'approval'

#: ``rule_type → 允许的处置动作``；未登记的类型一律不允许任何动作。
RULE_ACTION_MATRIX: Dict[str, FrozenSet[str]] = {
    RuleType.VALIDATION.value: frozenset({BLOCK, WARN_ACK, HOLD, NOTIFY}),
    RuleType.CONSTRAINT.value: frozenset({BLOCK, HOLD, NOTIFY}),
    RuleType.STATE_TRANSITION.value: frozenset({BLOCK, HOLD, ROUTE, NOTIFY}),
    RuleType.PERMISSION.value: frozenset({BLOCK, LOCK}),
    RuleType.DEFAULT.value: frozenset({NOTIFY, DEFAULT}),
    RuleType.COMPUTATION.value: frozenset({DEFAULT}),
    # derivation 是「计算」不是「处置」：由其他层引用其产出，不直接作用于操作。
    RuleType.DERIVATION.value: frozenset(),
    RuleType.TRIGGER.value: frozenset({ROUTE, NOTIFY, DEFAULT}),
    APPROVAL_RULE_TYPE: frozenset({HOLD, ROUTE, NOTIFY}),
}


def _rule_type_value(rule_type) -> str:
    """接受 ``RuleType`` 枚举或字符串，统一成小写字面量。"""
    value = getattr(rule_type, 'value', rule_type)
    return str(value or '').strip().lower()


def allowed_actions(rule_type) -> FrozenSet[str]:
    """返回该 ``rule_type`` 允许的动作集合；未登记类型返回空集。"""
    return RULE_ACTION_MATRIX.get(_rule_type_value(rule_type), frozenset())


def validate_action(rule_type, action) -> Optional[str]:
    """校验 ``rule_type × action``。

    返回 ``None`` 表示合法（``action`` 未声明时同样合法，M1 不强制必填）；
    否则返回可直接拼进错误信息的原因文本。
    """
    action = str(action or '').strip().lower()
    if not action:
        return None
    if action not in RULE_ACTIONS:
        return '动作 %r 不在词表 %s' % (action, ' / '.join(RULE_ACTIONS))
    allowed = allowed_actions(rule_type)
    if action not in allowed:
        return 'rule_type %r 不允许动作 %r（允许：%s）' % (
            _rule_type_value(rule_type), action,
            ' / '.join(sorted(allowed)) if allowed else '无')
    return None