# -*- coding: utf-8 -*-
"""
组织管理守卫拦截器（Spec 19 M1+M2：P0 安全加固 + 行级范围校验）

四类守卫（Spec 19 M1 / M2 2026-09-05）：

1. OrgMoveGuard —— 组织移动逃逸/入侵封堵（Spec 19 IF-002 / T1）
   user_group(org) crud_update 时 parent_id 变更 → 仅全局管理员（或持 org:move 码）可执行。
   委托管理员的 org:update 动作集不含 move，防止把外部子树移入自己范围（入侵）
   或把自己的范围子树移出（逃逸）。

2. SensitiveAssociationGuard —— 敏感关联门禁（Spec 19 FR-005 / T2/T9 + 二次检查 V1/V2）
   关联类动作（associate/dissociate/batch_assign/batch_unassign）分级拦截：
   - 管理员专属：org/user_group ↔ permission_set（组织权限集绑定 = 委托配置本身）、
     user ↔ permission_set / user ↔ role（用户直挂权限授予）、
     permission_set ↔ permission（权限集内容编辑 = 提权放大器）、
     menu_permission ↔ role（旧角色体系菜单授权）
   - 成员级（全局管理员或持 user:update / org_member:manage 任一码）：
     user ↔ user_group、org ↔ user（成员管理，与 org_api 端点双码语义对齐）

3. SensitiveActionGuard —— 敏感自定义动作门禁（二次检查 V2）
   permission_set 的 grant/revoke 类动作仅全局管理员（该动作直改权限集内容）。

4. RowScopeGuard —— 行级范围校验（Spec 19 M2 FR-004，双钥匙之钥匙二）
   org/user 的 crud_* 动作：持有 org 行级委托规则的用户（受托管理员），
   其写目标必须落在受托组织子树内（OrgAdminScopeService 动态解析）。
   - 全局管理员：放行（钥匙二对 admin 恒真）
   - 无委托规则：放行（交给 PermissionInterceptor 按功能码决策——本守卫只收紧越界）
   - 有委托规则：create 按 parent_id/org_ids 挂载点、update/delete 按目标 id
     校验行级范围，越界拒绝（RowScopeDenied）。

审计：拒绝事件统一走 permission_audit.log_permission_decision。
"""

import logging
from typing import TYPE_CHECKING, Optional

from meta.core.interceptors.base import Interceptor
from meta.core.interceptors.permission_interceptor import PermissionDenied

if TYPE_CHECKING:
    from meta.core.action_context import ActionContext

logger = logging.getLogger(__name__)

# org 主数据对象类型（spec 16 重命名 user_group→org 前后兼容）
_ORG_OBJECT_TYPES = {'user_group', 'org'}

# 行级范围校验对象（M2 FR-004）：org + user
_ROW_SCOPE_OBJECTS = {'org', 'user_group', 'user'}
_CRUD_ACTIONS = {'crud_create', 'crud_update', 'crud_delete'}

# 守卫覆盖的关联类动作（含 batch 变体——bo_api batch_assign/batch_unassign 端点旁路封堵，二次检查 V1）
_GUARDED_ASSOC_ACTIONS = {'associate', 'dissociate', 'batch_assign', 'batch_unassign'}

# 敏感关联（管理员专属）：(src_type 集合, tgt_type) —— 权限授予类，仅全局管理员
_ADMIN_ONLY_ASSOCIATIONS = [
    ({'org', 'user_group'}, 'permission_set'),
    ({'user'}, 'permission_set'),
    ({'user'}, 'role'),
    ({'permission_set'}, 'permission'),
    ({'menu_permission'}, 'role'),
]

# 成员关联（双码级）：全局管理员或持 user:update / org_member:manage 任一码
# 与 org_api 成员端点 @require_permission_any('user:update', 'org_member:manage') 语义对齐（二次检查 V1）
_MEMBER_ASSOCIATIONS = [
    ({'user'}, 'user_group'),
    ({'org', 'user_group'}, 'user'),
]

# 敏感自定义动作：permission_set 内容授权动作仅全局管理员（二次检查 V2）
_SENSITIVE_ACTION_OBJECTS = {'permission_set'}
_SENSITIVE_ACTIONS = {'grant', 'revoke', 'grant_permission', 'revoke_permission'}


