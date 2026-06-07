# -*- coding: utf-8 -*-
"""
功能性权限拦截器

在 BO 框架 before_action 阶段对 crud_* 标准动作进行 resource:action 权限校验。
权限码来自 JWT token 中的 permissions 列表（login_required 装饰器注入 g.current_user）。
"""

import logging
from typing import TYPE_CHECKING
from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# crud_* 标准动作 → 权限后缀映射
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_update': 'update',
    'crud_delete': 'delete',
    'crud_list':   'list',
    'crud_query':  'list',
}


class PermissionDenied(Exception):
    status_code = 403

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class PermissionInterceptor(Interceptor):
    """
    功能权限拦截器 — 对 BO CRUD 操作校验 resource:action 权限

    priority=30：与 DataPermissionInterceptor 同级，在 before_action 链中
    先做功能权限校验（允许/拒绝），再做数据权限过滤（行级范围）。

    权限检查逻辑（按优先级，O(1) set 查找）：
    1. 仅拦截 crud_* 标准动作（batch/custom/business 等非 CRUD 放行）
    2. 用户持有 '*' 通配 → 放行
    3. 用户 permissions 列表中含所需 resource:action → 放行
    4. 否则 → 403 PermissionDenied
    """
    priority = 30

    @classmethod
    def _get_permission_suffix(cls, action: str) -> str:
        return _ACTION_PERMISSION_SUFFIX.get(action, '')

    def should_execute(self, context: 'ActionContext') -> bool:
        return context.action.startswith('crud_')

    def before_action(self, context: 'ActionContext') -> None:
        from flask import g
        from meta.services.auth_middleware import is_admin

        user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        if not user_info:
            raise PermissionDenied('未登录')

        # [DECORATIVE] M11 v1.1.0: AI Agent 角色自动识别（X-Agent-Id header → 'ai-agent' 角色）
        user_info = inject_ai_agent_role(user_info, g)
        g.current_user = user_info

        if is_admin(user_info):
            return

        permissions = user_info.get('permissions', [])
        if not isinstance(permissions, set):
            permissions = set(permissions)

        if '*' in permissions:
            return

        suffix = self._get_permission_suffix(context.action)
        if not suffix:
            return

        required = f"{context.object_type}:{suffix}"

        # [DECORATIVE] M11 v1.2.0: YAML 集中化权限（rls_rules/*.yaml 优先于 JWT permissions）
        # 行为：
        # 1. 尝试从 rls.get_allowed_actions() 读 YAML 规则
        # 2. YAML 有规则 → 用 YAML 检查（注意 ai-agent 角色也参与）
        # 3. YAML 无规则或异常 → 回退到现有 JWT permissions 检查
        yaml_allowed = _check_yaml_permission(user_info, context.object_type, suffix)
        if yaml_allowed is True:
            return  # YAML 允许
        if yaml_allowed is False:
            raise PermissionDenied(f'RLS denied: {required}')

        # 回退到现有逻辑
        if required not in permissions:
            raise PermissionDenied(f'缺少权限: {required}')

    # [DECORATIVE] v3.16 bug fix: 之前 after_action 和 on_error 在 class 外 (放在 _apply_yaml_field_masks 函数内做 dead code)
    # 修复: 把它们正确放在 class 内
    def after_action(self, context: 'ActionContext') -> None:
        # [DECORATIVE] M11 v1.2.0: YAML 集中化字段脱敏（rls_rules/*.yaml field_masks 优先）
        try:
            from flask import g
            user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        except Exception:
            user_info = None
        if user_info and hasattr(context, 'result') and context.result:
            try:
                if isinstance(context.result, dict):
                    context.result = _apply_yaml_field_masks(
                        user_info, context.object_type, context.result
                    )
                elif isinstance(context.result, list):
                    context.result = [
                        _apply_yaml_field_masks(user_info, context.object_type, item)
                        if isinstance(item, dict) else item
                        for item in context.result
                    ]
            except Exception:
                pass  # 脱敏失败不影响主流程

    def on_error(self, context: 'ActionContext', error: Exception):
        from flask import jsonify
        if isinstance(error, PermissionDenied):
            return jsonify({
                'success': False,
                'message': error.detail,
                'code': 'PERMISSION_DENIED',
            }), error.status_code
        return None


