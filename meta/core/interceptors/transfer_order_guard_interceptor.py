# -*- coding: utf-8 -*-
"""调拨单守卫拦截器 —— 抬头 / 调拨行的统一写入入口。

优先级 53（receipt_guard 52 之后、PersistenceInterceptor 95 之前）：
  · before_action 先做写前校验（R-TO-0 ~ R-TO-13），并把守卫派生出的只读字段
    回填到实际写入口径；生命周期动作的跨表副作用由 `TransferOrderService` 承接
    （动作通道见 `transfer_order_actions`）。
  · after_action 无需额外副作用：`fulfillment_status` 派生在服务层完成。

受管范围:
  transfer_order       —— 创建（归一化 + 法人快照）/ 更新（冻结字段与终态保护）/ 删除
  transfer_order_line  —— 创建 / 更新 / 删除（行类型、物料、单位、数量区间校验）

口径:
  · 本拦截器不写 `status` / `fulfillment_status`（唯一写者是
    `TransferOrderService.release / ship / cancel / close / apply_receipt`）；
  · `legal_entity_id` 由调出 / 调入组织上溯解析后只读回填，解析失败直接拒绝
    （不降级放空值）；
  · 库存台账、发货单、成本金额均不在本波范围。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.transfer_order_guard_service import TransferOrderGuardService
from meta.services.transfer_order_service import TransferOrderError

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'transfer_order'
LINE_OBJECT = 'transfer_order_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')

#: 抬头由守卫派生后回填到写入口径的只读列
_HEADER_SYNC_KEYS = (
    'legal_entity_id',
    'fulfillment_status',
)
#: 行由守卫归一化后回填到写入口径的列
_LINE_NORMALIZED_KEYS = (
    'line_no', 'line_type_id', 'item_id', 'uom_id', 'qty',
    'qty_shipped', 'qty_received',
)


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class TransferOrderGuardInterceptor(Interceptor):
    """调拨单头 / 调拨行的守卫。"""

    @property
    def priority(self) -> int:
        return 53

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
        except TransferOrderError as error:
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
        # 派生字段已由服务层落库，无需在 after 侧回写
        return None

    # ------------------------------------------------------------------ 抬头

    def _guard_header(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        guard = TransferOrderGuardService(context.data_source)
        transfer_order_id = _object_id(context)

        if context.action == 'crud_delete':
            guard.validate_delete(transfer_order_id)
            return
        if context.action == 'crud_create':
            header = guard.validate_create(params)
            self._sync_header_params(params, header)
            return

        derived = guard.validate_update(dict(params), context.old_data)
        self._sync_header_params(params, derived)

    @staticmethod
    def _sync_header_params(params: Dict[str, Any],
                            values: Dict[str, Any]) -> None:
        for key in _HEADER_SYNC_KEYS:
            value = (values or {}).get(key)
            if not _blank(value):
                params[key] = value

    # ------------------------------------------------------------------ 行

    def _guard_line(self, context: 'ActionContext') -> None:
        guard = TransferOrderGuardService(context.data_source)
        if context.action == 'crud_delete':
            # 守卫服务未提供行级删除校验：以父单 draft 约束兜底（行随头级联删除）
            parent_id = (context.old_data or {}).get('transfer_order_id')
            if not _blank(parent_id):
                guard.validate_delete(parent_id)
            return

        if context.action == 'crud_create':
            values = guard.validate_line(
                context.params, (context.params or {}).get('transfer_order_id'))
        else:
            merged = dict(context.old_data or {})
            merged.update(context.params or {})
            values = guard.validate_line(
                merged, merged.get('transfer_order_id'))
        self._fill_line_params(context, values)

    @staticmethod
    def _fill_line_params(context: 'ActionContext',
                          values: Dict[str, Any]) -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        for key in _LINE_NORMALIZED_KEYS:
            if key in (values or {}):
                params[key] = values[key]
