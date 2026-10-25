# -*- coding: utf-8 -*-
"""税务守卫拦截器 —— 税码 / 税率 / 税务登记号写入的唯一入口。

依据:
  docs/superpowers/specs/2026-10-25-tax-wave0-implementation-spec.md §6

优先级 46（排在 CurrencyRateGuardInterceptor(44) 之后、HierarchyValidationInterceptor(45)
之后，避免同优先级顺序不确定）；仅对 tax_code / tax_rate / party_tax_registration
的创建 / 更新生效，其余对象与动作零开销短路。
判定口径见 meta/services/tax_guard_service.py（C1/C2、G1–G6）。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 currency_rate / payment_term 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.tax_guard_service import TaxGuardError, TaxGuardService

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

GUARDED_OBJECTS = {'tax_code', 'tax_rate', 'party_tax_registration'}
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class TaxGuardInterceptor(Interceptor):
    """税务三对象守卫（C1/C2、G1–G6）。"""

    @property
    def priority(self) -> int:
        return 46

    def should_execute(self, context: 'ActionContext') -> bool:
        if getattr(context.meta_object, 'id', None) not in GUARDED_OBJECTS:
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = TaxGuardService(context.data_source)
        params = dict(context.params or {})
        data = params
        exclude_id = None
        if context.action == 'crud_update':
            # 更新可能是部分字段：与旧行合并还原「更新后的有效行」
            merged = dict(context.old_data or {})
            merged.update(params)
            data = merged
            exclude_id = context.object_id or params.get('id')

        try:
            object_id = getattr(context.meta_object, 'id', None)
            if object_id == 'tax_code':
                service.validate_tax_code_write(data, exclude_id=exclude_id)
            elif object_id == 'tax_rate':
                service.validate_tax_rate_write(data, exclude_id=exclude_id)
            elif object_id == 'party_tax_registration':
                service.validate_party_tax_registration_write(data, exclude_id=exclude_id)
        except TaxGuardError as e:
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
