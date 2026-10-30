# -*- coding: utf-8 -*-
"""交货单守卫拦截器 —— 抬头状态迁移与交货行写入的统一入口。

优先级 51（territory 50 之后、PersistenceInterceptor 95 之前）：
  · before_action 先于持久化做写前校验与状态迁移委托；
  · after_action 为逆序执行，此时抬头 / 行已落库，可安全派生履约状态。

受管范围：
  shipment        —— 创建 / 更新 / 删除；shipped / delivered / cancelled 三段
                     迁移携带跨表副作用，委托 shipment_service 执行
  shipment_line   —— 创建 / 更新 / 删除；行冗余列（schedule_id / order_line_id /
                     item_id / uom_id / qty）由服务校验后回填入参
其余对象与动作零开销短路。

口径：
  · 本拦截器**不写** fulfillment_status（INV-1：唯一写者是
    SalesOrderFulfillmentService.recompute_order），只把派生结果并回响应体；
  · 跨表副作用（计划行 delivered_qty 回写、行级联状态）一律委托
    shipment_service，拦截器自身不发 SQL；
  · 已知边界：before_action 内服务已提交（服务不自行开事务），若随后持久化失败，
    跨表状态可能已变更；状态迁移请求通常只含 status，重复提交由服务幂等兜底
    （ship confirm 已 shipped 及之后直接返回）。拦截器链只覆盖 bo_api 写路径，
    manage_api 与 Excel 导入绕过本守卫。
"""

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.sales_order_fulfillment_service import SalesOrderFulfillmentService
from meta.services.shipment_service import (
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_DELIVERED,
    STATUS_RELEASED,
    STATUS_SHIPPED,
    STATUS_STAGED,
    ShipmentError,
    ShipmentService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'shipment'
LINE_OBJECT = 'shipment_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
#: 行服务归一化后回填入参的列
_LINE_NORMALIZED_KEYS = ('schedule_id', 'order_line_id', 'item_id', 'uom_id', 'qty')


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class ShipmentGuardInterceptor(Interceptor):
    """交货单头 / 行的守卫与履约状态接线。"""

    @property
    def priority(self) -> int:
        return 51

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (HEADER_OBJECT, LINE_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == HEADER_OBJECT:
                self._guard_header(context)
            elif object_id == LINE_OBJECT:
                self._guard_line(context)
        except ShipmentError as error:
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
        order_id = (context.extra or {}).get('shipment_order_id')
        if order_id is None:
            return
        status = SalesOrderFulfillmentService(
            context.data_source).recompute_order(order_id)
        if context.result is not None and isinstance(context.result.data, dict):
            context.result.data['fulfillment_status'] = status

    # ---------------- 抬头 ----------------

    def _guard_header(self, context: 'ActionContext') -> None:
        payload = context.params or {}
        service = ShipmentService(context.data_source)
        delivery_id = _object_id(context)

        if context.action == 'crud_delete':
            service.assert_deletable(delivery_id)
            return
        if context.action != 'crud_update':
            return

        target = payload.get('status')
        if _blank(target):
            return
        current = (context.old_data or {}).get('status')
        if target == current:
            return

        result = self._delegate_transition(
            service, delivery_id, target, payload)
        if result is None:
            return
        context.extra['shipment_result'] = result
        if result.get('order_id') is not None:
            context.extra['shipment_order_id'] = result['order_id']

    @staticmethod
    def _delegate_transition(service: ShipmentService, delivery_id: Any,
                             target: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """按目标状态委托服务；closed 无跨表副作用，不委托。"""
        if target == STATUS_RELEASED:
            return service.release(delivery_id)
        if target == STATUS_STAGED:
            return service.stage(delivery_id)
        if target == STATUS_SHIPPED:
            return service.ship_confirm(
                delivery_id, actual_ship_date=payload.get('actual_ship_date'))
        if target == STATUS_DELIVERED:
            return service.receive(
                delivery_id,
                signature_ref=payload.get('signature_ref'),
                actual_arrival_date=payload.get('actual_arrival_date'))
        if target == STATUS_CANCELLED:
            return service.cancel(delivery_id)
        if target == STATUS_CLOSED:
            return None
        return None

    # ---------------- 行 ----------------

    def _guard_line(self, context: 'ActionContext') -> None:
        if context.action == 'crud_delete':
            return
        service = ShipmentService(context.data_source)
        if context.action == 'crud_create':
            normalized = service.validate_new_line(context.params)
        else:
            normalized = service.update_line(
                _object_id(context), context.params)
        self._fill_line_params(context, normalized)

    @staticmethod
    def _fill_line_params(context: 'ActionContext', values: Dict[str, Any]) -> None:
        """把服务归一化后的冗余列回填入参，供持久化层写入。"""
        params = context.params
        if not isinstance(params, dict):
            return
        for key in _LINE_NORMALIZED_KEYS:
            if key in values:
                params[key] = values[key]
