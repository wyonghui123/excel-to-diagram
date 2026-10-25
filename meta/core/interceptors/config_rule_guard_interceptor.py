# -*- coding: utf-8 -*-
"""配置规则守卫拦截器 —— 规则头与条件项的写入入口。

优先级 47（在 ItemStructureGuardInterceptor 46 之后）：
  规则校验依赖结构树可达性，须等结构 / 行已通过前置校验后再做图遍历。
受管范围：
  config_rule      —— 创建 / 更新（R9 + structure_id 锁定）
  config_rule_term —— 创建 / 更新（R8 / R16 / §5.5 形状）
其余对象与动作零开销短路。判定口径见 meta/services/config_rule_guard_service.py。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.config_rule_guard_service import (
    ConfigRuleGuardError,
    ConfigRuleGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

RULE_OBJECT = 'config_rule'
TERM_OBJECT = 'config_rule_term'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class ConfigRuleGuardInterceptor(Interceptor):
    """配置规则头（R9）与条件项（R8 / R16 / 形状）守卫。"""

    @property
    def priority(self) -> int:
        return 47

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in (RULE_OBJECT, TERM_OBJECT):
            return False
        return context.action in _WRITE_ACTIONS

    def before_action(self, context: 'ActionContext') -> None:
        service = ConfigRuleGuardService(context.data_source)
        object_id = getattr(context.meta_object, 'id', None)
        data, exclude_id = self._effective_data(context)

        try:
            if object_id == RULE_OBJECT:
                service.validate_rule_write(data, exclude_id=exclude_id)
            else:
                service.validate_term_write(data, exclude_id=exclude_id)
        except ConfigRuleGuardError as e:
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
