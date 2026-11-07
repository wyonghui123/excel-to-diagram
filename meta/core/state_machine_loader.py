# -*- coding: utf-8 -*-
"""状态机声明加载（Rule Convergence M2 / FR-004）

唯一真源 = 各 BO YAML 的
  · 顶层 ``states`` 目录（code / category / seq）
  · ``rules`` 中 ``type: state_transition`` 的迁移边（state_field / from_states / to_state）

本模块只负责「把声明解析成有序状态图」，不执行副作用、不写库。
registry 已加载时读 MetaObject；未加载（脚本 / 单测）时直接读同名 schema 文件，
与 ``document_number_service._read_numbering`` 保持同一口径。

口径:
  · ``transitions`` 按规则出现顺序构建（不排序），保证与旧常量逐项相等；
  · ``states`` 以 states 目录顺序为准，缺失目录时按规则出现序；
  · ``terminal`` 取 states 目录中 ``category: terminal``；无目录时取无出边状态；
  · 未声明任何迁移规则 → 返回 None（调用方按 fail-open 处理）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from meta.core import yaml_compat as yaml

logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')

_cache: Dict[Tuple[str, str], Optional['StateMachine']] = {}


@dataclass(frozen=True)
class StateMachine:
    """解析后的状态图（只读）。"""

    object_type: str
    state_field: str
    states: Tuple[str, ...]
    transitions: Dict[str, Tuple[str, ...]]
    terminal: Tuple[str, ...]
    rules: Tuple[Any, ...]

    def allowed(self, from_state: Any) -> Tuple[str, ...]:
        """返回当前状态允许的目标状态（未知状态返回空元组）。"""
        return self.transitions.get(str(from_state), ())

    def can_transition(self, from_state: Any, to_state: Any) -> bool:
        return str(to_state) in self.allowed(from_state)


def _declaration(object_type: str, state_field: str):
    """返回 (rules, state_codes, terminal_codes)；对象未注册且无 schema 时 None。"""
    from meta.core.models import registry

    meta_obj = registry.get(object_type)
    if meta_obj is not None:
        from meta.core.models_enums import RuleType
        from meta.core.rule_provider import get_rule_provider

        rules = [
            rule for rule in get_rule_provider().get_rules_by_type(
                meta_obj, RuleType.STATE_TRANSITION)
            if getattr(rule, 'state_field', '') == state_field
        ]
        catalog = list(getattr(meta_obj, 'states', None) or [])
        state_codes = [str(getattr(item, 'code', '') or '') for item in catalog]
        terminal_codes = [
            str(getattr(item, 'code', '') or '') for item in catalog
            if getattr(item, 'category', '') == 'terminal'
        ]
        return rules, state_codes, terminal_codes

    path = os.path.join(_SCHEMA_DIR, '%s.yaml' % object_type)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:  # noqa: BLE001 - 读取失败按未声明处理
        logger.warning('[state_machine] 读取 %s 失败: %s', path, exc)
        return None

    from meta.core.yaml_loader import parse_state_transition

    rules = [
        parse_state_transition(raw)
        for raw in (data.get('rules') or [])
        if str(raw.get('type') or raw.get('rule_type') or '').lower()
        == 'state_transition'
        and str(raw.get('state_field') or '') == state_field
    ]
    catalog = [raw for raw in (data.get('states') or []) if isinstance(raw, dict)]
    state_codes = [str(raw.get('code') or '') for raw in catalog]
    terminal_codes = [
        str(raw.get('code') or '') for raw in catalog
        if raw.get('category') == 'terminal'
    ]
    return rules, state_codes, terminal_codes


def _build(object_type: str, state_field: str,
           rules: List[Any], state_codes: List[str],
           terminal_codes: List[str]) -> StateMachine:
    order: List[str] = []
    transitions: Dict[str, List[str]] = {}

    def _remember(code: str) -> None:
        if code and code not in order:
            order.append(code)

    for code in state_codes:
        _remember(code)

    for rule in rules:
        to_state = str(getattr(rule, 'to_state', '') or '')
        _remember(to_state)
        for from_state in (getattr(rule, 'from_states', None) or []):
            code = str(from_state)
            _remember(code)
            bucket = transitions.setdefault(code, [])
            if to_state and to_state not in bucket:
                bucket.append(to_state)

    for code in order:
        transitions.setdefault(code, [])

    declared_terminal = tuple(
        code for code in terminal_codes if code in transitions)
    if terminal_codes:
        terminal = declared_terminal
    else:
        terminal = tuple(
            code for code in order if not transitions.get(code))

    return StateMachine(
        object_type=object_type,
        state_field=state_field,
        states=tuple(order),
        transitions={key: tuple(value) for key, value in transitions.items()},
        terminal=terminal,
        rules=tuple(rules),
    )


def get_state_machine(object_type: str,
                      state_field: str = 'status') -> Optional[StateMachine]:
    """读取对象的状态机声明；未声明返回 None（调用方 fail-open）。"""
    key = (object_type, state_field)
    if key in _cache:
        return _cache[key]

    declaration = _declaration(object_type, state_field)
    if declaration is None:
        _cache[key] = None
        return None

    rules, state_codes, terminal_codes = declaration
    if not rules:
        _cache[key] = None
        return None

    machine = _build(object_type, state_field, rules, state_codes, terminal_codes)
    _cache[key] = machine
    return machine


def reload() -> None:
    """清空进程内缓存（测试 / 热加载用）。"""
    _cache.clear()
