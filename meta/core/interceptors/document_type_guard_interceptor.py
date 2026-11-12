# -*- coding: utf-8 -*-
"""单据类型守卫拦截器（平台层规范 T-D20）。

优先级 52（与需求入口守卫同段，均在 PersistenceInterceptor 95 之前）。
对**所有**声明 `document_type_id` 的对象生效——新增单据只需在 YAML 的
`aspects` 里引用 `document_type_aspect`，无需改代码。

受管动作:
  crud_create / crud_update —— 创建必填、归属域（scope_bo + level）、active、
  离开草稿后不可修改。其余对象与动作零开销短路。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.exceptions import ValidationFailedError
from meta.core.interceptors.base import Interceptor
from meta.services.document_type_guard_service import (
    DocumentTypeGuardService,
    object_declares_document_type,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

_WRITE_ACTIONS = ('crud_create', 'crud_update')


class DocumentTypeGuardInterceptor(Interceptor):
    """业务单据头的单据类型守卫。"""

    @property
    def priority(self) -> int:
        return 52

    def should_execute(self, context: 'ActionContext') -> bool:
        if context.action not in _WRITE_ACTIONS:
            return False
        return object_declares_document_type(getattr(context, 'meta_object', None))

    def before_action(self, context: 'ActionContext') -> None:
        object_type = getattr(context.meta_object, 'id', None)
        service = DocumentTypeGuardService(context.data_source)
        try:
            service.validate(
                object_type, dict(context.params or {}), context.old_data,
                is_create=context.action == 'crud_create')
        except ValueError as error:
            raise ValidationFailedError(
                message=str(error),
                details=[{
                    'field_name': 'document_type_id',
                    'rule': 'document_type',
                    'message': str(error),
                    'i18n_key': '',
                    'params': {},
                }],
            )

    def after_action(self, context: 'ActionContext') -> None:
        """校验在 before_action 完成，无需后置动作。"""
        return
