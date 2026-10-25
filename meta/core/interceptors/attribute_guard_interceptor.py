# -*- coding: utf-8 -*-
"""属性字典守卫拦截器 —— 字典表与字典桥接表的写入 / 删除前置校验。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md §3 / §4 / §6

优先级 45（紧随约束校验 42 / 业务守卫 43-44 之后）；仅对下列对象生效
（should_execute 短路，其余对象 / 动作零开销）。
  - 创建 / 更新：
      attribute_definition / attribute_scope → 准入 lint
      party_attribute_value                  → 通用值校验
      item_attribute_value                   → 平台层限定 + attr_code 与字典编码一致 + 通用值校验
  - 删除：只拦 attribute_definition —— 被引用时禁止删除，引导改为停用
判定口径见 meta/services/attribute_lint_service.py / attribute_value_service.py /
attribute_impact_service.py。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.attribute_impact_service import (
    AttributeImpactError,
    AttributeImpactService,
)
from meta.services.attribute_lint_service import AttributeLintError, AttributeLintService
from meta.services.attribute_value_service import (
    AttributeValueError,
    AttributeValueService,
    ItemAttributeValueService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

#: 受本守卫约束的对象
GUARDED_OBJECTS = ('attribute_definition', 'attribute_scope',
                   'party_attribute_value', 'item_attribute_value')
_GUARDED_ACTIONS = ('crud_create', 'crud_update')
#: 删除只对定义层设防（范围的删除不破坏值行语义）
_DELETE_GUARDED = ('attribute_definition',)


class AttributeGuardInterceptor(Interceptor):
    """属性字典准入守卫（P45）。"""

    @property
    def priority(self) -> int:
        return 45

    def should_execute(self, context: 'ActionContext') -> bool:
        """字典三表的创建 / 更新，以及定义层的删除；其余零开销短路。"""
        object_id = getattr(context.meta_object, 'id', None)
        if object_id not in GUARDED_OBJECTS:
            return False
        if context.action in _GUARDED_ACTIONS:
            return True
        return context.action == 'crud_delete' and object_id in _DELETE_GUARDED

    def before_action(self, context: 'ActionContext') -> None:
        object_id = getattr(context.meta_object, 'id', None)
        params = dict(context.params or {})

        if context.action == 'crud_delete':
            attribute_id = (context.object_id
                            or (context.old_data or {}).get('id')
                            or params.get('id'))
            try:
                AttributeImpactService(context.data_source).assert_not_referenced(attribute_id)
            except AttributeImpactError as e:
                self._reject(e)
            return

        if context.action == 'crud_update':
            # 更新常为部分字段：与旧行合并还原「更新后的有效行」
            merged = dict(context.old_data or {})
            merged.update(params)
            data = merged
            data.setdefault('id', context.object_id)
            exclude_id = context.object_id
        else:
            data = params
            exclude_id = None

        service = AttributeLintService(context.data_source)
        try:
            if object_id == 'attribute_definition':
                service.check_definition(data, exclude_id=exclude_id)
            elif object_id == 'attribute_scope':
                service.check_scope(data)
            elif object_id == 'item_attribute_value':
                ItemAttributeValueService(context.data_source).validate_write(data)
            else:
                AttributeValueService(context.data_source).validate_write(data)
        except (AttributeLintError, AttributeValueError) as e:
            self._reject(e)

    @staticmethod
    def _reject(error) -> None:
        """把服务层错误统一转成 ValidationFailedError（带 rule / field_name 明细）。"""
        from meta.core.exceptions import ValidationFailedError

        message = str(error)
        raise ValidationFailedError(
            message=message,
            details=[{
                'field_name': error.field_name,
                'rule': error.rule,
                'message': message,
                'i18n_key': '',
                'params': {},
            }],
        )

    def after_action(self, context: 'ActionContext') -> None:
        pass
