# -*- coding: utf-8 -*-
"""统一规则解释 / dry-run 门面（FR-011）。

覆盖四类场景：
    - default          默认值（复用既有 ActionExecutor.dry_run_defaults）
    - permission       权限拒绝 / 放行（复用 PermissionExplainer）
    - state_transition 状态流转允许 / 拒绝（复用 state_machine_loader 声明）
    - approval         审批命中 / 未命中（复用 DocumentApprovalResolver）

约束：
    - 解释过程只读，不落库、不改变数据；
    - 统一返回信封固定 8 个字段，调用方无需感知底层载体差异。
"""

import time
from typing import Any, Dict, Optional

from meta.core.models import registry
from meta.core.state_machine_loader import get_state_machine

SCENARIOS = ('default', 'permission', 'state_transition', 'approval')


def _envelope(scenario: str, decision: str, *, rule_id: Optional[str] = None,
              source: str = 'code', reason: str = '',
              factors: Optional[Dict[str, Any]] = None,
              detail: Optional[Dict[str, Any]] = None,
              elapsed_ms: float = 0.0, ok: bool = True) -> Dict[str, Any]:
    envelope = {
        'ok': ok,
        'scenario': scenario,
        'decision': decision,
        'rule_id': rule_id,
        'source': source,
        'reason': reason,
        'factors': factors or {},
        'elapsed_ms': round(elapsed_ms, 3),
    }
    if detail is not None:
        envelope['detail'] = detail
    return envelope


def _default_data_source():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=str(get_meta_db_path()))


def _explain_default(meta_obj, data, data_source) -> Dict[str, Any]:
    from meta.core.rule_executor import RuleEngine
    from meta.core.action_executor import ActionExecutor

    ds = data_source or _default_data_source()
    executor = ActionExecutor(ds, RuleEngine(ds))
    result = executor.dry_run_defaults(meta_obj, dict(data or {}))
    logs = result.get('logs') or []

    def _status(entry: Dict[str, Any]) -> str:
        if (entry.get('hit') and entry.get('value') is not None
                and not entry.get('skip_reason')):
            return 'applied'
        if entry.get('skip_reason'):
            return 'skipped'
        return 'not_matched'

    # [v1.8 2026-11-07] 全部参与评估的规则都要露出（原实现只给 winner，
    # 其余只躺在 factors.logs 里，等于看不到"为什么别的规则没生效"）。
    rules = [
        {
            'rule_id': entry.get('rule_id'),
            'target_field': entry.get('target_field'),
            'value': entry.get('value'),
            'status': _status(entry),
            'skip_reason': entry.get('skip_reason'),
        }
        for entry in logs
    ]
    applied = [entry for entry in logs if _status(entry) == 'applied']

    if not result.get('success', True):
        return _envelope(
            'default', 'skipped', source='yaml',
            reason=result.get('error') or 'dry_run_failed',
            factors={'target_fields': []}, detail={'rules': rules}, ok=False,
        )
    if applied:
        winner = applied[0]
        return _envelope(
            'default', 'applied', rule_id=winner.get('rule_id'), source='yaml',
            reason='first_match',
            factors={
                'target_field': winner.get('target_field'),
                'value': winner.get('value'),
                'auto_filled_fields': result.get('auto_filled_fields') or [],
                'logs': logs,
            },
            detail={'rules': rules},
        )
    skip_reason = next(
        (entry.get('skip_reason') for entry in logs if entry.get('skip_reason')),
        'no_default_matched',
    )
    return _envelope(
        'default', 'skipped', source='yaml', reason=skip_reason,
        factors={'auto_filled_fields': [], 'logs': logs},
        detail={'rules': rules},
    )


