# -*- coding: utf-8 -*-
"""
[Spec 22 FR-004 2026-09-13] state_transition action_ref 权限校验拦截器

触发条件：
  - action == 'crud_update'（PUT /bo/{type}/{id}）
  - meta_object.rules 中存在 state_transition 规则且其 action_ref 非空
  - 请求体（params）含与某条 rule 匹配的 state_field + 目标 to_state

校验逻辑：
  - 从 user.permissions 列表（PermissionInterceptor 注入的 current_user.permissions）中
    查找 action_ref
  - 找到 → 放行
  - 找不到 → 403 PermissionDenied
  - rule.action_ref 为空（自定义 transition）→ 走 allowed_roles 字段白名单校验（向后兼容）

priority=31：在 PermissionInterceptor (30) 之后立即执行，先做完基础 CRUD 校验
再补 state_transition 业务校验。
"""

import logging
from typing import TYPE_CHECKING

from meta.core.interceptors.base import Interceptor
from meta.core.interceptors.permission_interceptor import PermissionDenied

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)


class ActionPermissionDenied(PermissionDenied):
    """[Spec 22 FR-004] state_transition action_ref 权限缺失异常"""
    def __init__(self, action_ref: str, rule_id: str, object_type: str):
        self.action_ref = action_ref
        self.rule_id = rule_id
        self.object_type = object_type
        super().__init__(
            f"缺少权限 {action_ref}（state_transition: {rule_id}, object: {object_type}）"
        )


class ActionPermissionInterceptor(Interceptor):
    """
    [Spec 22 FR-004 2026-09-13] state_transition action_ref 权限校验拦截器

    与 PermissionInterceptor (priority=30) 协作：CRUD 权限通过后，
    进一步校验该 PUT 操作是否属于合法的 state_transition 触发（请求体含 state_field 目标值），
    若有 action_ref 则校验用户权限，无 action_ref 则走旧 allowed_roles 白名单。
    """

    priority = 31  # 在 PermissionInterceptor (30) 之后立即执行

    def should_execute(self, context: 'ActionContext') -> bool:
        """仅对 crud_update 操作生效（PUT /bo/{type}/{id}）"""
        return context.action == 'crud_update'

    def before_action(self, context: 'ActionContext') -> None:
        from flask import g
        from meta.services.auth_middleware import is_admin

        meta_obj = getattr(context, 'meta_object', None)
        if not meta_obj or not getattr(meta_obj, 'rules', None):
            return  # 无 rules 定义的对象跳过

        user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        if not user_info:
            return  # 登录态校验交给 login_required / PermissionInterceptor
        if is_admin(user_info):
            return  # 管理员放行

        request_body = context.params or {}
        rules = meta_obj.rules or []

        # 遍历规则找匹配的 state_transition
        for rule in rules:
            if not hasattr(rule, 'state_field') or not hasattr(rule, 'to_state'):
                continue

            state_field = rule.state_field
            target_state = rule.to_state
            target_value = request_body.get(state_field)

            # 请求体不含该 state_field → 不是 state_transition 触发（如普通字段更新）
            if state_field not in request_body:
                continue

            # 请求体值不等于 rule.to_state → 不是该 transition 触发
            if target_value != target_state:
                continue

            action_ref = getattr(rule, 'action_ref', '')

            if action_ref:
                # [Spec 22 FR-004] 标准 action 池校验
                self._check_action_ref(context, user_info, action_ref, rule.id, meta_obj.bo_id)
            else:
                # [Spec 22 FR-007 向后兼容] 自定义 transition 走 allowed_roles 校验
                allowed_roles = getattr(rule, 'allowed_roles', []) or []
                if allowed_roles:
                    self._check_allowed_roles(user_info, allowed_roles, rule.id, meta_obj.bo_id)
            # 注：一个 PUT 只能触发一个 transition（按 state_field 唯一匹配），找到就跳出
            return

    def _check_action_ref(self, context, user_info, action_ref, rule_id, object_type):
        """标准 action 池权限校验"""
        permissions = user_info.get('permissions', []) or []
        if isinstance(permissions, list):
            permissions = set(permissions)
        if '*' in permissions:
            return  # 通配符放行
        if action_ref in permissions:
            return  # 持有对应 action 权限，放行

        logger.info(
            f"[ActionPermissionInterceptor] DENY {user_info.get('user_name')} on "
            f"{object_type}:{getattr(context, 'target_id', '?')} state_transition:{rule_id} "
            f"requires action_ref:{action_ref}"
        )
        raise ActionPermissionDenied(action_ref, rule_id, object_type)

    def _check_allowed_roles(self, user_info, allowed_roles, rule_id, object_type):
        """[向后兼容] allowed_roles 白名单校验"""
        user_role = user_info.get('role') or user_info.get('user_type') or ''
        if user_role in allowed_roles:
            return
        # 注：旧 yaml 的 allowed_roles 字段如生效，PermissionInterceptor 会抛通用 403
        # 这里只做防御性补充，不重复 raise 避免双异常
        logger.debug(
            f"[ActionPermissionInterceptor] allowed_roles bypass for {rule_id} on {object_type}"
        )

    def after_action(self, context: 'ActionContext') -> None:
        """[Spec 22 FR-004] 权限校验为纯前置操作，无后置逻辑"""
        pass
