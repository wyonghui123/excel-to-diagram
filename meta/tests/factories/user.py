"""
UserFactory (Phase 1 扩展)
===========================

扩展原 UserFactory, 添加:
- create_admin (admin 角色)
- create_with_role (指定 role)
- 显式 password 字段
- 多 Agent 并行安全 (_COUNTER 含 PID)

TBD-4 采纳: counter+random 人类可读
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, unique_id, register_factory


@register_factory
class UserFactory(BaseFactory):
    """用户工厂"""

    _OBJECT_TYPE = 'user'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        suffix = unique_str(6)
        return {
            'username': f'test_user_{n}_{suffix}',
            'display_name': f'Test User {n}',
            'email': f'user_{n}_{suffix}@test.local',
            'role': 'user',
            'password': 'Test@12345',
            'is_active': True,
        }

    @classmethod
    def create_admin(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建 admin 用户"""
        return cls.create(cookie=cookie, role='admin', **overrides)

    @classmethod
    def create_with_role(cls, role: str, cookie=None, **overrides) -> Dict[str, Any]:
        """创建指定角色的用户"""
        return cls.create(cookie=cookie, role=role, **overrides)

    @classmethod
    def create_disabled(cls, cookie=None, **overrides) -> Dict[str, Any]:
        """创建禁用用户"""
        return cls.create(cookie=cookie, is_active=False, **overrides)
