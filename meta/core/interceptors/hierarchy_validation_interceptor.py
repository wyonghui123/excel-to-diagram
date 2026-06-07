# -*- coding: utf-8 -*-
import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class HierarchyValidationInterceptor(Interceptor):
    """
    层级校验拦截器

    before_action 阶段对 update/delete 操作进行层级约束校验：
    1. 更新时 — 父元素不可变校验（防止变更父级关联字段）
    2. 删除时 — 子元素存在校验（防止删除有子元素的记录）

    force=true 参数可跳过删除校验。
    """

    @property
    def name(self) -> str:
        return "hierarchy_validation"

    @property
    def priority(self) -> int:
        return 45

    def before_action(self, context: 'ActionContext') -> None:
        if context.is_update_action:
            self._validate_update(context)
        elif context.is_delete_action:
            self._validate_delete(context)

    def after_action(self, context: 'ActionContext') -> None:
        pass

    def _handle_validation_result(self, context: 'ActionContext', result) -> None:
        """统一的层级校验结果处理 — 消除 _validate_update/_delete 中完全重复的 15 行错误收集代码"""
        if result.valid:
            return

        if 'violations' not in context.extra:
            context.extra['violations'] = []
        context.extra['violations'].append({
            'type': 'hierarchy_validation',
            'message': result.message,
            'error_code': result.error_code,
            'details': result.details,
        })
        context.result = type(context.result)(
            success=False,
            data=None,
            message=result.message,
            errors=[result.message],
        )

    def _validate_update(self, context: 'ActionContext') -> None:
        try:
            from meta.services.hierarchy_validation_service import validate_update
            if context.old_data is None:
                return

            result = validate_update(
                context.object_type,
                context.old_data,
                context.params,
                context.data_source,
            )
            self._handle_validation_result(context, result)
        except Exception as e:
            logger.debug(f"[HierarchyValidation] update validation skipped: {e}")

    def _validate_delete(self, context: 'ActionContext') -> None:
        force = context.params.get('force', False)
        if force:
            return

        try:
            from meta.services.hierarchy_validation_service import validate_delete
            obj_id = context.object_id
            if obj_id is None:
                return

            result = validate_delete(
                context.object_type,
                obj_id,
                context.data_source,
            )
            self._handle_validation_result(context, result)
        except Exception as e:
            logger.debug(f"[HierarchyValidation] delete validation skipped: {e}")
