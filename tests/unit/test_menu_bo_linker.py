# -*- coding: utf-8 -*-
r"""
FR-013 菜单-BO 权限自动关联单元测试
"""
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.menu_bo_linker import MenuBOLinker, get_menu_bo_linker


class TestMenuBOLinker(unittest.TestCase):
    """FR-013 单元测试"""

    def setUp(self):
        self.linker = MenuBOLinker()

    def test_01_default_permissions_no_schema(self):
        """无 schema 时返回默认 CRUD 权限"""
        with patch.object(self.linker, '_schema_loader') as mock_loader:
            mock_loader.get_bo_schema.return_value = None
            perms = self.linker.get_default_bo_permissions('test_bo')
        self.assertIn('test_bo:read', perms)
        self.assertIn('test_bo:list', perms)
        self.assertIn('test_bo:update', perms)
        self.assertIn('test_bo:delete', perms)

    def test_02_default_permissions_with_actions(self):
        """有 BO actions 字段时用实际 actions"""
        mock_schema = {
            'id': 'business_object',
            'actions': [
                {'id': 'business_object_create'},
                {'id': 'business_object_read'},
                {'id': 'business_object_update'},
                {'id': 'business_object_list'},
            ],
        }
        with patch.object(self.linker, '_schema_loader') as mock_loader:
            mock_loader.get_bo_schema.return_value = mock_schema
            perms = self.linker.get_default_bo_permissions('business_object')
        self.assertIn('business_object:business_object_read', perms)
        self.assertIn('business_object:business_object_list', perms)
        # 不应包含 read（BO 实际叫 business_object_read）
        self.assertNotIn('business_object:read', perms)

    def test_03_effective_permissions_for_menu(self):
        """菜单绑定多个 BO 时合并去重权限"""
        with patch.object(self.linker, '_schema_loader') as mock_loader:
            mock_loader.get_bo_schema.return_value = None
            perms = self.linker.get_effective_permissions_for_menu(
                menu_code='test_menu',
                bo_bindings=[
                    {'bo_id': 'business_object'},
                    {'bo_id': 'domain'},
                ],
            )
        # 应有 2 个 BO 的默认权限合并去重
        self.assertIn('business_object:read', perms)
        self.assertIn('domain:read', perms)
        # 去重
        self.assertEqual(len(perms), len(set(perms)))

    def test_04_cross_menu_bo_intent_summary(self):
        """FR-015 跨菜单 BO 累加显式化"""
        all_bindings = [
            {'menu_code': 'menu1', 'bo_id': 'domain', 'role': 'primary'},
            {'menu_code': 'menu2', 'bo_id': 'domain', 'role': 'primary'},
            {'menu_code': 'menu3', 'bo_id': 'domain', 'role': 'secondary'},
        ]
        with patch.object(self.linker, '_schema_loader') as mock_loader:
            mock_loader.get_bo_schema.return_value = None
            summary = self.linker.get_cross_menu_bo_intent_summary(
                bo_id='domain',
                all_menu_bindings=all_bindings,
            )
        self.assertEqual(summary['bo_id'], 'domain')
        self.assertEqual(summary['menu_count'], 3)
        self.assertEqual(len(summary['menus']), 3)
        # role 有 primary 和 secondary，has_conflict = True
        self.assertTrue(summary['has_conflict'])
        # all_actions 应有 4 个 CRUD 权限（去重）
        self.assertEqual(len(summary['all_actions']), 4)

    def test_05_cross_menu_no_conflict(self):
        """所有 menu 同 role 时 has_conflict=False"""
        all_bindings = [
            {'menu_code': 'menu1', 'bo_id': 'version', 'role': 'primary'},
            {'menu_code': 'menu2', 'bo_id': 'version', 'role': 'primary'},
        ]
        with patch.object(self.linker, '_schema_loader') as mock_loader:
            mock_loader.get_bo_schema.return_value = None
            summary = self.linker.get_cross_menu_bo_intent_summary(
                bo_id='version',
                all_menu_bindings=all_bindings,
            )
        self.assertEqual(summary['menu_count'], 2)
        self.assertFalse(summary['has_conflict'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
