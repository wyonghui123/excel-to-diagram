# -*- coding: utf-8 -*-
"""批次守卫拦截器 —— 批次主数据的写前校验（P4c）。

优先级 56（过程指令守卫 55 之后、持久化 95 之前）：
  · 身份 `(item_id, org_id, batch_no)` 必填；`batch_no` ≤ 60。
  · `qty > 0`；`qty_uom_id` 与物料基本单位同 `uom_group`。
  · `status` / `quality_status` / `source` 枚举收敛。
  · `quality_status='blocked'` 时不允许 `status='closed'`。
  · `expiry_date >= date(produced_at)`；`potency_pct ∈ [0, 100]`。
  · 父批次单父、禁自指 / 成环（深度 ≤ 10）。
  · 更新时校验 `attribute_scopes(scope_ref='batch')` 必填特性是否已填。

口径: 只做写前校验，不回填业务字段；唯一索引由迁移兜底。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.batch_service import BatchError, BatchService

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT = 'batch'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class BatchGuardInterceptor(Interceptor):
    """批次主数据守卫。"""

    @property
    def priority(self) -> int:
        return 56

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id == OBJECT and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = BatchService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        try:
            service.validate_batch(params, old if old else None)
        except BatchError as error:
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
