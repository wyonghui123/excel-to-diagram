# -*- coding: utf-8 -*-
"""付款条件守卫拦截器 —— 分期行写入的唯一入口。

优先级 44（在 ConstraintValidationInterceptor 42 之后、HierarchyValidationInterceptor 45 之前）；
仅对 payment_term_line 的创建 / 更新生效，其余对象与动作零开销短路。
判定口径见 meta/services/payment_term_guard_service.py（G1 上半 / G3 / G4）。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 uom_conversion / currency_rate 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.payment_term_guard_service import (
    PaymentTermGuardError,
    PaymentTermGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

GUARDED_OBJECT = 'payment_term_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class PaymentTermGuardInterceptor(Interceptor):
    """付款条件分期守卫（G1 上限 / G3 / G4）。"""

    @property
    def priority(self) -> int:
        return 44

    def should_execute(self, context: 'ActionContext') -> bool:
        if getattr(context.meta_object, 'id', None) != GUARDED_OBJECT:
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = PaymentTermGuardService(context.data_source)
        params = dict(context.params or {})
        exclude_id = None
        data = params
        if context.action == 'crud_update':
            # 更新可能是部分字段：与旧行合并还原「更新后的有效行」
            merged = dict(context.old_data or {})
            merged.update(params)
            data = merged
            exclude_id = context.object_id or params.get('id')

        try:
            service.validate_line_write(data, exclude_id=exclude_id)
        except PaymentTermGuardError as e:
            from meta.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                message=str(e),
                details=[{
                    'field_name': e.field_name,
                    'rule': e.rule,
                    'message': str(e),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass
