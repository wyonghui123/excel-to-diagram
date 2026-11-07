# -*- coding: utf-8 -*-
"""G15 项目任务执行守卫拦截器 —— 工单项目归属（G1-G5）+ 任务解绑（G9）。

依据:
  docs/specs/spec-project-g15-eto-solution-2026-11-04.md §4.2 / §4.4 / §5

受管范围:
  work_order    —— 创建 / 更新：G1-G4 归属校验，G5 发布后锁定
  project_task  —— 删除 / 置 cancelled：G9 被引用时拒绝（409 语义）

说明:
  · 工单服务自建路径（WorkOrderService.create_work_order）已在服务内校验，
    本拦截器覆盖通用 BO CRUD 写路径（含更新），口径调用同一函数。
  · G9 的 409 语义由 `ProjectTaskGuardError.status_code` 承载；BO 框架统一
    返回 400 时，明细里仍带 http_status 供前端映射。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services import project_task_guard
from meta.services.work_order_service import (
    STATUS_CLOSED, WorkOrderError, WorkOrderService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

WORK_ORDER_OBJECT = 'work_order'
PROJECT_TASK_OBJECT = 'project_task'
_WRITE_ACTIONS = ('crud_create', 'crud_update')
_GUARDED_WORK_ORDER_FIELDS = ('project_id', 'project_task_id', 'status')
_STATUS_CANCELLED = 'cancelled'


def _to_int(value) -> int:
    if value in (None, ''):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class ProjectTaskGuardInterceptor(Interceptor):
    """工单归属守卫 + 项目任务解绑守卫。"""

    @property
    def priority(self) -> int:
        return 51

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == WORK_ORDER_OBJECT:
            return context.action in _WRITE_ACTIONS
        if object_id == PROJECT_TASK_OBJECT:
            return context.action in ('crud_delete', 'crud_update')
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == WORK_ORDER_OBJECT:
            self._guard_work_order(context)
            return
        self._guard_project_task(context)

    # ------------------------------------------------------------------
    # 工单 G1-G5
    # ------------------------------------------------------------------
    def _guard_work_order(self, context: 'ActionContext') -> None:
        data = dict(context.params or {})
        if context.action == 'crud_create' and self._is_production(data):
            self._guard_production_create(context, data)
            return
        if context.action == 'crud_update' \
                and not (set(data) & set(_GUARDED_WORK_ORDER_FIELDS)):
            return
        service = WorkOrderService(context.data_source)
        try:
            service.validate_project_scope(
                data, existing=(context.old_data or None)
                if context.action == 'crud_update' else None)
        except WorkOrderError as error:
            self._raise_validation(error)
        if context.action == 'crud_update':
            self._guard_work_order_close(context, data)

    @staticmethod
    def _is_production(data: dict) -> bool:
        return str(data.get('order_type') or '').strip().lower() == 'production'

    def _guard_production_create(self, context: 'ActionContext',
                                 data: dict) -> None:
        """通用 BO CRUD 建生产工单：与服务建单同一校验口径，并回填推导字段。"""
        service = WorkOrderService(context.data_source)
        try:
            normalized = service.validate_production_create(data)
        except WorkOrderError as error:
            self._raise_validation(error)
        for key in ('order_id', 'order_line_id', 'customer_account_id',
                    'project_id', 'project_task_id', 'schedule_id',
                    'item_id', 'planned_qty'):
            context.params[key] = normalized.get(key)
        context.extra['work_order_production'] = normalized

    def _guard_work_order_close(self, context: 'ActionContext',
                                data: dict) -> None:
        """工单关闭前置校验：仍有未核销组件承诺时拒绝 Closed。"""
        new_status = str(data.get('status') or '').strip().lower()
        old_status = str((context.old_data or {}).get('status') or '') \
            .strip().lower()
        if new_status != STATUS_CLOSED.lower() \
                or old_status == STATUS_CLOSED.lower():
            return
        work_order_id = _to_int(context.object_id) \
            or _to_int((context.old_data or {}).get('id'))
        if not work_order_id:
            return
        try:
            from meta.services.inventory_guard_service import InventoryError
            from meta.services.inventory_reservation_service import (
                InventoryReservationService,
            )
            InventoryReservationService(
                context.data_source).assert_source_closable(
                    'work_order', work_order_id)
        except InventoryError as error:
            self._raise_inventory_validation(error)

    # ------------------------------------------------------------------
    # 项目任务 G9
    # ------------------------------------------------------------------
    def _guard_project_task(self, context: 'ActionContext') -> None:
        old = dict(context.old_data or {})
        task_id = context.object_id or old.get('id')
        if task_id in (None, ''):
            return
        if context.action == 'crud_update':
            data = dict(context.params or {})
            if str(data.get('status') or '').strip().lower() != _STATUS_CANCELLED:
                return
            if str(old.get('status') or '').strip().lower() == _STATUS_CANCELLED:
                return
        try:
            project_task_guard.assert_task_not_referenced(
                context.data_source, task_id)
        except project_task_guard.ProjectTaskGuardError as error:
            self._raise_validation(error, http_status=error.status_code)

    # ------------------------------------------------------------------
    # 错误映射
    # ------------------------------------------------------------------
    @staticmethod
    def _raise_validation(error, http_status: int = 400) -> None:
        from meta.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            message=str(error),
            details=[{
                'field_name': getattr(error, 'field_name', ''),
                'rule': getattr(error, 'rule', ''),
                'message': str(error),
                'i18n_key': '',
                'params': {},
                'http_status': http_status,
            }],
        )

    @staticmethod
    def _raise_inventory_validation(error) -> None:
        from meta.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            message=str(error),
            details=[{
                'field_name': 'status',
                'rule': error.code,
                'message': error.message,
                'i18n_key': '',
                'params': {},
                'http_status': 400,
            }],
        )

    def after_action(self, context: 'ActionContext') -> None:
        """A3：工单/服务单创建或更新后，同步来源 SO 行与组件级 soft 预留。

        工单本身不新增预留事实：来源 SO 行走 sync_sales_order_line；
        组件（投料物料）是独立需求，走 sync_work_order_components。
        失败不阻断工单写入（仅告警）。
        """
        if getattr(context.meta_object, 'id', None) != WORK_ORDER_OBJECT:
            return
        if context.action not in _WRITE_ACTIONS:
            return
        result = context.result
        if result is not None and not getattr(result, 'success', True):
            return
        data = {}
        for source in (getattr(result, 'data', None), context.old_data,
                       context.params):
            for key, value in (source or {}).items():
                if value not in (None, ''):
                    data[key] = value
        line_id = _to_int(data.get('order_line_id'))
        work_order_id = (_to_int(getattr(context, 'object_id', 0))
                         or _to_int(data.get('id')))
        if context.action == 'crud_create':
            self._expand_components(context, work_order_id, data)
        if line_id > 0:
            try:
                from meta.services.inventory_reservation_service import (
                    InventoryReservationService,
                )
                InventoryReservationService(
                    context.data_source).sync_sales_order_line(line_id)
            except Exception as error:
                logger.warning(
                    '[inv2] 工单来源行 %s 预留同步失败（不阻断写入）: %s',
                    line_id, error)
        if work_order_id > 0:
            try:
                from meta.services.inventory_reservation_service import (
                    InventoryReservationService,
                )
                InventoryReservationService(
                    context.data_source).sync_work_order_components(
                        work_order_id)
            except Exception as error:
                logger.warning(
                    '[inv2] 工单 %s 组件预留同步失败（不阻断写入）: %s',
                    work_order_id, error)

    @staticmethod
    def _expand_components(context: 'ActionContext', work_order_id: int,
                           data: dict) -> None:
        """通用 BO CRUD 建单后展开组件（与服务建单同一入口，幂等重建）。"""
        item_id = data.get('item_id')
        qty = data.get('planned_qty')
        if qty in (None, ''):
            qty = data.get('qty')
        if not work_order_id or item_id in (None, '') or qty in (None, ''):
            return
        try:
            WorkOrderService(context.data_source).expand_components(
                work_order_id, item_id, qty)
        except Exception as error:
            logger.warning(
                '[work_order] 工单 %s 组件展开失败（不阻断写入）: %s',
                work_order_id, error)

