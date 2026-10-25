# -*- coding: utf-8 -*-
"""类型字典守卫拦截器 —— type_definition 的写入入口。

覆盖范围:
  type_definition 创建 / 更新 —— I1–I4 层级与字段适用 + I6 归属对象/层级不可变

优先级 47（在 SalesConfigGuard 46 之后）：销售配置守卫先处理控制参数与
行类型确定表，本守卫只关心类型字典自身。其余对象 / 动作零开销短路。

写入成功后失效 `get_line_type_resolver()` 的内存缓存：document_type / line_type
两个切片面已降级为只读视图，其写路径不再存在，
若不在类型字典上做失效，行类型确定缓存会一直停在旧值。

判定口径见 meta/services/type_definition_guard_service.py（I1–I4 / I6）。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与 payment_term / sales_config 守卫同一限制）。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.services.type_definition_guard_service import (
    TypeDefinitionGuardError,
    TypeDefinitionGuardService,
)

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

OBJECT_ID = 'type_definition'
_WRITE_ACTIONS = ('crud_create', 'crud_update', 'crud_delete')


class TypeDefinitionGuardInterceptor(Interceptor):
    """类型字典写前守卫（I1–I4 / I6 + 缓存失效）。"""

    @property
    def priority(self) -> int:
        return 47

    def should_execute(self, context: 'ActionContext') -> bool:
        return (getattr(context.meta_object, 'id', None) == OBJECT_ID
                and context.action in _WRITE_ACTIONS)

    def before_action(self, context: 'ActionContext') -> None:
        params = dict(context.params or {})
        if context.action == 'crud_delete':
            self._validate_delete(context.object_id or params.get('id'),
                                  context.data_source)
            return

        merged = dict(context.old_data or {})
        merged.update(params)
        if context.action == 'crud_create':
            merged = self._with_schema_defaults(context.meta_object, merged)

        exclude_id = None
        if context.action == 'crud_update':
            exclude_id = context.object_id or params.get('id')

        try:
            TypeDefinitionGuardService(context.data_source).validate_write(
                merged, exclude_id=exclude_id)
        except TypeDefinitionGuardError as e:
            self._raise_validation(e)

    def _validate_delete(self, type_id, data_source) -> None:
        try:
            TypeDefinitionGuardService(data_source).validate_delete(type_id)
        except TypeDefinitionGuardError as e:
            self._raise_validation(e)

    @staticmethod
    def _raise_validation(error: TypeDefinitionGuardError) -> None:
        from meta.core.exceptions import ValidationFailedError

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
        try:
            from meta.services.line_type_service import (
                get_line_type_resolver,
            )
            get_line_type_resolver().invalidate()
        except Exception as e:  # 缓存失效失败不应回滚已成功的写入
            logger.warning(f'[type_definition_guard] 行类型确定缓存失效失败: {e}')

    @staticmethod
    def _with_schema_defaults(meta_object, data: dict) -> dict:
        """创建时补 schema 默认值，避免「未传 → 视为空」误伤 I1/I2。

        例如 header 未传 document_category 时，数据库默认值 standard 会在落库时
        生效；守卫若按空值拒绝，同一份数据走 API 与走表单会得到不同结论。
        """
        filled = dict(data)
        for field in getattr(meta_object, 'fields', []) or []:
            column = getattr(field, 'db_column', None) or field.id
            if column in filled and filled[column] is not None:
                continue
            default = getattr(field, 'default', None)
            if column not in filled and default is not None:
                filled[column] = default
        return filled
