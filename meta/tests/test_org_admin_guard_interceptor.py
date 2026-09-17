# -*- coding: utf-8 -*-
"""
Spec 19 M1 单元测试：OrgAdminGuardInterceptor（组织管理守卫）

覆盖：
- OrgMoveGuard 决策逻辑（parent_id diff / 对象类型 / 动作类型）
- SensitiveAssociationGuard 匹配规则（管理员专属关联 / 成员级关联 / batch 动作变体）
- SensitiveActionGuard（permission_set grant/revoke 类动作）
- before_action 拒绝/放行路径（非管理员 403、管理员放行、org:move 码放行、成员双码放行）
- 异常继承链（PermissionDenied 子类 → execute() 403 转换生效）
- 二次安全检查回归（2026-09-05 V1/V2：batch 旁路、成员关联旁路、权限集授权旁路）
"""
import pytest

pytestmark = pytest.mark.integration

import sys
import os
from types import SimpleNamespace

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.interceptors.org_admin_guard_interceptor import (
    OrgAdminGuardInterceptor,
    OrgMoveDenied,
    SensitiveAssociationDenied,
)
from meta.core.interceptors.permission_interceptor import PermissionDenied
from meta.core.action_context import ActionContext


# ============== Fixtures ==============

def _make_context(object_type, action, params, old_data=None):
    return ActionContext(
        meta_object=SimpleNamespace(id=object_type, table_name='t'),
        action=action,
        params=params,
        data_source=None,
        old_data=old_data,
    )


@pytest.fixture
def guard():
    return OrgAdminGuardInterceptor()


@pytest.fixture
def admin_user():
    return {'id': 1, 'username': 'admin', 'permissions': {'*'}}


@pytest.fixture
def plain_user():
    """持 user:update 的普通用户（无 org:move）"""
    return {'id': 2, 'username': 'hr1', 'permissions': {'user:update', 'user_group:update'}}


@pytest.fixture
def no_perm_user():
    """无任何功能码的登录用户"""
    return {'id': 4, 'username': 'guest', 'permissions': set()}


@pytest.fixture
def member_perm_user():
    """仅持新成员管理码的委托管理员（过渡期）"""
    return {'id': 5, 'username': 'delegate1', 'permissions': {'org_member:manage'}}


@pytest.fixture
def move_perm_user():
    return {'id': 3, 'username': 'mover', 'permissions': {'org:move'}}


@pytest.fixture
def patch_user(monkeypatch):
    """monkeypatch 模块级 _get_user_info/_is_admin，注入指定用户"""
    def _patch(user):
        monkeypatch.setattr(
            'meta.core.interceptors.org_admin_guard_interceptor._get_user_info',
            lambda: user,
        )
        monkeypatch.setattr(
            'meta.core.interceptors.org_admin_guard_interceptor._is_admin',
            lambda u: '*' in (u or {}).get('permissions', set()),
        )
    return _patch


# ============== OrgMoveGuard：决策逻辑 ==============