def inject_ai_agent_role(user_info, flask_g=None):
    """[DECORATIVE] M11 v1.1.0: AI Agent 角色自动识别

    通过 X-Agent-Id header 识别 AI Agent 调用，向 user_info['roles'] 注入 'ai-agent' 角色。
    与 rls YAML 中的 applies_to: [role:ai-agent] 协同。

    Args:
        user_info: dict（来自 g.current_user）
        flask_g: flask.g（用于 setattr 回写，可选）

    Returns:
        修改后的 user_info（dict）。原 dict 不修改（浅拷贝）。

    行为：
    1. 无 X-Agent-Id header → 原样返回
    2. 有 X-Agent-Id header + 无 'ai-agent' 角色 → 注入（深拷贝）
    3. 有 X-Agent-Id header + 已有 'ai-agent' 角色 → 原样返回
    4. flask_g 不为 None → 同时回写 g.current_user
    """
    if user_info is None:
        return user_info
    try:
        from flask import request
    except ImportError:
        return user_info
    if not request or not request.headers.get('X-Agent-Id'):
        return user_info

    existing_roles = user_info.get('roles', [])
    if not isinstance(existing_roles, set):
        existing_roles = set(existing_roles)
    if 'ai-agent' in existing_roles:
        if flask_g is not None:
            flask_g.current_user = user_info
        return user_info  # 已存在

    new_user_info = dict(user_info)  # 浅拷贝，避免修改原 dict
    new_user_info['roles'] = existing_roles | {'ai-agent'}
    if flask_g is not None:
        flask_g.current_user = new_user_info
    return new_user_info


def _check_yaml_permission(user_info, object_type, action_suffix):
    """[DECORATIVE] M11 v1.2.0: YAML 集中化权限检查

    检查 rls_rules/*.yaml 中的 actions 规则。
    用户的 roles 列表（可能含 'ai-agent'）逐个与 YAML applies_to 匹配。

    Args:
        user_info: dict（含 'roles' 字段，list/set）
        object_type: 实体名
        action_suffix: 'create' / 'read' / 'update' / 'delete' / 'list' / 'export'

    Returns:
        True: YAML 明确允许
        False: YAML 明确拒绝
        None: YAML 无规则（回退到现有 JWT permissions 检查）
    """
    try:
        from rls import check_action
    except ImportError:
        return None  # rls 模块不可用，回退

    if user_info is None:
        return None
    user_roles = user_info.get('roles', [])
    if not user_roles:
        # 无 roles 字段，使用 'user' 作为默认
        user_roles = ['user']
    if not isinstance(user_roles, (list, set, tuple)):
        return None

    # 任意一个 role 通过即允许
    for role in user_roles:
        try:
            if check_action(role, object_type, action_suffix):
                return True
        except Exception:
            continue
    # 所有 role 都不允许
    # 但如果 YAML 中无任何该 entity 规则 → 回退
    try:
        from rls.loader import get_loader
        if not get_loader().has_rule_for(object_type):
            return None  # YAML 无该 entity 规则，回退
    except Exception:
        return None
    return False  # YAML 有规则且所有 role 都不允许


def _check_yaml_row_filter(user_info, object_type, current_scope_expr, user_id):
    """[DECORATIVE] M11 v1.2.0: YAML 集中化行级过滤

    从 rls_rules/*.yaml 的 row_filters 读规则，替换 YAML 优先于 meta_object.authorization.scope。
    """
    try:
        from rls import get_active_row_filter
    except ImportError:
        return None
    if user_info is None:
        return None
    user_roles = user_info.get('roles', []) or ['user']
    for role in user_roles:
        try:
            cond = get_active_row_filter(role, object_type)
        except Exception:
            continue
        if cond:
            return cond.replace('$user.id', str(user_id))
    return None  # YAML 无规则，回退


def _apply_yaml_field_masks(user_info, object_type, data):
    """[DECORATIVE] M11 v1.2.0: YAML 集中化字段脱敏

    从 rls_rules/*.yaml 的 field_masks 读规则，对 data 应用脱敏。
    """
    try:
        from rls import apply_field_masks
    except ImportError:
        return data
    if user_info is None or not isinstance(data, dict):
        return data
    user_roles = user_info.get('roles', []) or ['user']
    for role in user_roles:
        try:
            masked = apply_field_masks(role, object_type, data)
            if masked != data:  # 有 mask 规则应用
                return masked
        except Exception:
            continue
    return data

    # [DECORATIVE] v3.16 bug fix: 之前 after_action 和 on_error 错误地放在 _apply_yaml_field_masks 函数内
    # (Module refactor 时把 class end 弄丢了, 实际是 class 37-100 关闭)
    # 修复: 把它们移到 class 内 (in before_action 之后, module-level 之前)
    # 实际已修复: 这段 dead code 保留, 不会执行 (在函数 return 之后)
