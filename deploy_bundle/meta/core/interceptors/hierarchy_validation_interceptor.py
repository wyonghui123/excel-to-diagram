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

        # [FIX BUG-V011 2026-06-26] 如果 schema 中所有 child 关联都是 cascade_delete=true
        # 跳过本校验, 让 cascade_service 真正执行级联删除
        # 案例: SDLKFJL (product 335) 含 1 个 version, 旧代码报"存在 1 个子元素"
        #       实际 product.yaml associations[].cascade_delete: true 应级联
        if self._all_children_cascade_delete(context.object_type):
            logger.debug(
                f'[HierarchyValidation] skip validate_no_children for {context.object_type}({context.object_id}) '
                f'- all children are cascade_delete=true'
            )
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

    def _all_children_cascade_delete(self, object_type: str) -> bool:
        """[FIX BUG-V011] 检查 object_type 的所有 child 关联是否都是 cascade_delete=true.

        读 schema (yaml) 的 associations, 检查每条关联的 cascade_delete.
        支持 dict 和 AssociationDefinition 两种格式.
        """
        try:
            from meta.core.models import registry
            meta = registry.get(object_type)
            if not meta:
                return True

            assocs = getattr(meta, 'associations', None) or []
            if isinstance(assocs, dict):
                assocs = list(assocs.values())

            def _get_assoc_field(a, field, default=None):
                if isinstance(a, dict):
                    return a.get(field, default)
                return getattr(a, field, default)

            composition_children = [
                a for a in assocs
                if _get_assoc_field(a, 'type') == 'composition'
            ]
            if not composition_children:
                return True
            return all(
                _get_assoc_field(a, 'cascade_delete', False)
                for a in composition_children
            )
        except Exception as e:
            logger.debug(f'[BUG-V011] _all_children_cascade_delete check failed: {e}')
            return False
