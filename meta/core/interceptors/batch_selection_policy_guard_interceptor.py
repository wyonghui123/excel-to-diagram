# -*- coding: utf-8 -*-
"""批次选择策略守卫拦截器 —— rule_json / 范围 / 优先级的写前校验（P5）。

优先级 58（序列守卫 57 之后、持久化 95 之前）：
  · rule_json v1 白名单（只允许 batches 物理列，EAV 特性拒绝）。
  · scope_ref 目标表存在性。
  · 同 (scope_type, scope_ref) 下 active priority 唯一。

口径: 只做写前校验；唯一索引由迁移兜底。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.batch_selection_policy_service import (
    BatchSelectionPolicyError,
    BatchSelectionPolicyService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT = 'batch_selection_policy'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class BatchSelectionPolicyGuardInterceptor(Interceptor):
    """批次选择策略守卫。"""

    @property
    def priority(self) -> int:
        return 58

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id == OBJECT and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = BatchSelectionPolicyService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        try:
            service.validate_policy(params, old if old else None)
        except BatchSelectionPolicyError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': error.field_name,
                    'rule': error.rule,
                    'message': str(error),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        return None
