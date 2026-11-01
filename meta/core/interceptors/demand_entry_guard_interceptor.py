# -*- coding: utf-8 -*-
"""需求入口守卫拦截器 —— 提交取号、免审批直落、行级合法性（M1）。

优先级 52（territory 50 / shipment 51 之后、PersistenceInterceptor 95 之前）：
before_action 修改的入参由随后的持久化链路消费，状态机规则在 ActionExecutor
内执行，因此「提交即免审批」只改一次 status，不额外写 SQL、不破坏审计链。

受管范围:
  service_request / requisition —— crud_create 补单号；crud_update 且 status
    目标为 submitted 时补号 + 免审批直落
  service_request_line          —— crud_create / crud_update 的行级必填
其余对象与动作零开销短路。

单据类型（T-D20）由 DocumentTypeGuardInterceptor 统一处理，不在本拦截器内。

口径:
  · 取号：业务键在创建时生成（`{前缀}-{YYYYMMDD}-{流水}`）；提交时若仍缺号再补，
    均为事务内取号，极端并发由数据库唯一索引兜底；
  · 免审批：目录项 requires_approval=false 且 approval_policy 为空 → 直接落 approved；
    requisition 在 M1 无审批策略载体 → 免审批；
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
_STATUS_SUBMITTED = 'submitted'
_STATUS_DRAFT = 'draft'


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
            return context.action in _WRITE_ACTIONS
        if object_id in HEADER_OBJECTS:
            return context.action in _WRITE_ACTIONS
        return False

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        service = DemandEntryService(context.data_source)
        try:
            if object_id == LINE_OBJECT:
                service.validate_line(object_id, dict(context.params or {}))
                return
            if context.action == 'crud_create':
                self._allocate_on_create(object_id, context.params or {}, service)
                return
            self._guard_submit(context, object_id, service)
        except ValueError as error:
            self._raise_validation(error)

    def after_action(self, context: 'ActionContext') -> None:
        """免审批在 before_action 改写 status 完成，无需后置动作。"""
        return

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
