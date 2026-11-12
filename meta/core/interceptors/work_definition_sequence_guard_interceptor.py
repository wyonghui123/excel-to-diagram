# -*- coding: utf-8 -*-
"""作业定义序列守卫拦截器 —— 路线分支 / 并行 / 替代的写前校验（P5）。

优先级 57（批次守卫 56 之后、持久化 95 之前）：
  · 序列写入：G1–G10（std / parallel / alternative 边界、std 工序存在性、
    branch 下 priority 唯一、批量区间、序列内工序号、图成环、边界工序归属）。
  · 工序写入：G11（被 branch/return 引用的工序号不得改号）与边界冲突。

口径: 只做写前校验，不回填业务字段；部分唯一索引由迁移兜底。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.work_definition_sequence_service import (
    WorkDefinitionSequenceError,
    WorkDefinitionSequenceService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT_SEQUENCE = 'work_definition_sequence'
OBJECT_OPERATION = 'work_definition_operation'
OBJECTS = (OBJECT_SEQUENCE, OBJECT_OPERATION)
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class WorkDefinitionSequenceGuardInterceptor(Interceptor):
    """作业定义序列 / 工序守卫。"""

    @property
    def priority(self) -> int:
        return 57

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id in OBJECTS and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = WorkDefinitionSequenceService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        object_id = getattr(context.meta_object, 'id', None)
        try:
            if object_id == OBJECT_SEQUENCE:
                service.validate_sequence(params, old if old else None)
            else:
                service.validate_operation(params, old if old else None)
        except WorkDefinitionSequenceError as error:
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
