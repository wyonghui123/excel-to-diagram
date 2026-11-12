# -*- coding: utf-8 -*-
"""命中策略与排序契约（FR-006）

规则集命中多条时的处理方式必须显式声明，不得依赖 SQL ``ORDER BY``
的隐式语义：

- ``first``  ：按 :data:`ORDER_BY` 取首条（运行期默认）
- ``all``    ：全部返回，由调用方自行聚合
- ``unique`` ：仅用于建模期静态检查；命中多条即「规则重叠」，
  由 :func:`meta.core.rule_declaration_validator.validate_hit_policies`
  在加载期报错，不进入运行期。

``ORDER_BY = [priority DESC, effective_from DESC, id DESC]`` 与现状等价；
SQL 与 Python 两侧共用同一常量，避免两处排序口径漂移。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple

HIT_POLICIES = ('first', 'all', 'unique')
DEFAULT_HIT_POLICY = 'first'
ORDER_BY = ('priority DESC', 'effective_from DESC', 'id DESC')


def normalize_hit_policy(value: Any) -> str:
    """未声明（空值）回退默认 ``first``，显式值原样返回（小写）。"""
    text = str(value or '').strip().lower()
    return text or DEFAULT_HIT_POLICY


def validate_hit_policy(value: Any) -> Optional[str]:
    """校验 ``hit_policy`` 是否落在封闭词表内。

    未声明（空值）视为默认 ``first``，不报错。
    """
    text = str(value or '').strip().lower()
    if not text:
        return None
    if text not in HIT_POLICIES:
        return 'hit_policy %r 不在封闭词表 %s 内' % (text, list(HIT_POLICIES))
    return None


def order_by_sql(alias: str = '') -> str:
    """把 :data:`ORDER_BY` 渲染成可直接拼接的 SQL 片段。"""
    prefix = (alias + '.') if alias else ''
    parts = []
    for item in ORDER_BY:
        column, _, direction = item.partition(' ')
        parts.append('%s%s %s' % (prefix, column, direction))
    return ', '.join(parts)


def _int_value(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value or '').strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(
            tzinfo=None)
    except ValueError:
        return datetime.min


def sort_key(rule: Dict[str, Any]) -> Tuple[int, datetime, int]:
    """按 :data:`ORDER_BY` 生成的 Python 排序键（配合 ``reverse=True``）。"""
    return (
        _int_value(rule.get('priority')),
        _timestamp(rule.get('effective_from')),
        _int_value(rule.get('id')),
    )


def sort_rules(rules: Sequence[Dict[str, Any]]) -> list:
    """按 :data:`ORDER_BY` 排序（priority DESC, effective_from DESC, id DESC）。"""
    return sorted(rules, key=sort_key, reverse=True)


def select(hits: Sequence[Any], hit_policy: Any = DEFAULT_HIT_POLICY) -> list:
    """按命中策略裁剪已排序的命中列表。

    ``unique`` 不参与运行期取数，调用即报错，避免被误当 ``all`` 使用。
    """
    policy = normalize_hit_policy(hit_policy)
    if policy == 'unique':
        raise ValueError(
            'hit_policy=unique 仅用于建模期静态重叠检查，不参与运行期取数')
    if policy == 'all':
        return list(hits)
    return list(hits)[:1]