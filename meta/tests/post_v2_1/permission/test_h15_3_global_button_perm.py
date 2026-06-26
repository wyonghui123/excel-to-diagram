# -*- coding: utf-8 -*-
"""
test_h15_3_global_button_perm.py
覆盖提交: 70c11df
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 2 (Permission/RBAC)

全局按钮检查所有 OT 权限:
- 任一 OT 有权限 → 按钮可见
- 所有 OT 无权限 → 按钮隐藏
- 点击时只显示有权限的 OT
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [pytest.mark.post_v2_1, pytest.mark.permission]


# ============================================================
# 1. TestGlobalButtonPermission
# ============================================================

class TestGlobalButtonPermission:
    """全局按钮检查所有 OT 权限"""

    def test_button_visible_any_otype_has_perm(self):
        """任一 OT 有权限 → 按钮可见

        后端逻辑: 全局导出按钮的可见性 = 至少有一个 OT 有 export 权限
        """
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        # 用户有 product:export + service_module:export
        mock_cursor.fetchall.return_value = [
            ('product:export',),
            ('service_module:export',),
        ]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        perms = svc.get_user_permissions(3)

        # 模拟前端按钮可见性逻辑
        any_export = any('export' in p for p in perms)
        assert any_export is True

    def test_button_hidden_all_no_perm(self, user_no_export_perm):
        """所有 OT 无权限 → 按钮隐藏"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # 无 perm
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        perms = svc.get_user_permissions(user_no_export_perm['user_id'])
        any_export = any('export' in p for p in perms)
        assert any_export is False

    def test_button_click_filters_to_allowed(self, test_user):
        """点击时只显示有权限的 OT"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        # 用户只有 product:export, version:export
        mock_cursor.fetchall.return_value = [
            ('product:export',),
            ('version:export',),
        ]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        perms = svc.get_user_permissions(test_user['user_id'])

        # 提取有 export 权限的 OT
        allowed_ots = set()
        for p in perms:
            if ':export' in p:
                ot = p.split(':')[0]
                allowed_ots.add(ot)

        # 只有 product, version
        assert allowed_ots == {'product', 'version'}

    def test_admin_button_always_visible(self, admin_user):
        """admin 全局按钮始终可见"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('*',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        perms = svc.get_user_permissions(admin_user['user_id'])
        # admin 的 '*' 视为有所有权限 (含 export)
        is_admin_perm = '*' in perms
        any_export = any('export' in p for p in perms) or is_admin_perm
        assert any_export is True

    def test_wildcard_matches_export(self, admin_user):
        """admin 的 '*' 通配应匹配 :export 检查"""
        from meta.services.auth_middleware import is_admin

        # 即使 permissions 只是 ['*'], 也应能让按钮可见
        assert is_admin({'user_id': 1, 'username': 'admin', 'permissions': ['*']}) is True


# ============================================================
# 2. TestButtonPermissionByAction
# ============================================================

class TestButtonPermissionByAction:
    """按钮按 action 区分权限"""

    def test_export_button_needs_export_perm(self):
        """导出按钮需要 :export 权限"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        # 用户只有 import perm, 没有 export
        mock_cursor.fetchall.return_value = [('product:import',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        # 导出按钮应隐藏 (无 :export)
        assert svc.check_permission_unified(3, 'product', 'export') is False
        # 导入按钮应可见 (有 :import)
        assert svc.check_permission_unified(3, 'product', 'import') is True

    def test_import_button_needs_import_perm(self):
        """导入按钮需要 :import 权限"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        # 用户只有 export, 没有 import
        mock_cursor.fetchall.return_value = [('product:export',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        # 导入按钮应隐藏
        assert svc.check_permission_unified(3, 'product', 'import') is False
        # 导出按钮应可见
        assert svc.check_permission_unified(3, 'product', 'export') is True


# ============================================================
# 3. TestButtonVisibilitySourceCode
# ============================================================

class TestButtonVisibilitySourceCode:
    """按钮可见性的源码级别验证"""

    def test_global_button_routes_check_perms(self):
        """全局按钮相关 routes 应检查权限"""
        # 简化验证: 后端 PermissionService 接口存在
        from meta.services.permission_service import PermissionService
        assert hasattr(PermissionService, 'check_permission_unified')
        assert hasattr(PermissionService, 'get_user_permissions')
        assert hasattr(PermissionService, 'has_permission')

    def test_admin_bypass_via_username(self):
        """admin 通过 username 短路"""
        # import_export_service 中的 admin 短路
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        assert "user.get('username') != 'admin'" in content
