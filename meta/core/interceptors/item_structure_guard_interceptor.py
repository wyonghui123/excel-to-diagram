# -*- coding: utf-8 -*-
"""物料结构守卫拦截器 —— 结构头 / 结构行 / 物料角色的统一写入入口。

优先级 46（在 HierarchyValidationInterceptor 45 之后）：
  结构与行的规则都依赖层级 / 唯一性校验已完成的前置状态（如父键、行号），
  放在 45 之后可避免在无效数据上做图遍历。
受管范围：
  item              —— 创建 / 更新（M1 角色与类型一致）
  item_structure    —— 创建 / 更新（S1–S3）、删除（D1）
  item_structure_line —— 创建 / 更新（R1 / R3–R8 / R11）、删除（R15 规则条件项引用）
  item_structure_attribute —— 创建 / 更新（A1–A4）
其余对象与动作零开销短路。判定口径见 meta/services/item_structure_guard_service.py。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 uom_conversion / payment_term 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.item_structure_guard_service import (
    ItemStructureGuardError,
    ItemStructureGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

ITEM_OBJECT = 'item'
STRUCTURE_OBJECT = 'item_structure'
LINE_OBJECT = 'item_structure_line'
ATTRIBUTE_OBJECT = 'item_structure_attribute'
_WRITE_ACTIONS = ('crud_create', 'crud_update')


class ItemStructureGuardInterceptor(Interceptor):
    """物料结构头（S1–S3 / D1）、结构行（R1 / R3–R8 / R11）、模型特征（A1–A4）与物料角色（M1）守卫。"""

    @property
    def priority(self) -> int:
        return 46

    def should_execute(self, context: 'ActionContext') -> bool:
        object_id = getattr(context.meta_object, 'id', None)
        action = context.action
        if object_id == ITEM_OBJECT:
            return action in _WRITE_ACTIONS
        if object_id == STRUCTURE_OBJECT:
            return action in _WRITE_ACTIONS or action == 'crud_delete'
        if object_id == LINE_OBJECT:
            return action in _WRITE_ACTIONS or action == 'crud_delete'
        if object_id == ATTRIBUTE_OBJECT:
            return action in _WRITE_ACTIONS
        return False

    def before_action(self, context: 'ActionContext') -> None:
        service = ItemStructureGuardService(context.data_source)
        object_id = getattr(context.meta_object, 'id', None)

        try:
            if object_id == ITEM_OBJECT:
                data, _ = self._effective_data(context)
                service.validate_item_write(data)
            elif object_id == STRUCTURE_OBJECT and context.action == 'crud_delete':
                service.validate_structure_delete(self._delete_target(context))
            elif object_id == LINE_OBJECT and context.action == 'crud_delete':
                service.validate_line_delete(self._delete_target(context))
            else:
                data, exclude_id = self._effective_data(context)
                if object_id == STRUCTURE_OBJECT:
                    service.validate_structure_write(data, exclude_id=exclude_id)
                elif object_id == ATTRIBUTE_OBJECT:
                    service.validate_attribute_write(data, exclude_id=exclude_id)
                else:
                    service.validate_line_write(data, exclude_id=exclude_id)
        except ItemStructureGuardError as e:
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

    @staticmethod
    def _delete_target(context: 'ActionContext'):
        return context.object_id or (context.params or {}).get('id')
