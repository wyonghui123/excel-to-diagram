# -*- coding: utf-8 -*-
"""收货单守卫拦截器 —— 抬头状态迁移与收货行写入的统一入口。

优先级 52（shipment_guard 51 之后、PersistenceInterceptor 95 之前）：
  · before_action 先做写前校验（R-RC-0 ~ R-RC-18），再委托
    `ReceiptService.post / cancel` 完成跨表副作用（计划行回写、分配拆分、
    履约派生、状态置位）；
  · after_action 为逆序执行，此时抬头 / 行已落库，可安全把服务结果并回响应。

受管范围:
  receipt       —— 创建（归一化抬头 + 取号）/ 更新（仅状态迁移与时间补齐）/ 删除
  receipt_line  —— 创建 / 更新 / 删除（冗余列由服务校验后回填入参）

口径:
  · 本拦截器不写计划行 `received_qty` / `rejected_qty`，也不写
    `fulfillment_status`（INV-1 唯一写者是 PurchaseOrderFulfillmentService，
    由 receipt_service 调用）；跨表副作用一律委托服务。
  · `reversed` 只能由 `receipt.reverse` 动作产生，拦截器拒绝直接把状态改成
    reversed（R-RC-7 / §5.1）。
  · 状态迁移成功后收紧持久化入参：只保留 `id / status / actual_arrival_date`，
    避免过账已经写定的业务字段被同一请求体的旧值覆盖。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.receipt_guard_service import ReceiptGuardService
from meta.services.receipt_service import (
    STATUS_CANCELLED,
    STATUS_POSTED,
    ReceiptError,
    ReceiptService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'receipt'
LINE_OBJECT = 'receipt_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
_RESULT_KEY = 'receipt_result'
#: 创建时由服务归一化后回填到写入口径的抬头列
_CREATE_SYNC_KEYS = (
    'receipt_no', 'document_type_id', 'receipt_date', 'source_doc_type',
    'source_doc_no', 'supplier_party_id', 'supplier_delivery_no', 'org_id',
    'purchase_org_id', 'deliver_to_location_id', 'project_id',
)
#: 行服务归一化后回填入参的冗余列
_LINE_NORMALIZED_KEYS = (
    'schedule_id', 'order_id', 'order_line_id', 'item_id', 'uom_id',
    'qty_received', 'qty_rejected', 'rejection_reason_code',
    'rejection_disposition', 'lot_no', 'serial_no', 'putaway_location_id',
)
#: 状态迁移时的显式参数
_ARRIVAL_DATE_KEY = 'actual_arrival_date'


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class ReceiptGuardInterceptor(Interceptor):
    """收货单头 / 行的守卫与过账接线。"""

    @property
    def priority(self) -> int:
        return 52

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
        except ReceiptError as error:
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
        info = (context.extra or {}).get(_RESULT_KEY)
        if not info:
            return
        if context.result is not None and isinstance(context.result.data, dict):
            for key in ('order_ids', 'idempotent', 'reversal_receipt_no'):
                if key in info:
                    context.result.data[key] = info[key]

    # ------------------------------------------------------------------ 抬头

    def _guard_header(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        guard = ReceiptGuardService(context.data_source)
        receipt_id = _object_id(context)

        if context.action == 'crud_delete':
            guard.validate_delete(receipt_id)
            return
        if context.action == 'crud_create':
            header = guard.prepare_create(params)
            self._sync_create_params(params, header)
            return

        target = guard.validate_header_update(params, context.old_data)
        if target is None:
            return

        service = ReceiptService(context.data_source)
        if target == STATUS_POSTED:
            result = service.post(
                receipt_id, actual_arrival_date=params.get(_ARRIVAL_DATE_KEY))
        elif target == STATUS_CANCELLED:
            result = service.cancel(receipt_id)
        else:  # 守卫已拦截，兜底防新增分支漏配
            return
        context.extra[_RESULT_KEY] = result
        self._tighten_transition_params(params, receipt_id, target)

    @staticmethod
    def _sync_create_params(params: Dict[str, Any],
                            header: Dict[str, Any]) -> None:
        for key in _CREATE_SYNC_KEYS:
            value = header.get(key)
            if not _blank(value):
                params[key] = value

    @staticmethod
    def _tighten_transition_params(params: Dict[str, Any], receipt_id: Any,
                                   target: str) -> None:
        """过账 / 取消的服务已写定业务字段，持久化只回写状态本身。"""
        keep = {'id': receipt_id, 'status': target}
        if target == STATUS_POSTED and not _blank(params.get(_ARRIVAL_DATE_KEY)):
            keep[_ARRIVAL_DATE_KEY] = params[_ARRIVAL_DATE_KEY]
        params.clear()
        params.update(keep)

    # ------------------------------------------------------------------ 行

    def _guard_line(self, context: 'ActionContext') -> None:
        guard = ReceiptGuardService(context.data_source)
        if context.action == 'crud_delete':
            guard.validate_line_delete(_object_id(context))
            return
        if context.action == 'crud_create':
            values = guard.validate_line_create(
                context.params, context.params.get('receipt_id'))
        else:
            values = guard.validate_line_update(
                _object_id(context), context.params)
        self._fill_line_params(context, values)

    @staticmethod
    def _fill_line_params(context: 'ActionContext',
                          values: Dict[str, Any]) -> None:
        """把服务归一化后的冗余列回填入参，供持久化层写入。"""
        params = context.params
        if not isinstance(params, dict):
            return
        for key in _LINE_NORMALIZED_KEYS:
            if key in values:
                params[key] = values[key]
