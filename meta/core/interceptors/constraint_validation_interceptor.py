# -*- coding: utf-8 -*-
"""
约束校验拦截器 - 集成 ConstraintEngine 到拦截器链

在 BO 操作前后执行约束检查：
- immutable: 创建后不可修改
- no_delete: 不可删除
- unique_scope: 范围内唯一性

优先级 42（在 FieldPolicy 40 之后、HierarchyValidation 45 之前）
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.core.constraint_engine import ConstraintEngine
from meta.core.validation_messages import ValidationDetail, ValidationMessageRegistry

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class ConstraintValidationInterceptor(Interceptor):
    @property
    def priority(self) -> int:
        return 42

    def before_action(self, context: 'ActionContext') -> None:
        engine = ConstraintEngine()
        violations = engine.validate(context)
        if violations:
            details = []
            for v in violations:
                i18n_key = f"validation.field.{v.constraint_type}"
                detail = ValidationDetail(
                    field_id=v.field_id,
                    rule=v.constraint_type,
                    message=v.message,
                    i18n_key=i18n_key,
                )
                details.append(detail)
            from meta.core.exceptions import ValidationFailedError
            raise ValidationFailedError(
                message="; ".join(v.message for v in violations),
                details=[d.to_dict() for d in details]
            )

    def after_action(self, context: 'ActionContext') -> None:
        pass
