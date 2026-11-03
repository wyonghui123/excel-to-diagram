# -*- coding: utf-8 -*-
"""单据序列号守卫拦截器 —— 收货 / 发运过账前置校验（P6a / P60）。

优先级 50：必须早于 ShipmentGuardInterceptor(51) 与
ReceiptGuardInterceptor(52) —— 后两者在 before_action 内直接调用
`ship_confirm()` / `post()` 完成过账副作用，晚于它们执行将失去拦截意义。
规格中的 “P60” 为编号，不是 priority 数值。

受管范围:
  receipt  —— crud_update 且目标 status = posted
  shipment —— crud_update 且目标 status = shipped

口径（§6.1）:
  · require_on_receipt / require_on_issue=1 时，link 数必须等于数量；
  · qty=1 且行内 serial_no 非空 = 快捷录入（放行，由服务登记）；
  · qty>1 且行内 serial_no 非空 = 拒绝（SERIAL_SINGLE_VALUE_WITH_MULTI_QTY）；
  · 物料未启用序列号管理却填写 serial_no = 拒绝。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.serial_number_service import (
    SerialNumberError,
    SerialNumberService,
)
from meta.services.receipt_service import STATUS_POSTED
from meta.services.shipment_service import STATUS_SHIPPED

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT_RECEIPT = 'receipt'
OBJECT_SHIPMENT = 'shipment'
OBJECTS = (OBJECT_RECEIPT, OBJECT_SHIPMENT)


class SerialTrackingGuardInterceptor(Interceptor):
    """收货 / 发运过账的序列号前置守卫。"""

    @property
    def priority(self) -> int:
        return 50

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id in OBJECTS and context.action == 'crud_update'

    def before_action(self, context: 'ActionContext') -> None:
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        target = params.get('status')
        if target is None or target == old.get('status'):
            return
        document_id = getattr(context, 'object_id', None) or params.get('id')
        if document_id is None:
            return
        object_id = getattr(context.meta_object, 'id', None)
        service = SerialNumberService(context.data_source)
        try:
            if object_id == OBJECT_RECEIPT and target == STATUS_POSTED:
                service.precheck_receipt(document_id)
            elif object_id == OBJECT_SHIPMENT and target == STATUS_SHIPPED:
                service.precheck_shipment(document_id)
        except SerialNumberError as error:
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
