# -*- coding: utf-8 -*-
"""序列号守卫拦截器 —— 序列号主档写前校验（P6a / P59）。

优先级 59（在业务守卫 43–58 之后、PersistenceInterceptor 95 之前）：
  · serial_number 写入：物料必须已启用序列号管理、唯一键
    (item_id, org_id, serial_no)、初始状态必须 defined、状态合法、
    scrapped 为终态不可再改；usage_status 只能由 SerialNumberService 流转。
  · item 写入：require_on_receipt / require_on_issue 为 1 时
    serial_tracked 必须为 1（§3.4 服务层约束）。

口径: 只做写前校验，不回填业务字段；主档当前态由服务层维护。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.serial_number_service import (
    QUALITY_STATUSES,
    SOURCE_TYPES,
    STATUS_DEFINED,
    STATUS_SCRAPPED,
    USAGE_STATUSES,
    SerialNumberError,
    SerialNumberService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT_SERIAL_NUMBER = 'serial_number'
OBJECT_ITEM = 'item'
OBJECTS = (OBJECT_SERIAL_NUMBER, OBJECT_ITEM)
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class SerialNumberGuardInterceptor(Interceptor):
    """序列号主档 / 物料序列号开关守卫。"""

    @property
    def priority(self) -> int:
        return 59

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id in OBJECTS and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        object_id = getattr(context.meta_object, 'id', None)
        service = SerialNumberService(context.data_source)
        try:
            if object_id == OBJECT_ITEM:
                service.validate_item_switches(params, old if old else None)
            else:
                self._guard_serial_number(context, params, old if old else None)
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

    # ------------------------------------------------------------------
    def _guard_serial_number(self, context: 'ActionContext',
                             params: dict, old: dict) -> None:
        existing_id = old.get('id') or context.object_id or params.get('id')
        if old:
            if old.get('usage_status') == STATUS_SCRAPPED:
                raise SerialNumberError('已报废序列号为终态，不可再修改',
                                        field_name='usage_status',
                                        rule='SERIAL_STATUS_TRANSITION_INVALID')
            new_status = params.get('usage_status')
            if new_status is not None \
                    and new_status != old.get('usage_status'):
                raise SerialNumberError(
                    '序列号状态只能通过序列号服务流转，禁止直接修改',
                    field_name='usage_status',
                    rule='SERIAL_STATUS_TRANSITION_INVALID')

        status = params.get('usage_status')
        if not old and status not in (None, STATUS_DEFINED):
            raise SerialNumberError('新建序列号初始状态必须为 defined',
                                    field_name='usage_status',
                                    rule='SERIAL_STATUS_TRANSITION_INVALID')
        if status is not None and status not in USAGE_STATUSES:
            raise SerialNumberError('未知用途状态：%s' % status,
                                    field_name='usage_status',
                                    rule='SERIAL_STATUS_INVALID')
        quality = params.get('quality_status')
        if quality is not None and quality not in QUALITY_STATUSES:
            raise SerialNumberError('未知质量状态：%s' % quality,
                                    field_name='quality_status',
                                    rule='SERIAL_QUALITY_STATUS_INVALID')
        source_type = params.get('source_type')
        if not old and source_type is not None \
                and source_type not in SOURCE_TYPES:
            raise SerialNumberError('未知来源类型：%s' % source_type,
                                    field_name='source_type',
                                    rule='SERIAL_SOURCE_TYPE_INVALID')

        item_id = params.get('item_id', old.get('item_id'))
        org_id = params.get('org_id', old.get('org_id'))
        serial_no = params.get('serial_no', old.get('serial_no'))
        if not old:
            rows = context.data_source.query(
                'SELECT serial_tracked FROM items WHERE id = ?', [item_id])
            if not rows:
                raise SerialNumberError('物料不存在：%s' % item_id,
                                        field_name='item_id',
                                        rule='SERIAL_ITEM_NOT_FOUND')
            if not bool(rows[0].get('serial_tracked')):
                raise SerialNumberError('该物料未启用序列号管理',
                                        field_name='item_id',
                                        rule='SERIAL_ITEM_NOT_TRACKED')
        if item_id and org_id and serial_no:
            rows = context.data_source.query(
                'SELECT id FROM serial_numbers WHERE item_id = ? AND org_id = ? '
                'AND serial_no = ? AND id <> ?',
                [item_id, org_id, serial_no, existing_id or 0])
            if rows:
                raise SerialNumberError(
                    '同一物料同一组织下序列号已存在',
                    field_name='serial_no', rule='SERIAL_DUPLICATE')
