# -*- coding: utf-8 -*-
"""
V1 Cleanup - is_admin() 单元测试 (4 场景)

依据: spec-auth-object-category-v2-2026-06-10.md FR-V1-003 + AC-V1-003.3
- 场景 1: user 有 '*' 通配 → True
- 场景 2: user 无 '*' 通配 → False
- 场景 3: user_info=None → False
- 场景 4: permissions 字段异常类型 → False (不抛异常)
"""
import pytest
from meta.services.auth_middleware import is_admin


class TestIsAdminV1:
    """V1 简化后 is_admin() 行为验证"""

    def test_admin_with_wildcard_permission(self):
        """场景 1: 拥有 '*' 通配 → True"""
        user = {
            'user_id': 1,
            'username': 'admin',
            'roles': [{'code': 'admin', 'name': '系统管理员'}],
            'permissions': ['*'],
        }
        assert is_admin(user) is True

    def test_admin_with_wildcard_in_set(self):
        """场景 1b: permissions 是 set 也支持"""
        user = {
            'user_id': 1,
            'permissions': {'user:read', '*', 'role:read'},
        }
        assert is_admin(user) is True

    def test_admin_with_wildcard_in_tuple(self):
        """场景 1c: permissions 是 tuple 也支持"""
        user = {
            'user_id': 1,
            'permissions': ('*',),
        }
        assert is_admin(user) is True

    def test_non_admin_without_wildcard(self):
        """场景 2: 无 '*' 通配 → False"""
        user = {
            'user_id': 2,
            'username': 'viewer',
            'roles': [{'code': 'viewer', 'name': '查看者'}],
            'permissions': ['user:read', 'role:read'],
        }
        assert is_admin(user) is False

    def test_non_admin_with_only_is_super_admin_dict(self):
        """场景 2b: V1 简化: role.is_super_admin=True 已不再识别"""
        # 旧行为: is_super_admin=True 也算 admin
        # V1 行为: 只看 '*' 通配
        user = {
            'user_id': 3,
            'username': 'old_admin',
            'roles': [{'code': 'admin', 'name': '管理员', 'is_super_admin': True}],
            'permissions': ['user:read'],  # 无 '*'
        }
        assert is_admin(user) is False

    def test_none_user_info(self):
        """场景 3: user_info=None → False (不抛异常)"""
        assert is_admin(None) is False

    def test_empty_user_info(self):
        """场景 3b: 空 dict → False"""
        assert is_admin({}) is False

    def test_missing_permissions_key(self):
        """场景 3c: 缺少 permissions 字段 → False"""
        user = {'user_id': 1, 'username': 'admin'}
        assert is_admin(user) is False

    def test_malformed_permissions_type(self):
        """场景 4: permissions 字段是异常类型 → False (不抛异常)"""
        user = {'user_id': 1, 'permissions': 12345}  # int, 不是可迭代对象
        # 不应抛 TypeError, 应返回 False
        assert is_admin(user) is False

    def test_permissions_is_none(self):
        """场景 4b: permissions = None → False"""
        user = {'user_id': 1, 'permissions': None}
        assert is_admin(user) is False

    def test_admin_with_wildcard_string(self):
        """场景 1d: permissions 是 '*' 单元素 list → True"""
        user = {'user_id': 1, 'permissions': ['*']}
        assert is_admin(user) is True

    def test_admin_with_wildcard_in_string_with_other(self):
        """场景 1e: permissions 列表中含 '*' 和其他 → True"""
        user = {'user_id': 1, 'permissions': ['user:read', '*', 'role:read']}
        assert is_admin(user) is True
