# -*- coding: utf-8 -*-
"""规则处置动作分发器（spec-rule-model §12.4 / M7-3）。

契约：
  ① 运行期按 ``decision.action`` 分派的唯一入口；7 个处理器构成**封闭注册表**
    （``rule_action_matrix.RULE_ACTIONS``），未知动作直接抛错，禁止静默跳过。
  ② ``decision.matched=False`` 且 ``context['release_unmatched']`` 为真时，
    走 hold 释放（提交路径的 else 分支统一收敛到这里）。
  ③ holds 持久化只经 ``RuleHoldService``（本模块不手写 holds SQL）；
     审批任务复用 ``ApprovalTaskService``（tasks type='approval'）。
  ④ 处理器返回 ``dict`` 计入 ``applied``；返回 ``None`` 计入 ``skipped``
    （幂等无操作，如已在挂起 / 无通知通道 / 无默认字段）。
  ⑤ 上下文缺关键字段属调用方编程错误，抛 ``DispatchError``。

context 约定键（按需传）：
    data_source / holds           挂起与审批写入
    object_type / record_id       业务记录标识
    rule_key                      缺省取 ``decision.rule_key``
    code / reason / applied_by    hold 落库字段
    message                       block / warn_ack 文案
    fields / write_fields         default（写字段回调）/ lock（禁用字段列表）
    notify                        notify 通道回调
    release_unmatched             True = 未命中释放旧挂起
    fallback_action               未声明 disposition 时的回退动作（调用方显式声明）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from meta.core.exceptions import ValidationFailedError
from meta.core.rule_action_matrix import (
    BLOCK,
    DEFAULT,
    HOLD,
    LOCK,
    NOTIFY,
    ROUTE,
    RULE_ACTIONS,
    WARN_ACK,
)

logger = logging.getLogger(__name__)

#: 释放动作不是规则处置词（rule_action_matrix 的 7 动作）之一，
#: 只出现在「未命中」分支的结果里，用于审计与提交路径收集。
RELEASE = 'release'


class DispatchError(ValueError):
    """动作分派失败：未知动作或上下文缺字段。"""


@dataclass
class DispatchResult:
    """一次分派的结果；applied / skipped 逐条可审计。"""

    action: str = ''
    matched: bool = False
    applied: List[Dict[str, Any]] = field(default_factory=list)
    skipped: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def held(self) -> List[Dict[str, Any]]:
        return [item for item in self.applied if item.get('action') == HOLD]

    @property
    def released(self) -> List[Dict[str, Any]]:
        return [item for item in self.applied if item.get('action') == RELEASE]


def _rule_key(decision: Any, ctx: Dict[str, Any]) -> str:
    return str(ctx.get('rule_key') or getattr(decision, 'rule_key', '') or '')


def _explain(decision: Any) -> List[Dict[str, Any]]:
    """判定 explain（ConstraintDecision 等提供 explain() 时展开）。"""
    try:
        return list(decision.explain() or [])
    except (AttributeError, TypeError):
        return []


def _holds_of(ctx: Dict[str, Any]) -> Any:
    holds = ctx.get('holds')
    if holds is not None:
        return holds
    ds = ctx.get('data_source')
    if ds is None:
        raise DispatchError('缺少 holds / data_source，无法执行挂起动作')
    from meta.services.rule_hold_service import RuleHoldService
    return RuleHoldService(ds)


def _handle_block(decision: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """block：拒绝当前操作（不再落库）。"""
    key = _rule_key(decision, ctx)
    message = str(ctx.get('message') or '').strip() or (
        '规则 %s 拒绝该操作' % (key or '<unknown>'))
    raise ValidationFailedError(
        message,
        details=[{
            'rule_key': key,
            'action': BLOCK,
            'severity': str(getattr(decision, 'severity', '') or ''),
            'explain': _explain(decision),
        }])


def _handle_warn_ack(decision: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """warn_ack：放行但要求确认，同时写审计日志。"""
    key = _rule_key(decision, ctx)
    entry = {
        'action': WARN_ACK,
        'rule_key': key,
        'requires_ack': True,
        'message': str(ctx.get('message') or ''),
    }
    ds = ctx.get('data_source')
    if ds is not None:
        try:
            from meta.services.audit_service import AuditService
            AuditService(ds).log(
                object_type=str(ctx.get('object_type') or ''),
                object_id=ctx.get('record_id'),
                action='WARN_ACK',
                user_id=ctx.get('applied_by'),
                new_data={'rule_key': key, 'action': WARN_ACK,
                          'severity': str(getattr(decision, 'severity', '') or '')},
                extra_data={'rule_explain': _explain(decision)},
            )
        except Exception as exc:  # 审计失败不影响业务动作
            logger.warning('[rule_dispatcher] warn_ack 审计写入失败 key=%s: %s',
                           key, exc)
    return entry


def _require_record(ctx: Dict[str, Any], action: str) -> Any:
    record_id = ctx.get('record_id')
    if record_id in (None, ''):
        raise DispatchError('action=%s 缺少 record_id' % action)
    return record_id


def _handle_hold(decision: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """hold：可存不可过；已有同规则 active 行时视为无操作。"""
    record_id = _require_record(ctx, HOLD)
    key = _rule_key(decision, ctx)
    created = _holds_of(ctx).apply(
        str(ctx.get('object_type') or ''), record_id, key,
        code=ctx.get('code'), reason=ctx.get('reason'),
        applied_by=ctx.get('applied_by'))
    if not created:
        return None
    return {
        'action': HOLD,
        'rule_key': key,
        'record_id': record_id,
        'code': str(ctx.get('code') or ''),
        'reason': str(ctx.get('reason') or ''),
    }


def _handle_release(decision: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """未命中分支：释放该记录同规则的旧挂起。"""
    record_id = _require_record(ctx, RELEASE)
    key = _rule_key(decision, ctx)
    released = _holds_of(ctx).release(
        str(ctx.get('object_type') or ''), record_id, key,
        released_by=ctx.get('applied_by'))
    if not released:
        return None
    return {'action': RELEASE, 'rule_key': key, 'record_id': record_id,
            'released': int(released)}


def _handle_route(decision: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """route：转审批，复用 tasks(type='approval') 创建入口。"""
    from meta.services.approval_task_service import ApprovalTaskService

    ds = ctx.get('data_source')
    if ds is None:
        raise DispatchError('action=route 缺少 data_source')
    object_type = str(ctx.get('object_type') or '')
    record_id = _require_record(ctx, ROUTE)
    task_id = ApprovalTaskService(ds).create_task(
        object_type, record_id, actor=str(ctx.get('applied_by') or ''))
    if not task_id:
        return None
    return {'action': ROUTE, 'rule_key': _rule_key(decision, ctx),
            'task_id': task_id}


def _handle_notify(decision: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """notify：走调用方注入的现有消息通道。"""
    channel = ctx.get('notify')
    if not callable(channel):
        return None
    key = _rule_key(decision, ctx)
    payload = {
        'rule_key': key,
        'object_type': str(ctx.get('object_type') or ''),
        'record_id': ctx.get('record_id'),
        'message': str(ctx.get('message') or ''),
    }
    channel(payload)
    return {'action': NOTIFY, 'rule_key': key, 'channel': 'injected'}


def _handle_default(decision: Any, ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """default：按规则写默认值（写入动作由调用方以回调提供）。"""
    fields = dict(ctx.get('fields') or {})
    writer = ctx.get('write_fields')
    if not fields or not callable(writer):
        return None
    writer(fields)
    return {'action': DEFAULT, 'rule_key': _rule_key(decision, ctx),
            'fields': fields}


def _handle_lock(decision: Any, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """lock：输出禁用声明（字段锁定由调用方消费）。"""
    fields = [str(item) for item in (ctx.get('fields') or [])]
    return {'action': LOCK, 'rule_key': _rule_key(decision, ctx),
            'locked': True, 'fields': fields}


#: 封闭注册表：动作 → 处理器（唯一事实源是 rule_action_matrix.RULE_ACTIONS）
_HANDLERS = {
    BLOCK: _handle_block,
    WARN_ACK: _handle_warn_ack,
    HOLD: _handle_hold,
    ROUTE: _handle_route,
    NOTIFY: _handle_notify,
    DEFAULT: _handle_default,
    LOCK: _handle_lock,
}

if set(_HANDLERS) != set(RULE_ACTIONS):  # pragma: no cover - 静态一致性兜底
    raise RuntimeError(
        'rule_dispatcher 处理器注册表与 RULE_ACTIONS 不一致：'
        '缺少 %s，多出 %s' % (sorted(set(RULE_ACTIONS) - set(_HANDLERS)),
                            sorted(set(_HANDLERS) - set(RULE_ACTIONS))))

#: 处理器返回 None 时的跳过原因（便于审计区分「幂等」与「未声明」）
_SKIP_REASONS = {
    HOLD: 'already_held',
    ROUTE: 'route_not_applicable',
    NOTIFY: 'no_notify_channel',
    DEFAULT: 'no_default_fields',
}

#: 空动作（命中但未声明 disposition）的跳过原因
NO_ACTION = 'no_action_declared'


def dispatch(decision: Any, context: Optional[Dict[str, Any]] = None) -> DispatchResult:
    """按 ``decision.action`` 分派处置动作。

    未知动作抛 :class:`DispatchError`；未命中且 ``release_unmatched`` 为真时
    释放旧挂起，否则记为 skipped。
    """
    ctx = dict(context or {})
    matched = bool(getattr(decision, 'matched', False))
    action = str(getattr(decision, 'action', '') or '').strip().lower()
    key = _rule_key(decision, ctx)
    result = DispatchResult(action=action, matched=matched)

    if not matched:
        if ctx.get('release_unmatched'):
            entry = _handle_release(decision, ctx)
            if entry is None:
                result.skipped.append(
                    {'action': RELEASE, 'rule_key': key,
                     'reason': 'no_active_hold'})
            else:
                result.action = RELEASE
                result.applied.append(entry)
        else:
            result.skipped.append(
                {'action': action, 'rule_key': key, 'reason': 'not_matched'})
        return result

    if not action:
        fallback = str(ctx.get('fallback_action') or '').strip().lower()
        if not fallback:
            result.skipped.append(
                {'action': '', 'rule_key': key, 'reason': NO_ACTION})
            return result
        action = fallback
        result.action = fallback

    handler = _HANDLERS.get(action)
    if handler is None:
        raise DispatchError(
            '未知处置动作 %r（规则 %s）；允许 %s'
            % (action, key or '<unknown>', list(RULE_ACTIONS)))

    entry = handler(decision, ctx)
    if entry is None:
        result.skipped.append(
            {'action': action, 'rule_key': key,
             'reason': _SKIP_REASONS.get(action, 'no_op')})
    else:
        result.applied.append(entry)
    return result