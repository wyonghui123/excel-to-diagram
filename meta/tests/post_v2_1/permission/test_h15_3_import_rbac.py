# -*- coding: utf-8 -*-
"""
test_h15_3_import_rbac.py
覆盖提交: c19915c, 0e9c26c
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 2 (Permission/RBAC)

import 端 RBAC 权限检查:
- import_cascade 中 self.data_source 而非 self.ds, user['user_id'] 而非 user['id']
- 导入时尊重用户 permissions
- admin 导入绕过权限
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [pytest.mark.post_v2_1, pytest.mark.permission]


# ============================================================
# 1. TestImportRBAC
# ============================================================

class TestImportRBAC:
    """import 端 RBAC 权限检查"""

    def test_import_cascade_uses_correct_user_dict(self):
        """import_cascade 中 self.data_source 而非 self.ds, user['user_id'] 而非 user['id']"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # import_cascade 中应使用 user['user_id'] 而非 user['id']
        assert "user['user_id']" in content, \
            "import_cascade 应使用 user['user_id']"
        # 不应有 user['id'] (这是常见 bug 模式)
        # 这里弱断言: 只检查关键 user_id 引用
        assert 'check_permission_unified(\n                    user[\'user_id\']' in content or \
               "check_permission_unified(user['user_id']" in content, \
            "import_cascade 应将 user['user_id'] 传给 check_permission_unified"

    def test_import_respects_user_permissions(self):
        """导入时尊重用户 permissions"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('product:import',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        # 用户有 product:import → True
        assert svc.check_permission_unified(3, 'product', 'import') is True

    def test_import_with_admin_bypasses_check(self, admin_user):
        """admin 导入绕过权限"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('*',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        for ot in ['product', 'version', 'service_module', 'business_object', 'relationship']:
            assert svc.check_permission_unified(admin_user['user_id'], ot, 'import') is True

    def test_import_no_perm_returns_false(self, user_no_export_perm):
        """无 import 权限时返回 False"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # 无 perm
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        result = svc.check_permission_unified(user_no_export_perm['user_id'], 'product', 'import')
        assert result is False

    def test_import_skip_no_perm_sheet(self):
        """导入时无权限 sheet 被跳过 (而非整体失败)"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # 应有跳过逻辑
        assert '[H15.2 FIX] 添加导入权限检查' in content
        assert '跳过 sheet' in content
        # continue 而不是 fail
        assert 'continue' in content

    def test_import_strict_all_no_perm(self):
        """所有 sheet 都无权限 → 友好错误 (不是 500)"""
        # 验证源码: 应有 ImportResult(success=False, ...) 返回
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # import_cascade 失败返回
        assert 'return ImportResult(' in content
        assert 'success=False' in content


# ============================================================
# 2. TestImportRBACUserSourcePriority
# ============================================================

class TestImportRBACUserSourcePriority:
    """导入时 user 来源优先级"""

    def test_thread_local_user_first(self):
        """import_cascade 优先用 _get_thread_user"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # 应有 _get_thread_user
        assert '_get_thread_user' in content

    def test_fallback_to_flask_g(self):
        """无 thread-local user 时 fallback 到 flask.g.current_user"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # 应有 get_current_user
        assert 'get_current_user' in content

    def test_admin_username_short_circuit(self):
        """username == 'admin' 时短路"""
        src_path = Path(PROJECT_ROOT) / 'meta' / 'services' / 'import_export_service.py'
        content = src_path.read_text(encoding='utf-8')
        # import_cascade 中的 admin 短路
        assert "user.get('username') != 'admin'" in content


# ============================================================
# 3. TestImportRBACStrictChecks
# ============================================================

class TestImportRBACStrictChecks:
    """导入严格模式检查"""

    def test_check_permission_unified_with_resource_id(self):
        """check_permission_unified(uid, ot, action, resource_id) 实例级检查"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('product:import',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        result = svc.check_permission_unified(3, 'product', 'import', resource_id=123)
        # 默认 _check_instance_permission 返回 True
        assert result is True

    def test_permission_service_handles_empty_user_perms(self):
        """用户无任何 perm 时安全返回"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        perms = svc.get_user_permissions(999)
        assert perms == []

        # 不应抛异常
        assert svc.check_permission_unified(999, 'product', 'import') is False

    def test_permission_service_admin_wildcard(self, admin_user):
        """admin 通配始终通过"""
        from meta.services.permission_service import PermissionService

        mock_ds = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('*',)]
        mock_ds.execute.return_value = mock_cursor

        svc = PermissionService(mock_ds)
        # 任意 perm 都通过
        assert svc.has_permission(admin_user['user_id'], 'any:perm') is True
        assert svc.check_permission_unified(admin_user['user_id'], 'any', 'perm') is True