class TestOrgMoveDetection:
    def test_parent_id_changed_is_move(self, guard):
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        assert guard._is_org_move(ctx) is True

    def test_parent_id_unchanged_not_move(self, guard):
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 3}, old_data={'parent_id': 3})
        assert guard._is_org_move(ctx) is False

    def test_no_parent_id_field_not_move(self, guard):
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'name': '改名'}, old_data={'parent_id': 3})
        assert guard._is_org_move(ctx) is False

    def test_root_to_parent_is_move(self, guard):
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 7}, old_data={'parent_id': None})
        assert guard._is_org_move(ctx) is True

    def test_create_not_move(self, guard):
        ctx = _make_context('user_group', 'crud_create',
                            {'parent_id': 9, 'code': 'X'})
        assert guard._is_org_move(ctx) is False

    def test_other_object_type_not_move(self, guard):
        ctx = _make_context('product', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        assert guard._is_org_move(ctx) is False

    def test_org_alias_type_is_move(self, guard):
        """spec 16 重命名后 org 类型同样受守卫"""
        ctx = _make_context('org', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        assert guard._is_org_move(ctx) is True


# ============== SensitiveAssociationGuard：匹配规则 ==============

class TestSensitiveAssociationMatch:
    def test_org_associate_permission_set(self, guard):
        ctx = _make_context('org', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('org', 'permission_set'))

    def test_user_group_dissociate_permission_set(self, guard):
        ctx = _make_context('user_group', 'dissociate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('org', 'permission_set'))

    def test_user_associate_permission_set_admin_level(self, guard):
        ctx = _make_context('user', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('user', 'permission_set'))

    def test_permission_set_associate_permission_admin_level(self, guard):
        """[V2] 权限集 ↔ 权限 = 提权放大器，仅全局管理员"""
        ctx = _make_context('permission_set', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('permission_set', 'permission'))

    def test_user_associate_role_admin_level(self, guard):
        """[V1] 用户直挂角色 = 功能权限授予"""
        ctx = _make_context('user', 'associate',
                            {'src_id': 1, 'tgt_type': 'role', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('user', 'role'))

    def test_menu_permission_associate_role_admin_level(self, guard):
        """[V3] 旧角色体系菜单授权"""
        ctx = _make_context('menu_permission', 'associate',
                            {'src_id': 1, 'tgt_type': 'role', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('admin', ('menu_permission', 'role'))

    def test_user_associate_group_member_level(self, guard):
        """[V1] user ↔ user_group 成员关联 = 双码级（原守卫完全放行 → 旁路）"""
        ctx = _make_context('user', 'associate',
                            {'src_id': 1, 'tgt_type': 'user_group', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('member', ('user', 'user_group'))

    def test_org_associate_user_member_level(self, guard):
        """[V1] org ↔ user 成员关联 = 双码级"""
        ctx = _make_context('user_group', 'associate',
                            {'src_id': 1, 'tgt_type': 'user', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) == ('member', ('org', 'user'))

    def test_batch_assign_action_is_guarded(self, guard):
        """[V1] batch_assign 动作同样进入敏感匹配（bo_api batch 端点旁路封堵）"""
        ctx = _make_context('user', 'batch_assign',
                            {'src_id': 1, 'tgt_type': 'user_group', 'target_ids': [2, 3]})
        assert guard._match_sensitive_association(ctx) == ('member', ('user', 'user_group'))

    def test_batch_unassign_sensitive_combo(self, guard):
        ctx = _make_context('org', 'batch_unassign',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'target_ids': [2]})
        assert guard._match_sensitive_association(ctx) == ('admin', ('org', 'permission_set'))

    def test_business_object_associate_not_sensitive(self, guard):
        ctx = _make_context('business_object', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) is None

    def test_non_assoc_action_not_matched(self, guard):
        """crud 动作不走关联匹配（由移动守卫/PermissionInterceptor 负责）"""
        ctx = _make_context('user', 'crud_update',
                            {'src_id': 1, 'tgt_type': 'user_group', 'tgt_id': 2})
        assert guard._match_sensitive_association(ctx) is None


# ============== SensitiveActionGuard：permission_set 授权动作 ==============

class TestSensitiveAction:
    def test_permission_set_grant_is_sensitive(self, guard):
        ctx = _make_context('permission_set', 'grant_permission', {'id': 1})
        assert guard._is_sensitive_action(ctx) is True

    def test_permission_set_revoke_is_sensitive(self, guard):
        ctx = _make_context('permission_set', 'revoke', {'id': 1})
        assert guard._is_sensitive_action(ctx) is True

    def test_other_object_grant_not_sensitive(self, guard):
        ctx = _make_context('business_object', 'grant', {'id': 1})
        assert guard._is_sensitive_action(ctx) is False

    def test_permission_set_grant_denied_for_plain_user(self, guard, patch_user, plain_user):
        patch_user(plain_user)
        ctx = _make_context('permission_set', 'grant_permission', {'id': 1})
        with pytest.raises(SensitiveAssociationDenied):
            guard.before_action(ctx)

    def test_permission_set_grant_allowed_for_admin(self, guard, patch_user, admin_user):
        patch_user(admin_user)
        ctx = _make_context('permission_set', 'grant_permission', {'id': 1})
        guard.before_action(ctx)  # 不抛异常即放行


# ============== before_action：拒绝/放行 ==============

class TestBeforeAction:
    def test_move_denied_for_plain_user(self, guard, patch_user, plain_user):
        patch_user(plain_user)
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        with pytest.raises(OrgMoveDenied):
            guard.before_action(ctx)

    def test_move_allowed_for_admin(self, guard, patch_user, admin_user):
        patch_user(admin_user)
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        guard.before_action(ctx)  # 不抛异常即放行

    def test_move_allowed_with_org_move_perm(self, guard, patch_user, move_perm_user):
        patch_user(move_perm_user)
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        guard.before_action(ctx)  # org:move 码放行（TR-002 预留）

    def test_sensitive_assoc_denied_for_plain_user(self, guard, patch_user, plain_user):
        patch_user(plain_user)
        ctx = _make_context('org', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        with pytest.raises(SensitiveAssociationDenied):
            guard.before_action(ctx)

    def test_sensitive_assoc_allowed_for_admin(self, guard, patch_user, admin_user):
        patch_user(admin_user)
        ctx = _make_context('org', 'associate',
                            {'src_id': 1, 'tgt_type': 'permission_set', 'tgt_id': 2})
        guard.before_action(ctx)  # 不抛异常即放行

    # ---- [V1] 成员关联双码级：user ↔ user_group ----

    def test_member_assoc_denied_for_no_perm_user(self, guard, patch_user, no_perm_user):
        """[V1 回归] 无码登录用户经 BO 端点把人加组 → 拒绝"""
        patch_user(no_perm_user)
        ctx = _make_context('user', 'associate',
                            {'src_id': 4, 'tgt_type': 'user_group', 'tgt_id': 2})
        with pytest.raises(SensitiveAssociationDenied):
            guard.before_action(ctx)

    def test_member_assoc_allowed_with_user_update(self, guard, patch_user, plain_user):
        patch_user(plain_user)
        ctx = _make_context('user', 'associate',
                            {'src_id': 4, 'tgt_type': 'user_group', 'tgt_id': 2})
        guard.before_action(ctx)  # 持 user:update 放行（与 org_api 端点语义一致）

    def test_member_assoc_allowed_with_org_member_manage(self, guard, patch_user, member_perm_user):
        """过渡期新码 org_member:manage 单独放行"""
        patch_user(member_perm_user)
        ctx = _make_context('user', 'batch_assign',
                            {'src_id': 4, 'tgt_type': 'user_group', 'target_ids': [2]})
        guard.before_action(ctx)  # 不抛异常即放行

    def test_org_member_assoc_denied_for_no_perm_user(self, guard, patch_user, no_perm_user):
        patch_user(no_perm_user)
        ctx = _make_context('user_group', 'dissociate',
                            {'src_id': 1, 'tgt_type': 'user', 'tgt_id': 2})
        with pytest.raises(SensitiveAssociationDenied):
            guard.before_action(ctx)

    def test_user_update_does_not_unlock_admin_assoc(self, guard, patch_user, plain_user):
        """user:update 不能解锁管理员专属关联（分级不串）"""
        patch_user(plain_user)
        ctx = _make_context('user', 'associate',
                            {'src_id': 4, 'tgt_type': 'role', 'tgt_id': 2})
        with pytest.raises(SensitiveAssociationDenied):
            guard.before_action(ctx)

    def test_unauthenticated_denied(self, guard, monkeypatch):
        monkeypatch.setattr(
            'meta.core.interceptors.org_admin_guard_interceptor._get_user_info',
            lambda: None,
        )
        ctx = _make_context('user_group', 'crud_update',
                            {'id': 5, 'parent_id': 9}, old_data={'parent_id': 3})
        with pytest.raises(PermissionDenied):
            guard.before_action(ctx)


# ============== 异常继承链（403 转换保障） ==============

class TestExceptionHierarchy:
    def test_org_move_denied_is_permission_denied(self):
        """execute() L180 isinstance(PermissionDenied) → status_code=403"""
        assert issubclass(OrgMoveDenied, PermissionDenied)
        assert issubclass(SensitiveAssociationDenied, PermissionDenied)

    def test_priority_before_permission_interceptor(self, guard):
        """P26 必须先于 PermissionInterceptor(P30) 执行"""
        assert guard.priority < 30
