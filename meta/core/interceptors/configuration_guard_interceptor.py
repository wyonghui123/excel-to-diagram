# -*- coding: utf-8 -*-
"""配置结果层守卫拦截器 —— 实例头 / 特征值 / 组件。

优先级 48（在 ConfigRuleGuardInterceptor 47 之后）：
  结果层的状态锁与明细完整性都只依赖自身字段与父实例状态，
  放在最后可避免在尚未通过结构与规则校验的写入上做多余判定。
受管范围：
  configuration           —— 创建 / 更新（状态锁、hash 不可改）、删除（仅 draft）
  configuration_value     —— 创建 / 更新 / 删除（父实例必须 draft、值列互斥）
  configuration_component —— 创建 / 更新 / 删除（父实例必须 draft、键形态、父键存在）
其余对象与动作零开销短路。判定口径见 meta/services/configuration_guard_service.py。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.configuration_guard_service import (
    ConfigurationGuardError,
    ConfigurationGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

HEAD_OBJECT = 'configuration'
VALUE_OBJECT = 'configuration_value'
COMPONENT_OBJECT = 'configuration_component'


class ConfigurationGuardInterceptor(Interceptor):
    """配置实例（R10 / R11）与明细（draft 锁、值列互斥、组件键形态）守卫。"""

    @property
    def priority(self) -> int:
        return 48

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (HEAD_OBJECT, VALUE_OBJECT, COMPONENT_OBJECT):
            return False
        return context.action in ('crud_create', 'crud_update', 'crud_delete')

    def before_action(self, context: 'ActionContext') -> None:
        service = ConfigurationGuardService(context.data_source)
        object_id = getattr(context.meta_object, 'id', None)
        action = context.action

        try:
            if action == 'crud_delete':
                target = context.object_id or (context.params or {}).get('id')
                if object_id == HEAD_OBJECT:
                    service.validate_head_delete(target)
                elif object_id == VALUE_OBJECT:
                    service.validate_value_delete(target)
                else:
                    service.validate_component_delete(target)
                return

            data, exclude_id = self._effective_data(context)
            if object_id == HEAD_OBJECT:
                service.validate_head_write(data, exclude_id=exclude_id)
            elif object_id == VALUE_OBJECT:
                service.validate_value_write(data, exclude_id=exclude_id)
            else:
                service.validate_component_write(data, exclude_id=exclude_id)
        except ConfigurationGuardError as e:
            from meta.core.exceptions import ValidationFailedError

            raise ValidationFailedError(
                message=str(e),
                details=[{
                    'field_name': e.field_name,
                    'rule': e.rule,
                    'message': str(e),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass

    @staticmethod
    def _effective_data(context: 'ActionContext') -> tuple:
        """更新可能是部分字段：与旧行合并还原「更新后的有效行」。"""
        params = dict(context.params or {})
        if context.action != 'crud_update':
            return params, None
        merged = dict(context.old_data or {})
        merged.update(params)
        return merged, context.object_id or params.get('id')
