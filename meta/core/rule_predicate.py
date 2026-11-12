# -*- coding: utf-8 -*-
"""统一谓词求值器（spec-rule-model FR-001 / FR-002）。

条件只有一种语义：原子比较 + ``and / or / not`` 组合，求值输出结构化结果
（``passed`` + ``explain[]``），不感知 ``rule_type``，也不感知处置动作。

所有规则维度（审批策略 / 校验 / 状态守卫）必须共用本模块，禁止各自复制
比较逻辑；explain 每项固定为 ``field / op / expected / actual / passed``。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping

logger = logging.getLogger(__name__)

#: 运算符别名 → 规范名。配置侧历史写法（``=`` / ``>=``）与规范名并存。
OPERATOR_ALIASES: Dict[str, str] = {
    '=': 'eq', '==': 'eq', 'eq': 'eq',
    '!=': 'ne', '<>': 'ne', 'ne': 'ne',
    '>': 'gt', 'gt': 'gt',
    '>=': 'ge', 'ge': 'ge',
    '<': 'lt', 'lt': 'lt',
    '<=': 'le', 'le': 'le',
    'in': 'in',
    'not_in': 'not_in', 'not in': 'not_in',
    'between': 'between',
    'is_null': 'is_null', 'is null': 'is_null',
    'is_not_null': 'is_not_null', 'is not null': 'is_not_null',
    'like': 'like',
}

#: 组合节点判定：只有带 children / conditions 的字典才是组合节点，
#: 审批条件行自带的 ``logic`` / ``group_no`` 列不参与（R2 单层 AND）。
_COMPOSITE_KEYS = ('children', 'conditions')


@dataclass
class PredicateResult:
    """一次条件求值的结果；``explain`` 逐条对应叶子原子比较。"""

    passed: bool
    explain: List[Dict[str, Any]] = field(default_factory=list)


def normalize_operator(operator: Any) -> str:
    text = str(operator or '').strip().lower()
    return OPERATOR_ALIASES.get(text, text)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _num(value: Any) -> Any:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def condition_target(condition: Mapping[str, Any]) -> Any:
    """取条件期望值：value_number > value_json > value_text。"""
    if condition.get('value_number') is not None:
        return condition.get('value_number')
    raw_json = condition.get('value_json')
    if raw_json not in (None, ''):
        try:
            return json.loads(raw_json)
        except (TypeError, ValueError):
            return raw_json
    return condition.get('value_text')


def _eq(actual: Any, target: Any) -> bool:
    left_num, right_num = _num(actual), _num(target)
    if left_num is not None and right_num is not None:
        return abs(left_num - right_num) < 1e-9
    left_text, right_text = _text(actual).lower(), _text(target).lower()
    if left_text in ('true', 'false') and right_text in ('1', '0'):
        return left_text == ('true' if right_text == '1' else 'false')
    return left_text == right_text


def _as_values(target: Any) -> List[Any]:
    if isinstance(target, (list, tuple)):
        return list(target)
    return [item for item in _text(target).split(',') if item.strip()]


def _in(actual: Any, target: Any) -> bool:
    values = _as_values(target)
    actual_num = _num(actual)
    for candidate in values:
        if actual_num is not None and _num(candidate) is not None:
            if abs(actual_num - float(candidate)) < 1e-9:
                return True
        elif _text(candidate).lower() == _text(actual).lower():
            return True
    return False


def _between(actual: Any, target: Any) -> bool:
    bounds = _as_values(target)
    if len(bounds) < 2:
        return False
    low, high = _num(bounds[0]), _num(bounds[1])
    actual_num = _num(actual)
    if None in (low, high) or actual_num is None:
        return False
    return low <= actual_num <= high


def _compare(actual: Any, target: Any, operator: str) -> bool:
    left_num, right_num = _num(actual), _num(target)
    if left_num is not None and right_num is not None:
        left, right = left_num, right_num
    else:
        left, right = _text(actual), _text(target)
        if not left or not right:
            return False
    if operator == 'gte':
        return left >= right
    if operator == 'gt':
        return left > right
    if operator == 'lte':
        return left <= right
    return left < right


def _is_null(actual: Any) -> bool:
    return _blank(actual) or _text(actual).lower() == 'null'


def _like(actual: Any, target: Any) -> bool:
    pattern = _text(target)
    if not pattern or _blank(actual):
        return False
    regex = ''.join(
        '.*' if char == '%' else '.' if char == '_' else re.escape(char)
        for char in pattern)
    return re.fullmatch(regex, _text(actual), flags=re.IGNORECASE | re.DOTALL) is not None


def _match_atom(actual: Any, operator: str, target: Any) -> bool:
    if operator == 'eq':
        return _eq(actual, target)
    if operator == 'ne':
        return not _eq(actual, target)
    if operator == 'in':
        return _in(actual, target)
    if operator == 'not_in':
        return not _in(actual, target)
    if operator == 'between':
        return _between(actual, target)
    if operator in ('gt', 'ge', 'gte'):
        return _compare(actual, target, 'gt' if operator == 'gt' else 'gte')
    if operator in ('lt', 'le', 'lte'):
        return _compare(actual, target, 'lt' if operator == 'lt' else 'lte')
    if operator == 'is_null':
        return _is_null(actual)
    if operator == 'is_not_null':
        return not _is_null(actual)
    if operator == 'like':
        return _like(actual, target)
    return False


def _is_composite(node: Any) -> bool:
    return isinstance(node, Mapping) and any(key in node for key in _COMPOSITE_KEYS)


def evaluate(record: Mapping[str, Any], node: Any) -> PredicateResult:
    """求值一个条件节点（原子 / 列表 / and-or-not 组合），并返回 explain。"""
    if node is None:
        return PredicateResult(True, [])
    if isinstance(node, (list, tuple)):
        return _evaluate_group(record, node, 'and')
    if not isinstance(node, Mapping):
        logger.warning('[predicate] 非法条件节点类型 %s，按不命中处理',
                       type(node).__name__)
        return PredicateResult(False, [])

    if _is_composite(node):
        raw_children = node.get('children')
        if raw_children is None:
            raw_children = node.get('conditions')
        children = list(raw_children or [])
        logic = str(node.get('logic') or node.get('op') or 'and').strip().lower()
        if logic == 'not':
            inner = _evaluate_group(record, children, 'and')
            return PredicateResult(not inner.passed, inner.explain)
        if logic not in ('and', 'or'):
            logger.warning('[predicate] 未知组合逻辑 %s，按不命中处理', logic)
            return PredicateResult(False, [])
        return _evaluate_group(record, children, logic)

    return _evaluate_atom(record, node)


def _evaluate_group(record: Mapping[str, Any], children: Iterable[Any],
                    logic: str) -> PredicateResult:
    """组合节点：全部求值后再聚合，保证 explain 完整且顺序稳定。"""
    results = [evaluate(record, child) for child in children]
    explain: List[Dict[str, Any]] = []
    for result in results:
        explain.extend(result.explain)
    passed = all(item.passed for item in results) if logic == 'and' else \
        any(item.passed for item in results)
    return PredicateResult(passed, explain)


def _evaluate_atom(record: Mapping[str, Any],
                   condition: Mapping[str, Any]) -> PredicateResult:
    field_id = _text(condition.get('field_id', condition.get('field')))
    if not field_id:
        return PredicateResult(False, [])
    operator = normalize_operator(condition.get('operator', condition.get('op')))
    target = condition_target(condition)
    actual = record.get(field_id)
    passed = _match_atom(actual, operator, target)
    if operator not in set(OPERATOR_ALIASES.values()):
        logger.warning('[predicate] 未知条件操作符 %s（policy=%s field=%s），按不命中处理',
                       operator, condition.get('policy_id'), field_id)
    return PredicateResult(passed, [{
        'field': field_id,
        'op': operator,
        'expected': target,
        'actual': actual,
        'passed': passed,
    }])


def evaluate_conditions(record: Mapping[str, Any],
                        conditions: Iterable[Mapping[str, Any]]) -> PredicateResult:
    """审批条件行列表：单层 AND（R2），全部求值以生成完整 explain。"""
    return evaluate(record, list(conditions or []))