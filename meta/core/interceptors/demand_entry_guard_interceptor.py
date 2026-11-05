# -*- coding: utf-8 -*-
"""需求入口守卫拦截器 —— 提交取号、免审批直落、行级合法性（M1）。

优先级 52（territory 50 / shipment 51 之后、PersistenceInterceptor 95 之前）：
before_action 修改的入参由随后的持久化链路消费，状态机规则在 ActionExecutor
内执行，因此「提交即免审批」只改一次 status，不额外写 SQL、不破坏审计链。

受管范围:
  service_request / requisition —— crud_create 补单号；crud_update 且 status
    目标为 submitted 时补号 + 免审批直落；需审批时在 after_action 落一条
    `tasks(type=approval)`（S7 / S-D5，决策动作见 demand_entry_decision）
  service_request_line          —— crud_create / crud_update 的行级必填
其余对象与动作零开销短路。

单据类型（T-D20）由 DocumentTypeGuardInterceptor 统一处理，不在本拦截器内。

口径:
  · 取号：业务键在创建时生成（`{前缀}-{YYYYMMDD}-{流水}`）；提交时若仍缺号再补，
    均为事务内取号，极端并发由数据库唯一索引兜底；
  · 免审批：目录项 requires_approval=false 且 approval_policy 为空 → 直接落 approved；
    requisition 在 M1 无审批策略载体 → 免审批；
  · 需审批：单据保持 submitted，after_action 建审批待办（单据落库后才建，
    避免持久化失败留下孤儿任务）；
  · 取消不回滚下游：本拦截器不处理 cancel，交由状态机规则只改本条状态。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.demand_entry_service import (
    REQUISITION_OBJECT,
    SERVICE_REQUEST_OBJECT,
    DemandEntryService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

LINE_OBJECT = 'service_request_line'
HEADER_OBJECTS = (SERVICE_REQUEST_OBJECT, REQUISITION_OBJECT)
_WRITE_ACTIONS = ('crud_create', 'crud_update')
_DELETE_ACTION = 'crud_delete'
_STATUS_SUBMITTED = 'submitted'
_STATUS_DRAFT = 'draft'
_APPROVAL_FLAG = 'demand_entry_approval'


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


class DemandEntryGuardInterceptor(Interceptor):
    """需求入口（服务请求 / 请购）提交守卫。"""

    @property
    def priority(self) -> int:
        return 52

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id == LINE_OBJECT:
            return context.action in _WRITE_ACTIONS + (_DELETE_ACTION,)
        if object_id in HEADER_OBJECTS:
            return context.action in _WRITE_ACTIONS + (_DELETE_ACTION,)
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        service = DemandEntryService(context.data_source)
        try:
            if object_id == LINE_OBJECT:
                if context.action != _DELETE_ACTION:
                    service.validate_line(object_id, dict(context.params or {}))
                return
            if context.action == 'crud_create':
                self._allocate_on_create(object_id, context.params or {}, service)
                return
            self._guard_submit(context, object_id, service)
        except ValueError as error:
            self._raise_validation(error)

    def after_action(self, context: 'ActionContext') -> None:
        """写后同步：需审批的提交补建待办；服务请求备件行同步 soft 预留。"""
        result = getattr(context, 'result', None)
        if result is not None and not getattr(result, 'success', True):
            return
        self._create_approval_task(context)
        self._sync_service_request_reservations(context)

    def _create_approval_task(self, context: 'ActionContext') -> None:
        extra = getattr(context, 'extra', None) or {}
        info = extra.pop(_APPROVAL_FLAG, None)
        if not info:
            return
        actor = str(getattr(context, 'user_id', '') or
                    getattr(context, 'user_name', '') or '')
        try:
            DemandEntryService(context.data_source).create_approval_task(
                info['object_type'], info['record_id'], actor=actor)
        except Exception as error:  # noqa: BLE001 - 建任务失败不阻断已完成的提交
            logger.warning('[DemandEntry] 审批任务创建失败: %s', error)

    def _sync_service_request_reservations(self, context: 'ActionContext') -> None:
        """服务请求写后同步备件承诺（失败只告警，不阻断已完成的写入）。"""
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (SERVICE_REQUEST_OBJECT, LINE_OBJECT):
            return
        try:
            self._apply_reservation_sync(context, object_id)
        except Exception as error:  # noqa: BLE001
            logger.warning('[DemandEntry] 服务请求预留同步失败: %s', error)

    def _apply_reservation_sync(self, context: 'ActionContext',
                                object_id: str) -> None:
        from meta.services.inventory_reservation_service import (
            SERVICE_REQUEST_SOURCE_TYPE, InventoryReservationService,
        )

        service = InventoryReservationService(context.data_source)
        old = dict(getattr(context, 'old_data', None) or {})
        params = dict(getattr(context, 'params', None) or {})
        if context.action == _DELETE_ACTION:
            if object_id == LINE_OBJECT:
                request_id = old.get('request_id')
                line_id = old.get('id')
                if request_id and line_id:
                    service.release_by_source(
                        SERVICE_REQUEST_SOURCE_TYPE, request_id,
                        line_id=line_id, reason='服务请求行删除')
            else:
                request_id = params.get('id')
                if request_id:
                    service.release_by_source(
                        SERVICE_REQUEST_SOURCE_TYPE, request_id,
                        reason='服务请求删除')
            return
        if object_id == LINE_OBJECT:
            request_id = params.get('request_id') or old.get('request_id')
        else:
            request_id = params.get('id')
        if request_id:
            service.sync_service_request_reservations(request_id)

    # ---------------- 创建 ----------------

    def _allocate_on_create(self, object_type: str, payload: dict,
                            service: DemandEntryService) -> None:
        """创建时补业务键单号（业务键校验在 ActionExecutor 内要求非空）。"""
        document_no = service.allocate_document_no(object_type, payload)
        if document_no:
            column = 'request_no' if object_type == SERVICE_REQUEST_OBJECT else 'requisition_no'
            payload[column] = document_no
            logger.info('[DemandEntry] %s 创建取号 %s', object_type, document_no)

    # ---------------- 提交 ----------------

    def _guard_submit(self, context: 'ActionContext', object_type: str,
                      service: DemandEntryService) -> None:
        payload = context.params or {}
        if payload.get('status') != _STATUS_SUBMITTED:
            return

        current_status = (context.old_data or {}).get('status')
        if _blank(current_status):
            current_status = _STATUS_DRAFT
        if current_status != _STATUS_DRAFT:
            # 非「草稿 → 提交」的更新，不接管
            return

        document_no = service.allocate_document_no(object_type, payload)
        if document_no:
            column = 'request_no' if object_type == SERVICE_REQUEST_OBJECT else 'requisition_no'
            payload[column] = document_no
            logger.info('[DemandEntry] %s id=%s 提交取号 %s',
                        object_type, payload.get('id'), document_no)

        if service.is_approval_exempt(object_type, payload.get('id')):
            payload['status'] = 'approved'
            logger.info('[DemandEntry] %s id=%s 审批策略为空，提交即免审批',
                        object_type, payload.get('id'))
            return

        extra = getattr(context, 'extra', None)
        if extra is not None:
            extra[_APPROVAL_FLAG] = {
                'object_type': object_type,
                'record_id': payload.get('id'),
            }

    # ---------------- 错误转换 ----------------

    @staticmethod
    def _raise_validation(error: ValueError) -> None:
        raise ValidationFailedError(
            message=str(error),
            details=[{
                'field_name': '',
                'rule': 'demand_entry',
                'message': str(error),
                'i18n_key': '',
                'params': {},
            }],
        )