def _explain_permission(object_type: str, user_id: Optional[int],
                        action_id: str) -> Dict[str, Any]:
    from meta.core.permission_explainer import get_permission_explainer

    if user_id is None:
        raise ValueError('permission 场景必须提供 user_id')

    result = get_permission_explainer().explain(user_id, object_type, action_id)
    steps = result.get('steps') or []
    failed = next((step for step in steps if not step.get('passed')), None)
    granted = bool(result.get('granted'))
    return _envelope(
        'permission', 'granted' if granted else 'denied',
        source='db',
        reason='all_steps_passed' if granted else (
            f"step_{failed.get('step')}:{failed.get('name')}" if failed else 'denied'),
        factors={
            'user_id': user_id,
            'action_id': action_id,
            'steps': steps,
            'sql_preview': result.get('sql_preview'),
            'final_condition': result.get('final_condition'),
        },
    )


def _explain_state_transition(object_type: str, state_field: str,
                              from_state: Any, to_state: Any) -> Dict[str, Any]:
    if not from_state or not to_state:
        raise ValueError('state_transition 场景必须提供 from_state 与 to_state')

    machine = get_state_machine(object_type, state_field)
    factors = {
        'state_field': state_field,
        'from_state': from_state,
        'to_state': to_state,
    }
    if machine is None:
        factors['states'] = []
        return _envelope(
            'state_transition', 'rejected', source='yaml',
            reason='state_machine_undeclared', factors=factors,
        )

    factors['states'] = list(machine.states)
    factors['terminal'] = list(machine.terminal)
    allowed = list(machine.transitions.get(str(from_state), ()))
    factors['allowed_to_states'] = allowed

    matched_rule = next(
        (rule for rule in machine.rules
         if getattr(rule, 'to_state', None) == str(to_state)
         and str(from_state) in (getattr(rule, 'from_states', None) or [])),
        None,
    )
    rule_id = getattr(matched_rule, 'id', None) if matched_rule else None

    if str(to_state) in allowed:
        return _envelope(
            'state_transition', 'allowed', rule_id=rule_id, source='yaml',
            reason='transition_declared', factors=factors,
        )
    reason = 'terminal_state' if str(from_state) in machine.terminal else 'transition_undeclared'
    return _envelope(
        'state_transition', 'rejected', rule_id=rule_id, source='yaml',
        reason=reason, factors=factors,
    )


def _explain_approval(object_type: str, record_id: Any,
                      data_source) -> Dict[str, Any]:
    from meta.services.document_approval_service import DocumentApprovalResolver

    if record_id is None:
        raise ValueError('approval 场景必须提供 record_id')

    resolver = DocumentApprovalResolver(data_source or _default_data_source())
    result = resolver.resolve(object_type, record_id)
    required = bool(result.get('required'))
    return _envelope(
        'approval', 'matched' if required else 'not_matched',
        rule_id=result.get('policy_code') or (
            str(result['policy_id']) if result.get('policy_id') is not None else None),
        source='db',
        reason='approval_required' if required else (result.get('reason') or 'no_policy'),
        factors={
            'record_id': record_id,
            'amount': result.get('amount'),
            'policy_id': result.get('policy_id'),
            'steps': result.get('steps') or [],
            'snapshot': result.get('snapshot'),
        },
    )


def explain(object_type: str, scenario: str, *,
            data: Optional[Dict[str, Any]] = None,
            user_id: Optional[int] = None,
            action_id: str = 'read',
            record_id: Any = None,
            state_field: str = 'status',
            from_state: Any = None,
            to_state: Any = None,
            data_source: Any = None) -> Dict[str, Any]:
    """解释一次规则决策；非法入参抛 ``ValueError``（API 层转 400）。"""
    if scenario not in SCENARIOS:
        raise ValueError(f'scenario 非法: {scenario!r}')
    meta_obj = registry.get(object_type)
    if meta_obj is None:
        raise ValueError(f'object_type 未注册: {object_type!r}')

    started = time.perf_counter()
    if scenario == 'default':
        result = _explain_default(meta_obj, data, data_source)
    elif scenario == 'permission':
        result = _explain_permission(object_type, user_id, action_id)
    elif scenario == 'state_transition':
        result = _explain_state_transition(
            object_type, state_field, from_state, to_state)
    else:
        result = _explain_approval(object_type, record_id, data_source)

    result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 3)
    return result
