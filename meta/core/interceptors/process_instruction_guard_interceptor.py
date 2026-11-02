# -*- coding: utf-8 -*-
"""过程指令守卫拦截器 —— 单表双形态（text / parameter）的写前校验。

优先级 55（作业定义守卫 54 之后、持久化 95 之前）：
  · text 形态：`title` / `content` 必填，参数列必须为空。
  · parameter 形态：`parameter_code` / `parameter_name` / `data_type` /
    `direction` 必填，文本列必须为空；numeric 参数校验 min ≤ target ≤ max，
    `set` 方向必须有目标值；`uom_id` 仅 numeric 可填。
  · 绑定资源须为 machine / facility / tool。

口径: 只做写前校验，不回填业务字段；唯一索引 / 部分唯一索引由迁移兜底。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.process_instruction_service import (
    ProcessInstructionError, ProcessInstructionService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT = 'process_instruction'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class ProcessInstructionGuardInterceptor(Interceptor):
    """过程指令的形态 / 参数矩阵守卫。"""

    @property
    def priority(self) -> int:
        return 55

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        return object_id == OBJECT and context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = ProcessInstructionService(context.data_source)
        params = context.params if isinstance(context.params, dict) else {}
        old = dict(context.old_data or {})
        try:
            service.validate(params, old if old else None)
        except ProcessInstructionError as error:
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