class OrgMoveDenied(PermissionDenied):
    """组织移动被拒（继承 PermissionDenied 以复用 execute() 的 403 转换链）"""
    pass


class SensitiveAssociationDenied(PermissionDenied):
    """敏感关联操作被拒（同上）"""
    pass


class RowScopeDenied(PermissionDenied):
    """行级范围越界被拒（Spec 19 M2 FR-004，双钥匙之钥匙二）"""
    pass


def _get_user_info():
    from flask import g
    return g.get('current_user') if hasattr(g, 'current_user') else None


def _is_admin(user_info) -> bool:
    from meta.services.auth_middleware import is_admin
    return bool(user_info) and is_admin(user_info)


def _has_perm(user_info, code: str) -> bool:
    perms = (user_info or {}).get('permissions', []) or []
    return '*' in perms or code in perms


def _get_user_id(user_info) -> Optional[int]:
    """从当前用户信息提取 user_id。

    [FIX 2026-09-05 M2-9b] g.current_user 由 TokenService.verify_token 产出,
    键名为 'user_id'；此前误用 get('id') 恒得 None, 导致
    get_manageable_org_ids(None) 返回空集 → 行级守卫误走「无委托放行」分支,
    受托管理员的范围外成员操作被放行（T4 缺陷根因）。
    兼容单测构造的 {'id': ...} 形态。
    """
    uid = (user_info or {}).get('user_id')
    if uid is None:
        uid = (user_info or {}).get('id')
    return uid


def _log_deny(user_info, target_type, target_id, action, reason, guard):
    try:
        from meta.core.permission_audit import log_permission_decision
        log_permission_decision(
            user_id=_get_user_id(user_info),
            target_type=target_type,
            target_id=target_id,
            action=action,
            decision='deny',
            reason=reason,
            interceptor=guard,
        )
    except Exception:
        logger.warning('org_admin_guard audit log failed', exc_info=True)


