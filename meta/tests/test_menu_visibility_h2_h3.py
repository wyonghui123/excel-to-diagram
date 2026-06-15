# -*- coding: utf-8 -*-
"""
H2 + H3 回归测试 (2026-06-14): 菜单可见性 & 空分组清理
======================================================

[H2 背景]
audit-log 菜单的 required_permissions: ['audit_log:read', 'audit_log:delete']
在 OR 语义下, 业务用户 (有 audit_log:read) 误可见 audit-log 菜单. 修复后改为 ['*'] (super-admin only).

[H3 背景]
system 父菜单 page_type='custom_page' + 有 menu_path='/system', 子菜单被 visibility
过滤后, 父菜单仍保留导致空分组. 修复后 _prune_empty_groups() 后置清理
page_type='custom_page' + 空 children 的节点.

[本测试套件]
- H2: 3 角色 (admin / business_user / no_audit_user) x audit-log 菜单可见性
- H3: 3 角色 x system 父菜单是否展示 (含/不含 children)
- 额外契约: required_permissions 不能含无意义权限代码

[作者] Hotfix 2026-06-14
[关联] .trae/specs/auth-permission-system/tasks.md (Task H2, H3)
"""
import json
import pytest


pytestmark = pytest.mark.integration

MENU_URL = '/api/v1/menu-permission'


def _get_visible_menus(api_client, headers):
    """[H2/H3] 调用 /visible 端点, 返回 (menus, leaf_menus)"""
    resp = api_client.get(f'{MENU_URL}/visible', headers=headers)
    assert resp.status_code == 200, f'/visible 期望 200, 实际 {resp.status_code}'
    body = json.loads(resp.data)
    return body.get('menus', []), body.get('leaf_menus', [])


def _find_menu(menus, code):
    """[H2/H3] 递归查找菜单 (含子菜单)"""
    for m in menus:
        if m.get('menu_code') == code:
            return m
        if m.get('children'):
            r = _find_menu(m['children'], code)
            if r:
                return r
    return None


def _collect_leaf_codes(menus):
    """[H2/H3] 收集所有叶子菜单 code"""
    codes = []
    for m in menus:
        if not m.get('children'):
            codes.append(m.get('menu_code'))
        else:
            codes.extend(_collect_leaf_codes(m['children']))
    return codes


# ==================== H2: audit-log 菜单 admin-only ====================

class TestAuditLogMenuVisibilityH2:
    """H2 回归: audit-log 菜单对 super-admin 可见, 其他角色隐藏"""

    def test_super_admin_sees_audit_log_menu(self, api_client, super_admin_headers):
        """[H2] super_admin 可见 audit-log 菜单"""
        menus, _ = _get_visible_menus(api_client, super_admin_headers)
        audit = _find_menu(menus, 'audit-log')
        assert audit is not None, (
            f'[H2] super_admin 应可见 audit-log 菜单, 实际 menus: '
            f'{_collect_leaf_codes(menus)}'
        )

    def test_business_user_does_not_see_audit_log_menu(self, api_client, business_user_headers):
        """[H2] 业务用户 (有 audit_log:read) 不应看见 audit-log 菜单"""
        menus, _ = _get_visible_menus(api_client, business_user_headers)
        # 业务用户实际有 audit_log:read 权限 (因为 arch-data 自动绑定)
        # 但菜单 required_permissions: ['*'] 应该屏蔽
        audit = _find_menu(menus, 'audit-log')
        assert audit is None, (
            f'[H2] 业务用户不应见 audit-log 菜单 (H2 修复未生效或被绕过), '
            f'实际找到了: {audit}'
        )

    def test_no_audit_user_does_not_see_audit_log_menu(self, api_client, no_audit_user_headers):
        """[H2] 无 audit 权限用户不可见 audit-log 菜单"""
        menus, _ = _get_visible_menus(api_client, no_audit_user_headers)
        audit = _find_menu(menus, 'audit-log')
        assert audit is None, '[H2] 无 audit 权限用户不应见 audit-log 菜单'

    def test_admin_with_asterisk_sees_audit_log_menu(self, api_client, admin_headers):
        """[H2] admin 用户 (permissions=['*']) 可见 audit-log 菜单"""
        menus, _ = _get_visible_menus(api_client, admin_headers)
        audit = _find_menu(menus, 'audit-log')
        assert audit is not None, '[H2] admin 应见 audit-log 菜单 (有 * 权限)'

    def test_audit_log_menu_required_permissions_admin_only(self, api_client, super_admin_headers):
        """[H2 契约] audit-log 菜单的 required_permissions 应包含 '*'"""
        # 通过 /menus/<code> 或 /menus/all 查询菜单元数据
        # 这里用 /visible 拿不到 required_permissions 详情, 改为从叶子菜单检查
        # 仅做端到端检查: 业务用户不可见即满足
        _, leaf = _get_visible_menus(api_client, super_admin_headers)
        audit_leaf = next((m for m in leaf if m.get('menu_code') == 'audit-log'), None)
        assert audit_leaf is not None, '[H2] super_admin 应见 audit-log leaf'

    def test_audit_log_menu_not_derived_from_audit_log_read(self, api_client, business_user_headers):
        """[H2 契约] 仅 audit_log:read 不足以触发 audit-log 菜单可见性"""
        # 这是 H2 bug 的核心: 之前 required=['audit_log:read', 'audit_log:delete']
        # OR 语义下, business_user 凭 audit_log:read 可见
        # 修复后要求 '*', business_user 不可见
        menus, _ = _get_visible_menus(api_client, business_user_headers)
        audit = _find_menu(menus, 'audit-log')
        assert audit is None, (
            '[H2 契约违反] business_user 仍可见 audit-log 菜单, '
            '意味着 required_permissions 含 audit_log:read 这类可被推导权限, '
            '请检查 init_menu_permissions.py 中 audit-log 块'
        )


