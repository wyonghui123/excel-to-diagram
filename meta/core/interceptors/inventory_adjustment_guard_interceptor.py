# -*- coding: utf-8 -*-
"""库存调整单守卫拦截器 —— 调整单抬头 / 调整行的统一写入入口。

优先级 58（inventory_count_guard 59 之前、PersistenceInterceptor 95 之前）：
  · before_action 完成写前校验与派生：创建取号 / 类型白名单、状态迁移委托
    `InventoryAdjustmentService`（release / post / reverse / cancel）、终态锁定、
    行仅草稿可编辑；
  · 状态迁移成功后收紧持久化入参为 `id / status`，避免过账已写定的业务字段
    被同一请求体的旧值覆盖。

受管范围:
  inventory_adjustment       —— 创建 / 更新（状态迁移 + 冻结字段）/ 删除
  inventory_adjustment_line  —— 创建 / 更新 / 删除（行号、单位、状态对由服务派生）

口径:
  · `status` 的唯一写者是服务动作，拦截器只做分派与入参收紧；
  · 库存事务、余额投影一律由服务层完成，拦截器不写台账；
  · 权限异常（PermissionDenied）不在本拦截器捕获，交由权限拦截器 on_error 返回 403。
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.inventory_adjustment_service import (
    INV_ADJ_STATE_INVALID,
    STATUS_CANCELLED,
    STATUS_POSTED,
    STATUS_RELEASED,
    STATUS_REVERSED,
    InventoryAdjustmentService,
)
from meta.services.inventory_guard_service import InventoryError

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEADER_OBJECT = 'inventory_adjustment'
LINE_OBJECT = 'inventory_adjustment_line'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')

#: 创建时由服务归一化后回填到写入口径的抬头列
_CREATE_SYNC_KEYS = (
    'adjustment_no', 'adjustment_type', 'status', 'posting_date', 'org_id',
    'location_id', 'reason_code', 'reason_text', 'created_by', 'created_at',
    'updated_at',
)
#: 行创建时由服务派生后回填入参的列
_LINE_CREATE_KEYS = (
    'line_no', 'adjustment_id', 'uom_id', 'from_stock_status',
    'to_stock_status', 'created_at', 'updated_at',
)
#: 行更新时由服务归一化后回填入参的列
_LINE_UPDATE_KEYS = (
    'adjustment_id', 'uom_id', 'from_stock_status', 'to_stock_status',
    'updated_at',
)
#: 目标状态 → 服务动作
_STATUS_ACTIONS = {
    STATUS_RELEASED: 'release',
    STATUS_POSTED: 'post',
    STATUS_REVERSED: 'reverse',
    STATUS_CANCELLED: 'cancel',
}


def _object_id(context) -> Any:
    """目标记录 ID：优先 ActionContext 属性，退化到入参 id（SimpleNamespace 场景）。"""
    return getattr(context, 'object_id', None) or (context.params or {}).get('id')


def _blank(value: Any) -> bool:
    return value is None or value == ''


class InventoryAdjustmentGuardInterceptor(Interceptor):
    """库存调整单头 / 行的守卫与状态迁移接线。"""

    @property
    def priority(self) -> int:
        return 58

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
        # 状态与台账已由服务层落库，无需在 after 侧回写
        return None

    # ------------------------------------------------------------------ 抬头

    def _guard_header(self, context: 'ActionContext') -> None:
        params = context.params
        if not isinstance(params, dict):
            return
        service = InventoryAdjustmentService(context.data_source)
        adjustment_id = _object_id(context)

        if context.action == 'crud_delete':
            service.assert_deletable(adjustment_id)
            return
        if context.action == 'crud_create':
            header = service.prepare_create(params, context.user_info)
            _fill_params(params, header, _CREATE_SYNC_KEYS)
            return

        target = params.get('status')
        if _blank(target):
            # 普通字段更新：服务未提供单独的状态断言，复用草稿约束（非草稿抛 INV_DOC_POSTED_LOCKED）
            service.assert_deletable(adjustment_id)
            return

        action = _STATUS_ACTIONS.get(target)
        if action is None:
            raise InventoryError(
                INV_ADJ_STATE_INVALID, '未知的目标状态: %s' % target,
                {'adjustment_id': adjustment_id, 'status': target})
        if action == 'release':
            service.release(adjustment_id, context.user_info)
        elif action == 'post':
            service.post(adjustment_id, bypass_posting_block=False,
                         user_info=context.user_info)
        elif action == 'reverse':
            service.reverse(adjustment_id, context.user_info)
        else:
            service.cancel(adjustment_id, context.user_info)

        # 服务已写定业务字段，持久化只回写状态本身
        params.clear()
        params.update({'id': adjustment_id, 'status': target})

    # ------------------------------------------------------------------ 行

    def _guard_line(self, context: 'ActionContext') -> None:
        params = context.params if isinstance(context.params, dict) else {}
        old_data = context.old_data or {}
        parent_id = (old_data.get('adjustment_id')
                     or params.get('adjustment_id'))
        service = InventoryAdjustmentService(context.data_source)
        line_id = _object_id(context)

        if context.action == 'crud_delete':
            service.assert_line_deletable(parent_id, line_id)
            return
        if context.action == 'crud_create':
            values = service.prepare_line_create(
                params.get('adjustment_id'), params)
            _fill_params(params, values, _LINE_CREATE_KEYS)
            return

        values = service.prepare_line_update(parent_id, line_id, params)
        _fill_params(params, values, _LINE_UPDATE_KEYS)


def _fill_params(params: Dict[str, Any], values: Dict[str, Any],
                 keys) -> None:
    """把服务派生 / 归一化后的列回填入参，供持久化层写入。"""
    if not isinstance(params, dict):
        return
    for key in keys:
        if key in (values or {}):
            params[key] = values[key]
