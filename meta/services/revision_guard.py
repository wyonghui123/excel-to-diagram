# -*- coding: utf-8 -*-
"""修订闸门（FR-006）

顺序（spec §5）：
  1. enabled              —— 未启用直接跳过（零回归）
  2. editable_in_states   —— 命中当前 status 才允许
  3. editable_when        —— ConditionEvaluator 求值（fail-closed）
  4. fulfillment_status 分档 —— partial 需变更申请（M2 一律拒）；fulfilled/voided 拒绝

所有失败统一抛 RevisionError（错误码 + 业务消息）。
"""
from __future__ import annotations

from typing import Any, Dict

from meta.core.condition_evaluator import ConditionEvaluator
from meta.services.revision_service import RevisionError

STATUS_NOT_EDITABLE = 'REVISION_STATE_NOT_EDITABLE'
NOT_ALLOWED = 'REVISION_NOT_ALLOWED'
REQUIRES_CHANGE_REQUEST = 'REVISION_REQUIRES_CHANGE_REQUEST'
NOT_ALLOWED_FULFILLED = 'REVISION_NOT_ALLOWED_FULFILLED'

_FULFILLED_STATES = frozenset({'fulfilled', 'voided'})
_PARTIAL_STATES = frozenset({'partial'})


class RevisionGuard:
    """修订闸门（无状态，可复用）"""

    def __init__(self, evaluator=None):
        self._evaluator = evaluator or ConditionEvaluator()

    def check(self, meta_object, record: Dict[str, Any],
              changed_fields=None) -> None:
        """不通过即抛 RevisionError；通过则静默返回。"""
        policy = getattr(meta_object, 'revision_policy', None)
        if policy is None or not policy.enabled:
            return
        record = record or {}

        allowed_states = list(policy.editable_in_states or [])
        if allowed_states:
            status = record.get('status')
            if status not in allowed_states:
                raise RevisionError(
                    STATUS_NOT_EDITABLE,
                    '当前状态 %s 不允许修改内容（允许: %s）' % (
                        status, ', '.join(map(str, allowed_states))),
                )

        condition = (policy.editable_when or '').strip()
        if condition:
            if not self._evaluator.evaluate(condition, dict(record)):
                raise RevisionError(
                    NOT_ALLOWED,
                    '不满足修改条件: %s' % condition,
                )

        fulfillment = record.get('fulfillment_status')
        if fulfillment in _PARTIAL_STATES:
            raise RevisionError(
                REQUIRES_CHANGE_REQUEST,
                '单据已部分履约，修改必须走变更申请',
            )
        if fulfillment in _FULFILLED_STATES:
            raise RevisionError(
                NOT_ALLOWED_FULFILLED,
                '单据已履约（%s），不允许修改' % fulfillment,
            )
