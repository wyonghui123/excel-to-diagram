# -*- coding: utf-8 -*-
"""
平台运维作业菜单可见性回归 (2026-10-14)
======================================

[背景]
`platform-ops-jobs` 与 `task-management` 同构:
  - page_type='custom_page' (自实现页面, 由静态路由渲染, 不走 GenericTabContainer)
  - parent_menu='system' (系统管理分组)
  - 自身无 children

而 `/api/v1/menu-permission/visible` 的 `_prune_empty_groups` 把
"custom_page + 无 children" 一律当空分组容器裁掉 —— 于是这类"真页面叶子"
(有 menu_path 的 custom_page) 在侧边栏完全不可见。

[本套件]
- super_admin 应能在 system 分组下看到 platform-ops-jobs
- business_user 不应看到 (菜单 required_permissions=['*'], 管理员门槛)
- system 分组对 business_user 仍应隐藏 (H3 契约: 空分组清理, required=[] 的
  custom_page 叶子仍视为容器被裁掉, 以免非管理员看见空的"系统管理")

[作者] 2026-10-14 编排调度交付
"""
import json
import pytest


pytestmark = pytest.mark.integration

MENU_URL = '/api/v1/menu-permission'


def _get_visible_tree(api_client, headers):
    resp = api_client.get(f'{MENU_URL}/visible', headers=headers)
    assert resp.status_code == 200, f'/visible 期望 200, 实际 {resp.status_code}'
    return json.loads(resp.data).get('menus', [])


def _find_menu(menus, code):
    for m in menus:
        if m.get('menu_code') == code:
            return m
        if m.get('children'):
            r = _find_menu(m['children'], code)
            if r:
                return r
    return None


class TestPlatformOpsJobsMenuVisibility:
    """平台运维作业菜单: 管理员可见, 普通用户不可见"""

    def test_super_admin_sees_platform_ops_jobs(self, api_client, super_admin_headers):
        """super_admin 应见 platform-ops-jobs (custom_page 叶子不应被剪枝)"""
        menus = _get_visible_tree(api_client, super_admin_headers)
        node = _find_menu(menus, 'platform-ops-jobs')
        assert node is not None, (
            '[剪枝缺陷] super_admin 看不到 platform-ops-jobs —— '
            '_prune_empty_groups 把无 children 的 custom_page 误当空分组裁掉了'
        )
        assert node.get('menu_path') == '/system/platform-ops-jobs'

    def test_platform_ops_jobs_is_child_of_system(self, api_client, super_admin_headers):
        """platform-ops-jobs 应挂在 system 分组下"""
        menus = _get_visible_tree(api_client, super_admin_headers)
        system = _find_menu(menus, 'system')
        assert system is not None, 'super_admin 应见 system 分组'
        child_codes = [c.get('menu_code') for c in system.get('children', [])]
        assert 'platform-ops-jobs' in child_codes, f'system 子菜单缺 platform-ops-jobs, 实际: {child_codes}'

    def test_business_user_does_not_see_platform_ops_jobs(self, api_client, business_user_headers):
        """business_user 不应见 platform-ops-jobs (required_permissions=['*'])"""
        menus = _get_visible_tree(api_client, business_user_headers)
        assert _find_menu(menus, 'platform-ops-jobs') is None, \
            'business_user 不应见平台运维作业菜单'

    def test_business_user_still_no_empty_system_group(self, api_client, business_user_headers):
        """H3 契约: business_user 无 system 子菜单权限时, 空 system 分组仍应隐藏"""
        menus = _get_visible_tree(api_client, business_user_headers)
        assert _find_menu(menus, 'system') is None, \
            'business_user 不应见空的 system 分组 (H3 契约被破坏)'


class TestTaskManagementMenuVisibility:
    """任务管理菜单: 与 platform-ops-jobs 同口径 (required_permissions=['*'])"""

    def test_super_admin_sees_task_management(self, api_client, super_admin_headers):
        """super_admin 应见 task-management (custom_page 叶子不应被剪枝)"""
        menus = _get_visible_tree(api_client, super_admin_headers)
        node = _find_menu(menus, 'task-management')
        assert node is not None, (
            '[剪枝缺陷] super_admin 看不到 task-management —— '
            'required_permissions 为空时被 _prune_empty_groups 误当空分组裁掉'
        )
        assert node.get('menu_path') == '/system/task-management'

    def test_task_management_is_child_of_system(self, api_client, super_admin_headers):
        """task-management 应挂在 system 分组下"""
        menus = _get_visible_tree(api_client, super_admin_headers)
        system = _find_menu(menus, 'system')
        assert system is not None, 'super_admin 应见 system 分组'
        child_codes = [c.get('menu_code') for c in system.get('children', [])]
        assert 'task-management' in child_codes, \
            f'system 子菜单缺 task-management, 实际: {child_codes}'

    def test_business_user_does_not_see_task_management(self, api_client, business_user_headers):
        """business_user 不应见 task-management (required_permissions=['*'])"""
        menus = _get_visible_tree(api_client, business_user_headers)
        assert _find_menu(menus, 'task-management') is None, \
            'business_user 不应见任务管理菜单'
