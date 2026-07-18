"""
RolePermissionFactory (Phase 6 新建)
======================================

角色权限关联工厂: 用于角色-权限多对多关联测试

yaml: meta/schemas/role_permission.yaml
required 字段:
- role_id (关联角色)
- permission_id (关联权限)
- granted (授予状态, 默认 true)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class RolePermissionFactory(BaseFactory):
    """角色权限关联工厂"""

    _OBJECT_TYPE = 'role_permission'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        return {
            # 真实调用必须用 create_for_role() 显式传入
            'role_id': None,  # 需配 RoleFactory
            'permission_id': None,  # 需配 PermissionFactory
            'granted': True,
        }

    @classmethod
    def create_for_role(
        cls, role_id: int, permission_id: int, granted: bool = True,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """为指定角色分配权限"""
        return cls.create(
            cookie=cookie,
            role_id=role_id,
            permission_id=permission_id,
            granted=granted,
            **overrides
        )

    @classmethod
    def create_grant(
        cls, role_id: int, permission_id: int, cookie=None, **overrides
    ) -> Dict[str, Any]:
        """授予权限 (granted=True)"""
        return cls.create_for_role(role_id, permission_id, granted=True, cookie=cookie, **overrides)

    @classmethod
    def create_deny(
        cls, role_id: int, permission_id: int, cookie=None, **overrides
    ) -> Dict[str, Any]:
        """排除权限 (granted=False)"""
        return cls.create_for_role(role_id, permission_id, granted=False, cookie=cookie, **overrides)
