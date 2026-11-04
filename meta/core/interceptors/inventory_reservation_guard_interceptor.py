# -*- coding: utf-8 -*-
"""库存预留守卫拦截器 —— 预留写入与状态迁移的统一入口。

口径:
  ① 创建委托 `InventoryReservationService.create_reservation`：取号、段解析、
     幂等键、投影回写全部在服务层完成。
  ② 更新只允许「status=cancelled」触发释放；段列与数量不可通过通用更新修改。
  ③ 删除仅允许 cancelled / expired（与 schema deletion_policy 一致）。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.inventory_guard_service import InventoryError
from meta.services.inventory_reservation_service import (
    STATUS_CANCELLED,
    STATUS_EXPIRED,
    InventoryReservationService,
)
from meta.services.stock_segment_service import SEGMENT_COLUMNS

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT = 'inventory_reservation'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')
#: 创建后回填到写入参数的列（避免通用持久化覆盖服务派生值）
_CREATE_KEYS = (
    'reservation_no', 'status', 'stock_segment_type', 'project_id',
    'project_task_id', 'sales_order_line_id', 'owner_party_id',
    'qty_reserved', 'qty_fulfilled', 'peg_type', 'created_at', 'updated_at',
)
#: 不允许通过通用更新修改的列
_IMMUTABLE_KEYS = SEGMENT_COLUMNS + (
    'reservation_no', 'reservation_key', 'org_id', 'item_id', 'uom_id',
    'demand_object_type', 'demand_object_id', 'demand_line_id',
    'qty_reserved', 'qty_fulfilled', 'peg_type',
)


def _object_id(context) -> Any:
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


class InventoryReservationGuardInterceptor(Interceptor):
    """库存预留的写入守卫与状态迁移接线。"""

    @property
    def priority(self) -> int:
        return 60

    def should_execute(self, context: 'ActionContext') -> bool:
        return (getattr(context.meta_object, 'id', None) == OBJECT
                and context.action in _WRITE_ACTIONS)

    def before_action(self, context: 'ActionContext') -> None:
        try:
            if context.action == 'crud_create':
                self._create(context)
            elif context.action == 'crud_update':
                self._update(context)
            else:
                self._delete(context)
        except InventoryError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': error.code,
                    'rule': error.code,
                    'message': str(error),
                    'i18n_key': '',
                    'params': error.details,
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        return None

    # ------------------------------------------------------------------
    def _create(self, context: 'ActionContext') -> None:
        params = context.params if isinstance(context.params, dict) else {}
        service = InventoryReservationService(context.data_source)
        result = service.create_reservation(params)
        row = result.get('reservation') or {}
        for key in _CREATE_KEYS:
            if key in row:
                params[key] = row[key]
        params['id'] = row.get('id')
        if context.user_info:
            params.setdefault('created_by', context.user_info.get('username'))

    def _update(self, context: 'ActionContext') -> None:
        params = context.params if isinstance(context.params, dict) else {}
        target = params.get('status')
        reservation_id = _object_id(context)
        changed = [key for key in _IMMUTABLE_KEYS
                   if key in params and key != 'status']
        if changed and target != STATUS_CANCELLED:
            raise InventoryError(
                'INV_SEGMENT_INVALID',
                '预留的段/数量/需求键不可修改，请释放后重建',
                {'reservation_id': reservation_id, 'fields': changed})
        if target == STATUS_CANCELLED:
            service = InventoryReservationService(context.data_source)
            service.release_reservation(reservation_id,
                                        reason=params.get('remark') or '')
            params.clear()
            params.update({'id': reservation_id, 'status': STATUS_CANCELLED})
            return
        if target == STATUS_EXPIRED:
            raise InventoryError(
                'INV_RESERVATION_STATE_INVALID',
                'expired 仅由过期任务写入，禁止手工设置',
                {'reservation_id': reservation_id})

    def _delete(self, context: 'ActionContext') -> None:
        reservation_id = _object_id(context)
        service = InventoryReservationService(context.data_source)
        row = service._load(reservation_id)
        if row.get('status') not in (STATUS_CANCELLED, STATUS_EXPIRED):
            raise InventoryError(
                'INV_RESERVATION_STATE_INVALID',
                '仅已取消/已过期的预留可删除',
                {'reservation_id': reservation_id, 'status': row.get('status')})
