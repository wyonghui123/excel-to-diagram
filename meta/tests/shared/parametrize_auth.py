# -*- coding: utf-8 -*-
"""
[MODULE] 参数化认证测试工具
[DESCRIPTION] 提供用户角色权限的参数化测试功能

使用方式：
1. 使用 @parametrize_auth 装饰器生成测试函数
2. 使用 AuthTestCases 类定义测试用例
3. 使用权限常量定义标准角色和权限

示例：
    # 方式 1: 使用装饰器
    @parametrize_auth(['admin', 'viewer'], ['*', 'user:read'])
    def test_auth(api_client, headers, role, permissions):
        ...

    # 方式 2: 使用类定义
    class TestUserPermission(AuthTestCases):
        roles = ['admin', 'viewer']
        permissions = ['*', 'user:read']

    # 权限检查
    @parametrize_permissions(['user:read', 'user:write', 'user:delete'])
    def test_permission(api_client, headers, permission):
        ...
"""

import pytest
import jwt as pyjwt
import os
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass


# ==================== 角色和权限定义 ====================

# 标准角色
STANDARD_ROLES = {
    'super_admin': {'code': 'super_admin', 'name': '超级管理员', 'is_super_admin': True},
    'admin': {'code': 'admin', 'name': '管理员', 'is_super_admin': False},
    'developer': {'code': 'developer', 'name': '开发者', 'is_super_admin': False},
    'viewer': {'code': 'viewer', 'name': '查看者', 'is_super_admin': False},
    'operator': {'code': 'operator', 'name': '操作员', 'is_super_admin': False},
    'guest': {'code': 'guest', 'name': '访客', 'is_super_admin': False},
}

# 标准权限
STANDARD_PERMISSIONS = [
    'user:read', 'user:write', 'user:delete',
    'role:read', 'role:write', 'role:delete',
    'domain:read', 'domain:write', 'domain:delete',
    '*',  # 所有权限
]

# 角色默认权限映射
ROLE_DEFAULT_PERMISSIONS = {
    'super_admin': ['*'],
    'admin': ['*'],
    'developer': ['user:read', 'user:write', 'role:read', 'domain:read', 'domain:write'],
    'viewer': ['user:read', 'role:read', 'domain:read'],
    'operator': ['user:read', 'user:write', 'domain:read', 'domain:write'],
    'guest': ['user:read', 'domain:read'],
}


# ==================== 辅助函数 ====================

def create_token(user_id: str = '1', username: str = 'admin',
                display_name: str = 'Admin', roles: List = None,
                permissions: List = None, **extra_claims) -> str:
    """
    [FUNCTION] 创建 JWT Token
    [DESCRIPTION] 生成测试用 JWT Token
    [PARAMETERS]
        - user_id: str - 用户 ID
        - username: str - 用户名
        - display_name: str - 显示名称
        - roles: List - 角色列表
        - permissions: List - 权限列表
        - **extra_claims: Dict - 额外的 JWT claims
    [RETURN] str: JWT Token
    """
    if roles is None:
        roles = [{'code': 'admin', 'name': '管理员'}]

    if permissions is None:
        permissions = ['*']

    secret = os.environ.get('JWT_SECRET_KEY', 'dev-only-secret-key-not-for-production-use')
    payload = {
        'user_id': user_id,
        'username': username,
        'display_name': display_name,
        'roles': roles,
        'permissions': permissions,
        'exp': 9999999999,
        **extra_claims
    }

    token = pyjwt.encode(payload, secret, algorithm='HS256')
    if isinstance(token, bytes):
        token = token.decode('utf-8')
    return token


def create_headers(user_id: str = '1', username: str = 'admin',
                  roles: List = None, permissions: List = None,
                  extra_headers: Dict = None) -> Dict:
    """
    [FUNCTION] 创建认证请求头
    [DESCRIPTION] 生成包含 JWT Token 的请求头
    [PARAMETERS]
        - user_id: str - 用户 ID
        - username: str - 用户名
        - roles: List - 角色列表
        - permissions: List - 权限列表
        - extra_headers: Dict - 额外的请求头
    [RETURN] Dict: 请求头
    """
    token = create_token(user_id, username, roles=roles, permissions=permissions)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': user_id,
        'X-User-Name': username
    }

    if extra_headers:
        headers.update(extra_headers)

    return headers


def create_role_token(role_code: str, permissions: List = None) -> str:
    """
    [FUNCTION] 创建指定角色的 Token
    [DESCRIPTION] 根据角色代码生成 Token
    [PARAMETERS]
        - role_code: str - 角色代码
        - permissions: List - 权限列表（可选，默认使用角色默认权限）
    [RETURN] str: JWT Token
    """
    role_info = STANDARD_ROLES.get(role_code, {'code': role_code, 'name': role_code})
    role_permissions = permissions or ROLE_DEFAULT_PERMISSIONS.get(role_code, [])

    return create_token(
        user_id='1',
        username=f'test_{role_code}',
        display_name=f'Test {role_info["name"]}',
        roles=[role_info],
        permissions=role_permissions
    )


# ==================== Pytest 参数化 ====================

