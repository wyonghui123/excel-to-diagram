# -*- coding: utf-8 -*-
"""
功能性权限拦截器

在 BO 框架 before_action 阶段对 crud_* 标准动作进行 resource:action 权限校验。
权限码来自 JWT token 中的 permissions 列表（login_required 装饰器注入 g.current_user）。
"""

import logging
import os
from typing import TYPE_CHECKING
from meta.core.interceptors.base import Interceptor

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# crud_* 标准动作 → 权限后缀映射
# [v1.0.1 FR-001] 合并 read/list: list 和 query 复用 read 权限, 避免缺 product:list 时 403
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_update': 'update',
    'crud_delete': 'delete',
    'crud_list':   'read',  # v1.0.1: 合并到 read
    'crud_query':  'read',  # v1.0.1: 合并到 read
}

# [v1.0.1 D9] 父读 audit-only 严格模式开关 (env 升级用)
_PARENT_READ_STRICT_MODE = os.environ.get('PARENT_READ_STRICT_MODE', '').lower() == 'true'

# [v1.0.1 D10] 链 read audit-only 严格模式开关 (env 升级用)
_CHAIN_DERIVATION_STRICT_MODE = os.environ.get('CHAIN_DERIVATION_STRICT_MODE', '').lower() == 'true'


class PermissionDenied(Exception):
    status_code = 403

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


# [v1.0.1 D9] 父读 audit-only 升级模式异常
class ParentPermissionDenied(Exception):
    status_code = 403

    def __init__(self, child: str, parent: str, perm: str, action: str):
        self.child = child
        self.parent = parent
        self.perm = perm
        self.action = action
        super().__init__(f'缺少父资源 {parent} 的 read 权限 (操作 {child}.{action}, 需 {perm})')


# [v1.0.1 D10] 链 read 类型级硬拒异常 (env 升级模式)
class ChainReadDenied(Exception):
    status_code = 403

    def __init__(self, object_type: str, chain: list, required_perm_any_of: list):
        self.object_type = object_type
        self.chain = chain
        self.required_perm_any_of = required_perm_any_of
        super().__init__(
            f'写 {object_type} 需链中任一 read 权限: {",".join(required_perm_any_of)}'
        )


# [v1.0.1 D13] 链 read 实例级越权异常
class ChainInstanceOutOfScope(Exception):
    status_code = 403

    def __init__(self, object_type: str, target_id: int, chain: list, out_of_scope_parents: list):
        self.object_type = object_type
        self.target_id = target_id
        self.chain = chain
        self.out_of_scope_parents = out_of_scope_parents
        super().__init__(
            f'操作 {object_type}({target_id}) 越权, parent chain 中实例不在 user 数据权限范围'
        )


