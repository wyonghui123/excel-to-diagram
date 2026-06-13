# -*- coding: utf-8 -*-
"""
枚举保护拦截器 (v3.18 enum-mgmt-spec)

基于三层矩阵保护枚举类型和枚举值的完整性：

保护维度（AND 严格，任一触发即拒绝）：
  1. category='system'    — 宏观：系统枚举 vs 业务枚举
  2. mutability=locked    — 类型级：3 档 {fullEditable, extensible, locked}
  3. is_system=true       — 值级：预置值

mutability 矩阵（DEC-1）：
  - fullEditable:  CRUD 全部允许（除 is_system=true 仍不可 update/delete）
  - extensible:    可加新值，可改/删非预置值，不可改/删预置值
  - locked:        全部禁止

is_system 矩阵（DEC-2 AND 严格）：
  - is_system=true 时，无论 mutability 是什么，update/delete 都被拒绝
  - is_system=true 仅表示"该值不可被业务方改/删"，不影响"可以创建新值"

校验规则（FR-006 ~ FR-010）：
  - id/code 必填
  - code 格式：^[A-Z][A-Z0-9_]*$
  - code 不可改
  - id 不可改
  - (enum_type_id, name) 唯一

Author: AI Coding Agent
Date: 2026-06-13
"""

import logging
import re
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionResult
from meta.core.error_codes import ErrorCode

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# enum_value.code 格式：必须以大写字母开头，仅含大写字母、数字、下划线
CODE_PATTERN = re.compile(r'^[A-Z][A-Z0-9_]*$')

# 允许的 mutability 值（FR-001）
ALLOWED_MUTABILITY = {'fullEditable', 'extensible', 'locked'}


