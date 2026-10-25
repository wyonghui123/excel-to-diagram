# -*- coding: utf-8 -*-
"""客户销售组织守卫拦截器 —— 销售职能校验的唯一入口（W1-R11）。

优先级 49：与其余业务守卫同档，位于 PersistenceInterceptor（95）之前。
受管范围：`customer_sales_org` 的创建 / 更新；其余对象与动作零开销短路。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 绕过拦截器链
（与 sales_order / payment_term 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.customer_sales_org_guard_service import (
    CustomerSalesOrgGuardError,
    CustomerSalesOrgGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT_ID = 'customer_sales_org'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class CustomerSalesOrgGuardInterceptor(Interceptor):
    """客户销售组织写前校验。"""

    @property
    def priority(self) -> int:
        return 49

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id != OBJECT_ID:
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        guard = CustomerSalesOrgGuardService(context.data_source)
        data, _old = self._effective_data(context)
        try:
            guard.validate_write(data)
        except CustomerSalesOrgGuardError as e:
            self._raise_validation(e)

    def after_action(self, context: 'ActionContext') -> None:
        """写后无动作（守卫只做前置校验）。"""

    @staticmethod
    def _effective_data(context: 'ActionContext') -> tuple:
        """更新可能是部分字段：与旧行合并还原「更新后的有效行」。"""
        params = dict(context.params or {})
        if context.action != 'crud_update':
            return params, context.old_data
        merged = dict(context.old_data or {})
        merged.update(params)
        return merged, context.old_data

    @staticmethod
    def _raise_validation(error) -> None:
        from meta.core.exceptions import ValidationFailedError

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