def user_info_has_perm(permissions, required: str) -> bool:
    """[v1.0.1] helper: 检查 permissions 集合/列表中是否含 required (支持通配 *)"""
    if not permissions:
        return False
    if '*' in permissions:
        return True
    return required in permissions


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

        # [v1.0.1 D9] 父读 audit-only (写操作触发, 不阻塞)
        if context.action in ('crud_create', 'crud_update', 'crud_delete'):
            self._check_parent_read_advisory(context, user_info)

        # [v1.0.1 D10] 链 read 类型级 audit-only (写操作触发)
        if context.action in ('crud_create', 'crud_update', 'crud_delete'):
            self._check_chain_read(context, user_info, target_id=getattr(context, 'target_id', None))

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
        # [v1.0.1 D13] 链 read 实例级越权
        if isinstance(error, ChainInstanceOutOfScope):
            return jsonify({
                'success': False,
                'message': str(error),
                'code': 'ERR_CHAIN_INSTANCE_OUT_OF_SCOPE',
                'out_of_scope_parents': error.out_of_scope_parents,
                'chain': error.chain,
            }), error.status_code
        # [v1.0.1 D10 env 升级] 链 read 类型级硬拒
        if isinstance(error, ChainReadDenied):
            return jsonify({
                'success': False,
                'message': str(error),
                'code': 'ERR_CHAIN_READ_DENIED',
                'chain': error.chain,
                'required_perm_any_of': error.required_perm_any_of,
            }), error.status_code
        return None

    # ============================================================
    # [v1.0.1 D9] 父读 audit-only
    # ============================================================
    def _check_parent_read_advisory(self, context: 'ActionContext', user_info: dict) -> None:
        """[FR-003 v1.0.1 D9] 父读 audit-only 校验 — 写操作触发, log + header + 不阻塞.

        流程:
        1. 查 BoYamlCache.get_parent(child_type) → 父 BO 配置
        2. 缺权限 → audit-only (log + header + /_diagnostics)
        3. 升级模式: PARENT_READ_STRICT_MODE=true → 抛 ParentPermissionDenied
        """
        try:
            from meta.core.bo_yaml_cache import BoYamlCache
        except ImportError:
            return  # BoYamlCache 不可用, 跳过 (向后兼容)

        parent_cfg = BoYamlCache.get_parent(context.object_type)
        if not parent_cfg:
            return  # 无 parent 配置, 跳过

        parent_type = parent_cfg.get('object')
        if not parent_type:
            return

        permissions = user_info.get('permissions', [])
        if not isinstance(permissions, set):
            permissions = set(permissions)

        # admin / 通配符 跳过
        if '*' in permissions:
            return

        required_perm = f'{parent_type}:read'
        if required_perm in permissions:
            return  # 有权限, 放行

        # 缺权限: audit-only
        missing_perms = [required_perm]
        try:
            from flask import request
            if request and hasattr(request, 'response') and request.response:
                request.response.headers['X-Parent-Permission-Warning'] = (
                    f'missing {",".join(missing_perms)}'
                )
        except Exception:
            pass

        logger.warning(
            'permission.parent_read.missing',
            extra={
                'child_object': context.object_type,
                'parent_object': parent_type,
                'parent_required_perm': required_perm,
                'action': context.action,
                'user_id': user_info.get('id'),
                'decision': 'allow_with_warning',
            }
        )

        # 写入 /_diagnostics 计数
        try:
            from meta.core.diagnostics import get_diagnostics
            diag = get_diagnostics()
            if 'parent_read_warnings' not in diag:
                diag['parent_read_warnings'] = []
            diag['parent_read_warnings'].append({
                'child_object': context.object_type,
                'parent_object': parent_type,
                'parent_required_perm': required_perm,
                'action': context.action,
                'user_id': user_info.get('id'),
                'decision': 'allow_with_warning',
            })
            # 保留最近 100 条
            if len(diag['parent_read_warnings']) > 100:
                diag['parent_read_warnings'] = diag['parent_read_warnings'][-100:]
        except Exception:
            pass

        # env 升级模式: 硬拒
        if _PARENT_READ_STRICT_MODE:
            logger.warning(
                'permission.parent_read.missing (strict mode)',
                extra={'decision': 'hard_reject'}
            )
            raise ParentPermissionDenied(
                child=context.object_type,
                parent=parent_type,
                perm=required_perm,
                action=context.action,
            )

    # ============================================================
    # [v1.0.1 D10/D13] 链 read 校验
    # ============================================================
    def _check_chain_read(self, context: 'ActionContext', user_info: dict, target_id: int = None) -> None:
        """[FR-003b v1.0.1 D10/D13] 链 read 校验 — 类型级 audit-only + 实例级硬拒.

        类型级 (FR-003b.1):
        - 写操作触发, 链中任一 read 缺失 → audit-only (log + header + 不阻塞)
        - env 升级: CHAIN_DERIVATION_STRICT_MODE=true → 抛 ChainReadDenied

        实例级 (FR-003b.2):
        - 带 target_id 时, 解析实际 parent chain instances
        - 任一 parent instance 不在 user data scope → 硬拒 ChainInstanceOutOfScope
        """
        try:
            from meta.core.bo_yaml_cache import BoYamlCache
        except ImportError:
            return

        chain = BoYamlCache.get_parent_chain(context.object_type)
        if not chain:
            return  # 顶层 BO, 无链

        # D11 A2 模式: 读/列表不校验
        # (已经在 caller 处判断 action, 这里再防一次)
        if context.action in ('crud_read', 'crud_list', 'crud_query'):
            return

        permissions = user_info.get('permissions', [])
        if not isinstance(permissions, set):
            permissions = set(permissions)

        if '*' in permissions:
            return  # 通配符放行

        # =========================================================
        # FR-003b.1 类型级 audit-only
        # =========================================================
        if not any(user_info_has_perm(permissions, f'{bo}:read') for bo in chain):
            missing_perms = [f'{bo}:read' for bo in chain
                            if not user_info_has_perm(permissions, f'{bo}:read')]

            try:
                from flask import request
                if request and hasattr(request, 'response') and request.response:
                    request.response.headers['X-Chain-Permission-Warning'] = (
                        f'missing {",".join(missing_perms)}'
                    )
            except Exception:
                pass

            logger.warning(
                'permission.chain_read.type.missing',
                extra={
                    'object_type': context.object_type,
                    'chain': chain,
                    'missing_perms': missing_perms,
                    'action': context.action,
                    'user_id': user_info.get('id'),
                    'decision': 'allow_with_warning',
                }
            )

            # 写入 /_diagnostics
            try:
                from meta.core.diagnostics import get_diagnostics
                diag = get_diagnostics()
                if 'chain_read_warnings' not in diag:
                    diag['chain_read_warnings'] = []
                diag['chain_read_warnings'].append({
                    'object_type': context.object_type,
                    'chain': chain,
                    'missing_perms': missing_perms,
                    'action': context.action,
                    'user_id': user_info.get('id'),
                    'decision': 'allow_with_warning',
                })
                if len(diag['chain_read_warnings']) > 100:
                    diag['chain_read_warnings'] = diag['chain_read_warnings'][-100:]
            except Exception:
                pass

            # env 升级模式: 类型级硬拒
            if _CHAIN_DERIVATION_STRICT_MODE:
                raise ChainReadDenied(
                    object_type=context.object_type,
                    chain=chain,
                    required_perm_any_of=[f'{bo}:read' for bo in chain],
                )

        # =========================================================
        # FR-003b.2 实例级硬拒 (仅写 + target_id)
        # =========================================================
        if target_id is not None:
            try:
                actual_parents = BoYamlCache.resolve_parent_chain(
                    context.object_type, target_id
                )
            except Exception as e:
                logger.debug(f'resolve_parent_chain failed: {e}')
                actual_parents = []

            if actual_parents:
                user_data_scope = user_info.get('data_scope', {})
                out_of_scope = []
                for parent in actual_parents:
                    parent_bo = parent['bo']
                    parent_id = parent['id']
                    scope = user_data_scope.get(parent_bo, [])
                    if scope and parent_id not in scope:
                        out_of_scope.append({
                            'bo': parent_bo,
                            'instance_id': parent_id,
                            'data_scope': scope,
                        })

                if out_of_scope:
                    logger.warning(
                        'permission.chain_read.instance.out_of_scope',
                        extra={
                            'object_type': context.object_type,
                            'target_id': target_id,
                            'out_of_scope_parents': out_of_scope,
                            'action': context.action,
                            'user_id': user_info.get('id'),
                            'decision': 'hard_reject',
                        }
                    )
                    raise ChainInstanceOutOfScope(
                        object_type=context.object_type,
                        target_id=target_id,
                        chain=[p['bo'] for p in actual_parents],
                        out_of_scope_parents=out_of_scope,
                    )


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