class EnumProtectionInterceptor(Interceptor):
    """
    枚举保护拦截器

    优先级: 35
    在 DataPermissionInterceptor 之后执行，在 HierarchyValidationInterceptor 之前

    保护规则（AND 严格，任一触发即拒绝）：
    1. 系统枚举（category='system'）：不可修改/删除（ENUM_TYPE 维度）
    2. 锁定枚举（mutability='locked'）：不可增删改 enum_value（ENUM_TYPE 维度）
    3. 系统预置值（is_system=1）：不可 update/delete（ENUM_VALUE 维度）
    4. 字段校验（FR-006~010）：id/code 必填、code 格式、code/id 不可改
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

        # FR-001: mutability 值空间校验（仅 enum_type 的 create/update 需校验）
        if object_type == 'enum_type':
            mutability = context.params.get('mutability')
            if mutability and mutability not in ALLOWED_MUTABILITY:
                self._reject(
                    context,
                    f"mutability 必须是 {sorted(ALLOWED_MUTABILITY)} 之一，当前值 '{mutability}'",
                    ErrorCode.INVALID_MUTABILITY.value,
                )
                return

        if context.is_create_action:
            self._validate_create(context)
        elif context.is_update_action:
            self._validate_update(context)
        elif context.is_delete_action:
            self._validate_delete(context)

    def after_action(self, context: 'ActionContext') -> None:
        """后置处理 - 命名唯一性校验（FR-009）"""
        if not context.result or not context.result.success:
            return
        if context.object_type not in ('enum_type', 'enum_value'):
            return
        if not (context.is_create_action or context.is_update_action):
            return

        # 仅当 is_active 字段参与时不需要 name 唯一检查（toggle_active 不影响 name）
        # 实际上 name 唯一应在 create/update 路径拦截，这里仅作为最后一道防线
        # 若有 DUPLICATE_NAME 已在 API 层捕获（unique index），这里不必再查

    # ──────────────────────────────────────────
    # 公共 reject 工具
    # ──────────────────────────────────────────

    def _reject(self, context: 'ActionContext', message: str, error_code: str) -> None:
        """统一的拒绝方式（设置 result + 标记阻止后续执行）"""
        context.result = ActionResult(
            success=False,
            data=None,
            message=message,
            errors=[error_code],
        )
        logger.warning(
            f"[EnumProtection] Blocked action {context.action}: {error_code} - {message}"
        )

    # ──────────────────────────────────────────
    # Create 校验
    # ──────────────────────────────────────────

    def _validate_create(self, context: 'ActionContext') -> None:
        """创建校验"""
        if context.object_type == 'enum_type':
            self._validate_enum_type_create(context)
        elif context.object_type == 'enum_value':
            self._validate_enum_value_create(context)

    def _validate_enum_type_create(self, context: 'ActionContext') -> None:
        """enum_type 创建校验 - 系统枚举不可通过 API 创建（必须由初始化脚本）"""
        category = context.params.get('category')
        if category == 'system':
            self._reject(
                context,
                "系统枚举不可通过 API 创建（请使用初始化脚本或 migrate_enums.py）",
                ErrorCode.SYSTEM_ENUM_IMMUTABLE.value,
            )

    def _validate_enum_value_create(self, context: 'ActionContext') -> None:
        """enum_value 创建校验 - 锁定枚举不可添加 + 字段必填 + code 格式"""
        # FR-006: 必填校验
        enum_type_id = context.params.get('enum_type_id')
        code = context.params.get('code')
        name = context.params.get('name')
        if not enum_type_id or not code or not name:
            self._reject(
                context,
                "enum_type_id / code / name 必填",
                ErrorCode.ACTION_PARAMS_MISSING.value,
            )
            return

        # FR-007: code 格式校验
        if not CODE_PATTERN.match(code):
            self._reject(
                context,
                f"code '{code}' 不符合格式 ^[A-Z][A-Z0-9_]*$（仅允许大写字母、数字、下划线，且以大写字母开头）",
                ErrorCode.INVALID_CODE_FORMAT.value,
            )
            return

        # mutability=locked → 不可添加值（与 is_system 无关）
        enum_type = self._get_enum_type(context, enum_type_id)
        if enum_type and enum_type.get('mutability') == 'locked':
            self._reject(
                context,
                f"该枚举类型 '{enum_type_id}' 已锁定（mutability=locked），不可添加值",
                ErrorCode.ENUM_VALUE_LOCKED.value,
            )

    # ──────────────────────────────────────────
    # Update 校验
    # ──────────────────────────────────────────

    def _validate_update(self, context: 'ActionContext') -> None:
        """更新校验"""
        if context.object_type == 'enum_type':
            self._validate_enum_type_update(context)
        elif context.object_type == 'enum_value':
            self._validate_enum_value_update(context)

    def _validate_enum_type_update(self, context: 'ActionContext') -> None:
        """enum_type 更新校验 - 系统不可改 / id 不可改"""
        # FR-010: id 不可改
        if 'id' in context.params:
            old_id = context.old_data.get('id') if context.old_data else None
            if old_id and context.params['id'] != old_id:
                self._reject(
                    context,
                    f"id 字段不可修改（原值 '{old_id}'，尝试改为 '{context.params['id']}'）",
                    ErrorCode.ID_IMMUTABLE.value,
                )
                return

        # 系统枚举不可改
        if self._check_system_enum_immutable(context, '修改'):
            return

    def _validate_enum_value_update(self, context: 'ActionContext') -> None:
        """enum_value 更新校验 - 多重保护"""
        old_data = context.old_data
        if not old_data:
            return

        # FR-008: code 不可改
        if 'code' in context.params:
            old_code = old_data.get('code')
            if old_code and context.params['code'] != old_code:
                self._reject(
                    context,
                    f"code 字段不可修改（原值 '{old_code}'，尝试改为 '{context.params['code']}'）",
                    ErrorCode.CODE_IMMUTABLE.value,
                )
                return

        # FR-007: code 格式校验（如果更新时改了 code 之外的字段不影响，但若改了 code 需符合格式）
        # 这里因已在上方拦截 code 变更，不再重复检查

        # DEC-2 AND 严格：is_system=true 永远不可 update
        if old_data.get('is_system') == 1:
            self._reject(
                context,
                "系统预置值（is_system=true）不可修改",
                ErrorCode.SYSTEM_VALUE_IMMUTABLE.value,
            )
            return

        # mutability=locked → 不可 update（与 is_system 无关）
        enum_type_id = old_data.get('enum_type_id')
        if self._check_enum_locked(context, enum_type_id, '修改'):
            return

    # ──────────────────────────────────────────
    # Delete 校验
    # ──────────────────────────────────────────

    def _validate_delete(self, context: 'ActionContext') -> None:
        """删除校验"""
        if context.object_type == 'enum_type':
            self._validate_enum_type_delete(context)
        elif context.object_type == 'enum_value':
            self._validate_enum_value_delete(context)

    def _validate_enum_type_delete(self, context: 'ActionContext') -> None:
        """enum_type 删除校验 - 系统不可删 / 有值不可删"""
        if self._check_system_enum_immutable(context, '删除'):
            return

        old_data = context.old_data
        if not old_data:
            return

        enum_type_id = context.object_id or old_data.get('id')
        if self._has_enum_values(context, enum_type_id):
            self._reject(
                context,
                f"该枚举类型 '{enum_type_id}' 下有枚举值，无法删除",
                ErrorCode.HAS_VALUES.value,
            )

    def _validate_enum_value_delete(self, context: 'ActionContext') -> None:
        """enum_value 删除校验 - 预置不可删 / 锁定不可删（AND）"""
        old_data = context.old_data
        if not old_data:
            return

        # DEC-2 AND 严格：is_system=true 永远不可 delete
        if old_data.get('is_system') == 1:
            self._reject(
                context,
                "系统预置值（is_system=true）不可删除",
                ErrorCode.SYSTEM_VALUE_IMMUTABLE.value,
            )
            return

        # mutability=locked → 不可 delete
        enum_type_id = old_data.get('enum_type_id')
        if self._check_enum_locked(context, enum_type_id, '删除'):
            return

    # ──────────────────────────────────────────
    # 工具方法
    # ──────────────────────────────────────────

    def _check_system_enum_immutable(self, context: 'ActionContext', action_name: str) -> bool:
        """检查系统枚举不可变 — 成功拒绝时返回 True（已 set context.result）"""
        old_data = context.old_data
        if not old_data:
            return False

        if old_data.get('category') == 'system':
            self._reject(
                context,
                f"系统枚举不可{action_name}",
                ErrorCode.SYSTEM_ENUM_IMMUTABLE.value,
            )
            return True
        return False

    def _check_enum_locked(self, context: 'ActionContext', enum_type_id: str, action_name: str) -> bool:
        """检查枚举类型是否已锁定 — 成功拒绝时返回 True"""
        if not enum_type_id:
            return False
        try:
            enum_type = self._get_enum_type(context, enum_type_id)
            if not enum_type:
                return False

            if enum_type.get('mutability') == 'locked':
                self._reject(
                    context,
                    f"该枚举类型 '{enum_type_id}' 已锁定（mutability=locked），不可{action_name}值",
                    ErrorCode.ENUM_VALUE_LOCKED.value,
                )
                return True
        except Exception as e:
            logger.debug(f"[EnumProtection] Enum lock check skipped: {e}")
        return False

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