class OrgAdminGuardInterceptor(Interceptor):
    """组织管理守卫（M1）：移动守卫 + 敏感关联门禁

    priority=26：在 PermissionInterceptor(30) 之前执行，尽早拒绝敏感操作。
    """

    priority = 26

    # ---------------- OrgMoveGuard ----------------

    def _is_org_move(self, context: 'ActionContext') -> bool:
        if context.object_type not in _ORG_OBJECT_TYPES:
            return False
        if context.action != 'crud_update':
            return False
        params = context.params or {}
        if 'parent_id' not in params:
            return False
        old_data = getattr(context, 'old_data', None) or {}
        new_parent = params.get('parent_id')
        old_parent = old_data.get('parent_id')
        # 值未变化（含 None==None）不算移动
        return new_parent != old_parent

    # ---------------- SensitiveAssociationGuard ----------------

    def _match_sensitive_association(self, context: 'ActionContext'):
        """匹配敏感关联。

        返回值：
        - ('admin', (src_label, tgt_label))：管理员专属关联
        - ('member', (src_label, tgt_label))：成员级关联（双码任一放行）
        - None：非敏感关联
        """
        if context.action not in _GUARDED_ASSOC_ACTIONS:
            return None
        params = context.params or {}
        tgt_type = params.get('tgt_type')
        for src_types, sensitive_tgt in _ADMIN_ONLY_ASSOCIATIONS:
            if context.object_type in src_types and tgt_type == sensitive_tgt:
                return ('admin', (sorted(src_types)[0], sensitive_tgt))
        for src_types, member_tgt in _MEMBER_ASSOCIATIONS:
            if context.object_type in src_types and tgt_type == member_tgt:
                return ('member', (sorted(src_types)[0], member_tgt))
        return None

    # ---------------- SensitiveActionGuard ----------------

    def _is_sensitive_action(self, context: 'ActionContext') -> bool:
        return (
            context.object_type in _SENSITIVE_ACTION_OBJECTS
            and context.action in _SENSITIVE_ACTIONS
        )

    # ---------------- RowScopeGuard（M2 FR-004） ----------------

    def _row_scope_applies(self, context: 'ActionContext') -> bool:
        return (
            context.object_type in _ROW_SCOPE_OBJECTS
            and context.action in _CRUD_ACTIONS
        )

    def _check_row_scope(self, context: 'ActionContext', user_info) -> None:
        """行级范围校验：仅收紧「持有委托规则但越界」的场景。

        - 全局管理员：放行（before_action 已提前返回）
        - 无委托规则：放行（功能码由 PermissionInterceptor 决策）
        - 有委托规则：目标必须在受托组织子树内
        """
        from meta.services.org_admin_scope_service import OrgAdminScopeService
        from meta.core.bo_framework import bo_framework

        svc = OrgAdminScopeService(bo_framework._data_source)
        user_id = _get_user_id(user_info)
        params = context.params or {}
        object_type = 'org' if context.object_type == 'user_group' else context.object_type

        # 无委托规则 → 放行（本守卫只收紧受托管理员越界）
        manageable = svc.get_manageable_org_ids(user_id)
        if manageable is not None and not manageable:
            return

        if object_type == 'org':
            if context.action == 'crud_create':
                # 挂载点：parent_id；根级创建（无 parent）受托管理员不可为
                targets = [params.get('parent_id')]
                targets = [t for t in targets if t is not None]
                if not targets:
                    ok, reason = False, '受托管理员不可创建根级组织（需绑定父组织或全局管理员）'
                    self._raise_scope_denied(user_info, context, None, reason)
            else:
                targets = [params.get('id') or getattr(context, 'target_id', None)]
            for t in targets:
                ok, reason = svc.check_org_scope(user_id, t, context.action)
                if not ok:
                    self._raise_scope_denied(user_info, context, t, reason)
        else:  # user
            if context.action == 'crud_create':
                targets = OrgAdminScopeService.extract_org_ids_from_params(params)
                if not targets:
                    # 创建用户未指明组织 → 交由业务层校验必填；此处放行挂载点检查
                    return
                for t in targets:
                    ok, reason = svc.check_org_scope(user_id, t, context.action)
                    if not ok:
                        self._raise_scope_denied(user_info, context, t, reason)
            else:
                target_user = params.get('id') or getattr(context, 'target_id', None)
                if target_user is None:
                    return
                ok, reason = svc.check_user_scope(user_id, target_user, context.action)
                if not ok:
                    self._raise_scope_denied(user_info, context, target_user, reason)

    def _raise_scope_denied(self, user_info, context, target_id, reason):
        _log_deny(user_info, context.object_type, target_id,
                  context.action, reason, 'RowScopeGuard')
        raise RowScopeDenied(reason)

    # ---------------- RowScopeGuard：成员关联行级（M2 FR-004） ----------------

    def _row_scope_applies_member(self, params: dict) -> bool:
        """成员关联是否需要行级校验（src/tgt 均含有效组织 id 时）"""
        return any(isinstance(params.get(k), int) for k in ('src_id', 'tgt_id'))

    def _check_member_row_scope(self, context: 'ActionContext', user_info, params: dict) -> None:
        """成员关联行级校验：涉及的载体组织 + 目标用户都必须在受托范围内。

        - (org, user) 关联：src_id = 目标组织（org 范围），tgt_id/target_ids = 目标用户（user 范围）
        - (user, user_group) 关联：tgt_id = 目标组织（org 范围）
        - batch 变体：src_id 为组织，target_ids 为用户列表
        """
        from meta.services.org_admin_scope_service import OrgAdminScopeService
        from meta.core.bo_framework import bo_framework

        svc = OrgAdminScopeService(bo_framework._data_source)
        user_id = _get_user_id(user_info)
        object_type = 'org' if context.object_type == 'user_group' else context.object_type

        # 无委托规则 → 放行（本守卫只收紧受托管理员越界，功能码交给 PermissionInterceptor）
        manageable = svc.get_manageable_org_ids(user_id)
        if manageable is not None and not manageable:
            return

        if object_type == 'org':
            target_org = params.get('src_id')
        else:  # user ↔ user_group
            target_org = params.get('tgt_id')
        if isinstance(target_org, int):
            ok, reason = svc.check_org_scope(user_id, target_org, context.action)
            if not ok:
                self._raise_scope_denied(user_info, context, target_org, reason)

        # [Spec 19 FR-004] 成员关联的目标用户须在 user 范围内
        #（org → user 关联：tgt_id 单个 / target_ids 批量）
        if object_type == 'org':
            target_users = []
            if isinstance(params.get('tgt_id'), int):
                target_users.append(params['tgt_id'])
            batch_ids = params.get('target_ids')
            if isinstance(batch_ids, (list, tuple)):
                target_users.extend(x for x in batch_ids if isinstance(x, int))
            for tu in target_users:
                ok, reason = svc.check_user_scope(user_id, tu, context.action)
                if not ok:
                    self._raise_scope_denied(user_info, context, tu, reason)

    def should_execute(self, context: 'ActionContext') -> bool:
        return (
            self._is_org_move(context)
            or self._match_sensitive_association(context) is not None
            or self._is_sensitive_action(context)
            or self._row_scope_applies(context)
        )

    def before_action(self, context: 'ActionContext') -> None:
        user_info = _get_user_info()
        if not user_info:
            from meta.core.interceptors.permission_interceptor import PermissionDenied
            raise PermissionDenied('未登录')

        # 全局管理员：四类守卫全部放行（单一出口，避免每段重复判定）
        if _is_admin(user_info):
            if self._is_org_move(context):
                logger.info(
                    f'OrgMoveGuard: org move allowed '
                    f'(target={context.object_type}#{getattr(context, "target_id", None)}, admin=True)'
                )
            return

        if self._is_org_move(context):
            # 允许：显式持有 org:move 码（默认任何委托不可得）
            if _has_perm(user_info, 'org:move'):
                logger.info(
                    f'OrgMoveGuard: org move allowed '
                    f'(target={context.object_type}#{getattr(context, "target_id", None)}, '
                    f'org:move holder)'
                )
                return
            reason = '组织移动（变更上级组织）仅限全局管理员 (org:move)'
            _log_deny(user_info, context.object_type, getattr(context, 'target_id', None),
                      'move', reason, 'OrgMoveGuard')
            raise OrgMoveDenied(reason)

        pair = self._match_sensitive_association(context)
        if pair:
            level, (src_label, tgt_label) = pair
            params = context.params or {}
            if level == 'admin':
                if _is_admin(user_info):
                    return
                reason = (
                    f'敏感关联操作（{src_label} ↔ {tgt_label}）仅限全局管理员：'
                    f'权限授予类绑定属于委托配置，不可由非管理员执行'
                )
                _log_deny(user_info, context.object_type, params.get('src_id'),
                          context.action, reason, 'SensitiveAssociationGuard')
                raise SensitiveAssociationDenied(reason)
            # member 级：全局管理员或双码任一（与 org_api 成员端点对齐）
            if _has_perm(user_info, 'user:update') \
                    or _has_perm(user_info, 'org_member:manage'):
                # [M2 FR-004] 受托管理员的成员操作须做行级校验：
                #   src=org（把人加进组织）→ 目标组织 src_id 在受托范围内
                #   src=user（把用户挂到组织）→ 目标组织 tgt_id 在受托范围内
                if self._row_scope_applies_member(params):
                    self._check_member_row_scope(context, user_info, params)
                return
            reason = (
                f'成员管理操作（{src_label} ↔ {tgt_label}）需要 user:update 或 '
                f'org_member:manage 权限之一'
            )
            _log_deny(user_info, context.object_type, params.get('src_id'),
                      context.action, reason, 'SensitiveAssociationGuard')
            raise SensitiveAssociationDenied(reason)

        if self._is_sensitive_action(context):
            if _is_admin(user_info):
                return
            reason = (
                f'敏感动作（{context.object_type}.{context.action}）仅限全局管理员：'
                f'权限集内容授权属于委托配置本体'
            )
            _log_deny(user_info, context.object_type, (context.params or {}).get('id'),
                      context.action, reason, 'SensitiveActionGuard')
            raise SensitiveAssociationDenied(reason)

        # RowScopeGuard（M2 FR-004）：仅收紧持有委托规则的受托管理员
        if self._row_scope_applies(context):
            self._check_row_scope(context, user_info)

    def after_action(self, context: 'ActionContext') -> None:
        """守卫无后置逻辑（基类抽象方法空实现）"""
        pass

    def on_error(self, context: 'ActionContext', error: Exception):
        from flask import jsonify
        if isinstance(error, (OrgMoveDenied, SensitiveAssociationDenied, RowScopeDenied)):
            return jsonify({
                'success': False,
                'message': error.detail,
                'code': 'ERR_ORG_ADMIN_GUARD_DENIED',
            }), error.status_code
        return None