def parametrize_auth(roles: List = None, permissions: List = None,
                   include_admin: bool = True):
    """
    [DECORATOR] 认证参数化装饰器
    [DESCRIPTION] 生成用户认证参数
    [PARAMETERS]
        - roles: List - 角色列表
        - permissions: List - 权限列表
        - include_admin: bool - 是否包含管理员
    [RETURN] pytest.mark.parametrize 装饰器
    [USAGE]
        @parametrize_auth(['admin', 'viewer'], ['*', 'user:read'])
        def test_auth(api_client, headers, role, permissions):
            ...
    """
    if roles is None:
        roles = list(STANDARD_ROLES.keys())

    arg_values = []
    for role in roles:
        role_info = STANDARD_ROLES.get(role, {'code': role, 'name': role})
        role_perms = permissions or ROLE_DEFAULT_PERMISSIONS.get(role, [])

        token = create_token(
            user_id='1',
            username=f'test_{role}',
            display_name=f'Test {role_info["name"]}',
            roles=[role_info],
            permissions=role_perms
        )

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-User-Id': '1',
            'X-User-Name': f'test_{role}'
        }

        arg_values.append((headers, role, role_perms))

    return pytest.mark.parametrize('headers,role,permissions', arg_values)


def parametrize_permissions(permissions: List):
    """
    [DECORATOR] 权限参数化装饰器
    [DESCRIPTION] 生成权限测试参数
    [PARAMETERS]
        permissions: List - 权限列表
    [RETURN] pytest.mark.parametrize 装饰器
    [USAGE]
        @parametrize_permissions(['user:read', 'user:write'])
        def test_permission(api_client, headers, permission):
            ...
    """
    arg_values = [(p,) for p in permissions]
    return pytest.mark.parametrize('permission', arg_values)


def parametrize_roles(roles: List = None):
    """
    [DECORATOR] 角色参数化装饰器
    [DESCRIPTION] 生成角色测试参数
    [PARAMETERS]
        roles: List - 角色列表
    [RETURN] pytest.mark.parametrize 装饰器
    [USAGE]
        @parametrize_roles(['admin', 'viewer'])
        def test_role_access(api_client, headers, role_code):
            ...
    """
    if roles is None:
        roles = list(STANDARD_ROLES.keys())

    arg_values = [(role,) for role in roles]
    return pytest.mark.parametrize('role_code', arg_values)


# ==================== 测试用例类 ====================

class AuthTestCases:
    """
    [CLASS] 认证测试用例集合
    [DESCRIPTION] 提供标准化的认证测试用例定义

    使用方式：
        class TestUserAuth(AuthTestCases):
            roles = ['admin', 'viewer']
            permissions = ['*', 'user:read', 'user:write']

            @pytest.mark.parametrize('headers,role,permissions', AuthTestCases.parametrize())
            def test_auth(self, api_client, headers, role, permissions):
                ...
    """

    roles: List[str] = None
    permissions: List[str] = None

    @classmethod
    def parametrize(cls):
        """生成参数化测试数据"""
        if cls.roles is None:
            cls.roles = list(STANDARD_ROLES.keys())

        arg_values = []
        for role in cls.roles:
            role_info = STANDARD_ROLES.get(role, {'code': role, 'name': role})
            role_perms = cls.permissions or ROLE_DEFAULT_PERMISSIONS.get(role, [])

            token = create_token(
                user_id='1',
                username=f'test_{role}',
                display_name=f'Test {role_info["name"]}',
                roles=[role_info],
                permissions=role_perms
            )

            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}',
                'X-User-Id': '1',
                'X-User-Name': f'test_{role}'
            }

            arg_values.append((headers, role, role_perms))

        return pytest.mark.parametrize('headers,role,permissions', arg_values)

    @classmethod
    def get_headers(cls, role: str, permissions: List = None):
        """获取指定角色的请求头"""
        return create_headers(roles=[role], permissions=permissions)


# ==================== 权限检查装饰器 ====================

def requires_permission(permission: str):
    """
    [DECORATOR] 权限检查装饰器
    [DESCRIPTION] 检查用户是否有所需权限
    [PARAMETERS]
        permission: str - 所需权限
    [RETURN] 装饰器函数
    [USAGE]
        @requires_permission('user:delete')
        def test_delete_user(api_client, headers):
            ...
    """
    def decorator(func):
        @pytest.mark.parametrize('headers,role,permissions', parametrize_auth())
        @pytest.mark.usefixtures('requires_permission')
        def wrapper(api_client, headers, role, permissions):
            if permission not in permissions and '*' not in permissions:
                pytest.skip(f"Role {role} does not have {permission}")
            return func(api_client, headers, role, permissions)
        return wrapper
    return decorator


# ==================== 导出 ====================

__all__ = [
    'STANDARD_ROLES',
    'STANDARD_PERMISSIONS',
    'ROLE_DEFAULT_PERMISSIONS',
    'create_token',
    'create_headers',
    'create_role_token',
    'parametrize_auth',
    'parametrize_permissions',
    'parametrize_roles',
    'AuthTestCases',
    'requires_permission',
]
