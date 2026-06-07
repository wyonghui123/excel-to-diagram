# -*- coding: utf-8 -*-
"""
枚举保护拦截器

基于 Oracle 三级配置级别设计，保护枚举类型和枚举值的完整性：

1. 系统枚举保护（category = 'system'）
   - 不可修改
   - 不可删除

2. 锁定枚举保护（mutability = 'locked'）
   - 不可添加新值
   - 不可修改现有值
   - 不可删除值

3. 系统预置值保护（is_system = 1）
   - 不可删除

注意：当前实现为 MVP，仅支持基本的 system/business 区分
后续可扩展支持 Oracle 三级配置级别：
- system + locked: 完全锁定
- system + extensible: 可添加，不可修改预置
- business + editable: 完全可编辑
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionResult

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class EnumProtectionInterceptor(Interceptor):
    """
    枚举保护拦截器

    优先级: 35
    在 DataPermissionInterceptor 之后执行，在 HierarchyValidationInterceptor 之前

    保护规则：
    1. 系统枚举（category='system'）：不可修改/删除
    2. 锁定枚举的值（mutability='locked'）：不可增删改
    3. 系统预置值（is_system=1）：不可删除
    """

    @property
    def name(self) -> str:
        return "enum_protection"

    @property
    def priority(self) -> int:
        return 35

    def before_action(self, context: 'ActionContext') -> None:
        """前置校验"""
        object_type = context.object_type

        if object_type not in ('enum_type', 'enum_value'):
            return

        if context.is_create_action:
            self._validate_create(context)
        elif context.is_update_action:
            self._validate_update(context)
        elif context.is_delete_action:
            self._validate_delete(context)

    def after_action(self, context: 'ActionContext') -> None:
        """后置处理"""
        pass

    def _validate_create(self, context: 'ActionContext') -> None:
        """创建校验 - 锁定枚举不可添加值"""
        if context.object_type != 'enum_value':
            return

        enum_type_id = context.params.get('enum_type_id')
        if not enum_type_id:
            return

        try:
            enum_type = self._get_enum_type(context, enum_type_id)
            if not enum_type:
                return

            if enum_type.get('mutability') == 'locked':
                context.result = ActionResult(
                    success=False,
                    data=None,
                    message="该枚举类型已锁定，不可添加值",
                    errors=["ENUM_LOCKED"],
                )
                logger.warning(
                    f"[EnumProtection] Blocked create enum_value: "
                    f"enum_type={enum_type_id} is locked"
                )
        except Exception as e:
            logger.debug(f"[EnumProtection] Create validation skipped: {e}")

    def _validate_update(self, context: 'ActionContext') -> None:
        """更新校验"""
        if context.object_type == 'enum_type':
            self._validate_enum_type_update(context)
        elif context.object_type == 'enum_value':
            self._validate_enum_value_update(context)

    def _validate_delete(self, context: 'ActionContext') -> None:
        """删除校验"""
        if context.object_type == 'enum_type':
            self._validate_enum_type_delete(context)
        elif context.object_type == 'enum_value':
            self._validate_enum_value_delete(context)

    def _validate_enum_type_immutable(self, context: 'ActionContext', action_name: str = '修改') -> bool:
        """检查系统枚举不可变 — 消除 _validate_enum_type_update/_delete 中重复的 system 检查"""
        old_data = context.old_data
        if not old_data:
            return False

        if old_data.get('category') == 'system':
            context.result = ActionResult(
                success=False,
                data=None,
                message=f"系统枚举不可{action_name}",
                errors=["SYSTEM_ENUM_IMMUTABLE"],
            )
            logger.warning(
                f"[EnumProtection] Blocked {action_name} enum_type: "
                f"id={context.object_id} is system enum"
            )
            return True
        return False

    def _validate_enum_type_update(self, context: 'ActionContext') -> None:
        """枚举类型更新校验 - 系统枚举不可修改"""
        self._validate_enum_type_immutable(context, '修改')

    def _validate_enum_type_delete(self, context: 'ActionContext') -> None:
        """枚举类型删除校验"""
        if self._validate_enum_type_immutable(context, '删除'):
            return

        old_data = context.old_data
        if not old_data:
            return

        enum_type_id = context.object_id or old_data.get('id')

        has_values = self._has_enum_values(context, enum_type_id)
        if has_values:
            context.result = ActionResult(
                success=False,
                data=None,
                message=f"该枚举类型下有枚举值，无法删除",
                errors=["HAS_VALUES"],
            )
            logger.warning(
                f"[EnumProtection] Blocked delete enum_type: "
                f"id={enum_type_id} has values"
            )

    def _check_enum_locked(self, context: 'ActionContext', enum_type_id: str, action_name: str = '修改') -> bool:
        """检查枚举类型是否已锁定 — 消除 _validate_enum_value_update/_delete 中重复的 locked 检查"""
        try:
            enum_type = self._get_enum_type(context, enum_type_id)
            if not enum_type:
                return False

            if enum_type.get('mutability') == 'locked':
                context.result = ActionResult(
                    success=False,
                    data=None,
                    message=f"该枚举类型已锁定，不可{action_name}值",
                    errors=["ENUM_LOCKED"],
                )
                logger.warning(
                    f"[EnumProtection] Blocked {action_name} enum_value: "
                    f"enum_type={enum_type_id} is locked"
                )
                return True
        except Exception as e:
            logger.debug(f"[EnumProtection] Enum value validation skipped: {e}")
        return False

    def _validate_enum_value_update(self, context: 'ActionContext') -> None:
        """枚举值更新校验 - 锁定枚举不可修改"""
        old_data = context.old_data
        if not old_data:
            return

        enum_type_id = context.params.get('enum_type_id') or old_data.get('enum_type_id')
        if not enum_type_id:
            return

        self._check_enum_locked(context, enum_type_id, '修改')

    def _validate_enum_value_delete(self, context: 'ActionContext') -> None:
        """枚举值删除校验 - 系统预置值不可删除，锁定枚举不可删除"""
        old_data = context.old_data
        if not old_data:
            return

        enum_type_id = old_data.get('enum_type_id')
        if not enum_type_id:
            return

        if old_data.get('is_system') == 1:
            context.result = ActionResult(
                success=False,
                data=None,
                message="系统预置值不可删除",
                errors=["SYSTEM_VALUE_IMMUTABLE"],
            )
            logger.warning(
                f"[EnumProtection] Blocked delete enum_value: "
                f"id={context.object_id} is system value"
            )
            return

        self._check_enum_locked(context, enum_type_id, '删除')

    def _get_enum_type(self, context: 'ActionContext', enum_type_id: str) -> dict:
        """获取枚举类型"""
        try:
            cursor = context.data_source.execute(
                "SELECT * FROM enum_types WHERE id = ?",
                [enum_type_id]
            )
            row = cursor.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))
        except Exception as e:
            logger.debug(f"[EnumProtection] Failed to get enum_type {enum_type_id}: {e}")
            return None

    def _has_enum_values(self, context: 'ActionContext', enum_type_id: str) -> bool:
        """检查枚举类型是否有枚举值"""
        try:
            cursor = context.data_source.execute(
                "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ?",
                [enum_type_id]
            )
            result = cursor.fetchone()
            return result and result[0] > 0
        except Exception as e:
            logger.debug(f"[EnumProtection] Failed to check enum values: {e}")
            return False
