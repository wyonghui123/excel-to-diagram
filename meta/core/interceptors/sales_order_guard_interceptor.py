# -*- coding: utf-8 -*-
"""销售订单守卫拦截器 —— 抬头 / 订单行写入的统一入口。

优先级 49（item_structure 46 / config_rule 47 / configuration 48 之后，
PersistenceInterceptor 95 之前）：
  · before_action 做写前校验（W0-R1/R2/R4/R5/R6/R8/R9/R10）；
  · after_action 做金额重算（W0-R7/R11/R12）—— 拦截器 after 为逆序执行，
    优先级 49 低于 PersistenceInterceptor 的 95，故重算时行已落库、新行 id 已回填。

受管范围：
  sales_order          —— 创建 / 更新 / 删除
  sales_order_line     —— 创建 / 更新 / 删除
  sales_order_schedule —— 创建 / 更新 / 删除（R-SCH-0 ~ R-SCH-10，
                          不参与金额 / 定价回写）
其余对象与动作零开销短路。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 uom_conversion / payment_term 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.sales_order_amount_service import (
    SalesOrderAmountError,
    SalesOrderAmountService,
)
from meta.services.sales_order_guard_service import (
    SalesOrderGuardError,
    SalesOrderGuardService,
)
from meta.services.sales_order_pricing_service import (
    SalesOrderPricingError,
    SalesOrderPricingService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

ORDER_OBJECT = 'sales_order'
LINE_OBJECT = 'sales_order_line'
SCHEDULE_OBJECT = 'sales_order_schedule'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
_ORDER_ID_KEY = 'so_parent_order_id'
# 抬头变更触发重取价的维度（§3.7 触发时点 3）
_PRICE_HEADER_FIELDS = ('price_date', 'currency_id', 'sales_org_id', 'order_type_id')
# 行变更触发重取价的维度（§3.7 触发时点 2）
_PRICE_LINE_FIELDS = ('item_id', 'qty', 'uom_id')


class SalesOrderGuardInterceptor(Interceptor):
    """销售订单头 / 行的守卫与金额回写。"""

    @property
    def priority(self) -> int:
        return 49

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (ORDER_OBJECT, LINE_OBJECT, SCHEDULE_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        guard = SalesOrderGuardService(context.data_source)
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == ORDER_OBJECT:
                if context.action == 'crud_delete':
                    guard.validate_order_delete(context.object_id)
                    return
                data, old_data = self._effective_data(context)
                # TER-M3：新建订单按客户主区域带出销售区域（手工已填不覆盖）
                if context.action == 'crud_create':
                    territory = guard.territory_default(data)
                    if territory:
                        data.update(territory)
                        if isinstance(context.params, dict):
                            context.params.update(territory)
                # W2-D：确认动作同一请求内回填地址文本快照（只补/覆盖自地址库全文）
                snapshot = guard.snapshot_address_text(data, old_data)
                if snapshot:
                    data.update(snapshot)
                    if isinstance(context.params, dict):
                        context.params.update(snapshot)
                guard.validate_order_write(
                    data, old_data=old_data,
                    is_create=context.action == 'crud_create')
                return

            if object_id == SCHEDULE_OBJECT:
                if context.action == 'crud_delete':
                    guard.validate_schedule_delete(context.object_id)
                    return
                data, old_data = self._effective_data(context)
                guard.validate_schedule_write(
                    data, old_data=old_data,
                    is_create=context.action == 'crud_create')
                return

            # 订单行
            if context.action == 'crud_delete':
                # 删除前先记下父单（after_action 时行已不在了）
                context.extra[_ORDER_ID_KEY] = (context.old_data or {}).get('order_id')
                guard.validate_line_delete(context.object_id)
                return

            data, old_data = self._effective_data(context)
            is_create = context.action == 'crud_create'
            # W2-A：服务行默认值（计费方式 / 资源类型 / 时长 / 时长单位）随创建写入
            if is_create:
                defaults = guard.service_line_defaults(data)
                if defaults:
                    data.update(defaults)
                    if isinstance(context.params, dict):
                        context.params.update(defaults)
            context.extra[_ORDER_ID_KEY] = data.get('order_id')
            guard.validate_line_write(
                data, old_data=old_data, is_create=is_create)
        except SalesOrderGuardError as e:
            self._raise_validation(e)

    def after_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == SCHEDULE_OBJECT:
            # 计划行不参与行金额 / 定价回写
            return
        if object_id == ORDER_OBJECT:
            self._after_order_write(context)
            return
        if object_id != LINE_OBJECT:
            return

        pricing = SalesOrderPricingService(context.data_source)
        self._apply_line_pricing(context, pricing)

        amount = SalesOrderAmountService(context.data_source)
        try:
            if context.action in ('crud_create', 'crud_update'):
                line_id = context.object_id
                if line_id in (None, ''):
                    return
                values = amount.recompute_line(line_id)
                self._merge_result(context, values)

            order_id = context.extra.get(_ORDER_ID_KEY)
            if order_id in (None, '') and context.old_data:
                order_id = context.old_data.get('order_id')
            if order_id in (None, ''):
                return
            totals = amount.recompute_order(order_id)
            self._merge_result(context, totals)
            status = pricing.refresh_order_pricing_status(order_id)
            if status and context.result and context.result.data is not None:
                context.result.data['pricing_status'] = status
        except SalesOrderAmountError as e:
            self._raise_validation(e)

    # ---------------- 定价接线 ----------------

    def _apply_line_pricing(self, context: 'ActionContext',
                            pricing: SalesOrderPricingService) -> None:
        """按 §3.7 触发时点对行取价；手工改价只打标记不重取。"""
        line_id = context.object_id
        if line_id in (None, ''):
            return
        params = dict(context.params or {})

        if context.action == 'crud_create':
            manual = params.get('unit_price') not in (None, '')
        elif context.action == 'crud_update':
            if 'unit_price' in params and params.get('unit_price') is not None:
                pricing.mark_manual(line_id)
                return
            if not (set(params) & set(_PRICE_LINE_FIELDS)):
                return
            manual = False
        else:
            return

        if manual:
            pricing.mark_manual(line_id)
            return
        pricing.price_line(line_id)

    def _after_order_write(self, context: 'ActionContext') -> None:
        """抬头定价维度变更 → 重解析并重取全部非手工行（§3.7 触发时点 3）。"""
        if context.action != 'crud_update':
            return
        if not (set(dict(context.params or {})) & set(_PRICE_HEADER_FIELDS)):
            return

        pricing = SalesOrderPricingService(context.data_source)
        try:
            summary = pricing.reprice_order(context.object_id, force=False,
                                            strict=False)
        except SalesOrderPricingError as e:
            self._raise_validation(e)
            return
        if not summary or not context.result or context.result.data is None:
            return
        context.result.data['pricing_status'] = summary['pricing_status']
        self._merge_result(context, {
            'net_amount': summary.get('net_amount'),
            'tax_amount': summary.get('tax_amount'),
            'gross_amount': summary.get('gross_amount'),
        })

    # ---------------- 内部 ----------------

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
    def _merge_result(context: 'ActionContext', values) -> None:
        """把重算结果并回响应体（Decimal → float，便于 JSON 序列化）。"""
        if not values or not context.result or not context.result.data:
            return
        for key, value in values.items():
            context.result.data[key] = (
                None if value is None else float(value))

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