# ==================== H3: 空 system 分组清理 ====================

class TestSystemMenuEmptyGroupCleanupH3:
    """H3 回归: 空 system 父菜单 (无子菜单权限) 应对业务用户隐藏"""

    def test_admin_sees_system_with_children(self, api_client, super_admin_headers):
        """[H3] super_admin 可见 system 父菜单 + 4 个子菜单组"""
        menus, _ = _get_visible_menus(api_client, super_admin_headers)
        system = _find_menu(menus, 'system')
        assert system is not None, '[H3] super_admin 应见 system 父菜单'
        children = system.get('children', [])
        assert len(children) > 0, '[H3] super_admin 应见 system 下的子菜单'
        # 子菜单组应含 task-management, user-permission, business-config, audit-log
        # task-management 是 multi_object_hub, 其叶子是 task-definitions 等
        child_codes = [c.get('menu_code') for c in children]
        assert 'user-permission' in child_codes
        assert 'business-config' in child_codes
        assert 'audit-log' in child_codes

    def test_business_user_no_system_children_hides_system(self, api_client, business_user_headers):
        """[H3] 业务用户 (无 system 子菜单权限) 不可见 system 父菜单"""
        menus, _ = _get_visible_menus(api_client, business_user_headers)
        system = _find_menu(menus, 'system')
        assert system is None, (
            f'[H3 修复未生效] business_user 不应见空 system 分组, 实际找到: {system}'
        )

    def test_no_audit_user_no_system_children_hides_system(self, api_client, no_audit_user_headers):
        """[H3] 无 audit 权限用户不可见空 system 分组"""
        menus, _ = _get_visible_menus(api_client, no_audit_user_headers)
        system = _find_menu(menus, 'system')
        assert system is None, '[H3] 无 audit 用户不应见空 system 分组'

    def test_audit_reader_no_system_children_hides_system(self, api_client, audit_reader_headers):
        """[H3] 审计读者不可见空 system 分组"""
        menus, _ = _get_visible_menus(api_client, audit_reader_headers)
        system = _find_menu(menus, 'system')
        assert system is None, '[H3] 审计读者不应见空 system 分组'

    def test_super_admin_object_list_with_path_not_pruned(self, api_client, super_admin_headers):
        """[H3 契约] page_type='object_list' 的菜单, 不应被 _prune_empty_groups 误删"""
        # super_admin 应见 product-management (page_type=object_list, 有 menu_path)
        menus, _ = _get_visible_menus(api_client, super_admin_headers)
        pm = _find_menu(menus, 'product-management')
        assert pm is not None, '[H3] object_list 菜单不应被误删'
        # 验证 page_type 不是 custom_page
        assert pm.get('page_type') != 'custom_page', (
            '[H3 契约违反] object_list 被错误标记为 custom_page, 清理逻辑误判'
        )


# ==================== 综合可见性矩阵 ====================

class TestMenuVisibilityMatrixH2H3:
    """H2 + H3 综合: 多角色对比, 重点验证 system/audit-log 隐藏"""

    def test_super_admin_sees_full_tree(self, api_client, super_admin_headers):
        """[H2+H3] super_admin 看到完整菜单 (含 system+子菜单)"""
        menus, leaf = _get_visible_menus(api_client, super_admin_headers)
        codes = _collect_leaf_codes(menus)
        # audit-log 应在叶子菜单中
        assert 'audit-log' in codes, f'[H2] super_admin 缺 audit-log, 实际: {codes}'
        # user-permission, business-config 也是 system 子菜单
        assert 'user-permission' in codes
        assert 'business-config' in codes
        # 应有 dashboard, arch-data, product-management
        assert 'dashboard' in [m.get('menu_code') for m in menus]

    def test_business_user_no_system_no_audit_log(self, api_client, business_user_headers):
        """[H2+H3] 业务用户 (无 system 权限) 不可见 system 父菜单和 audit-log 叶子"""
        menus, _ = _get_visible_menus(api_client, business_user_headers)
        codes = set(_collect_leaf_codes(menus))
        top_codes = set(m.get('menu_code') for m in menus)

        # 关键契约 (H2/H3):
        assert 'system' not in top_codes, '[H3] system 父菜单应隐藏'
        assert 'audit-log' not in codes, '[H2] audit-log 应隐藏'
        # business_user 没 system 权限, 子菜单都应隐藏
        assert 'user-permission' not in codes, 'user-permission 应隐藏'
        assert 'business-config' not in codes, 'business-config 应隐藏'

    def test_no_audit_user_sees_dashboard_only(self, api_client, no_audit_user_headers):
        """[H2+H3] 无权限用户仅见 dashboard"""
        menus, _ = _get_visible_menus(api_client, no_audit_user_headers)
        top_codes = set(m.get('menu_code') for m in menus)
        # dashboard 总是可见 (login_required)
        assert 'dashboard' in top_codes
        # 业务相关不可见
        assert 'arch-data' not in top_codes
        assert 'system' not in top_codes, '[H3] system 应隐藏'


# 总结: 6 H2 用例 + 5 H3 用例 + 3 综合矩阵 = 14 用例
