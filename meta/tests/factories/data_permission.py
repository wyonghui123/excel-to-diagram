"""
DataPermissionFactory (Phase 6 新建)
=======================================

数据权限工厂: 用于用户级别数据访问权限测试

yaml: meta/schemas/data_permission.yaml
required 字段:
- user_id (关联用户)
- resource_type (资源类型)
- resource_id (资源实例ID)
- permission_level (权限级别)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class DataPermissionFactory(BaseFactory):
    """数据权限工厂"""

    _OBJECT_TYPE = 'data_permission'

    # 标准 resource_type 值
    RESOURCE_DOMAIN = 'domain'
    RESOURCE_SUB_DOMAIN = 'sub_domain'
    RESOURCE_SERVICE_MODULE = 'service_module'
    RESOURCE_BUSINESS_OBJECT = 'business_object'

    # 标准 permission_level 值
    LEVEL_READ = 'read'
    LEVEL_WRITE = 'write'
    LEVEL_ADMIN = 'admin'

    @classmethod
    def _base_defaults(cls) -> Dict[str, Any]:
        n = cls._next_counter()
        return {
            # 真实调用必须用 create_for_user() 显式传入
            'user_id': None,  # 需配 UserFactory
            'resource_type': cls.RESOURCE_DOMAIN,
            'resource_id': None,  # 需配实际资源
            'permission_level': cls.LEVEL_READ,
            'inherit_to_children': True,
        }

    @classmethod
    def create_for_user(
        cls, user_id: int, resource_type: str, resource_id: int,
        level: str = 'read', cookie=None, **overrides
    ) -> Dict[str, Any]:
        """为指定用户创建数据权限"""
        return cls.create(
            cookie=cookie,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission_level=level,
            **overrides
        )

    @classmethod
    def create_read_only(
        cls, user_id: int, resource_type: str, resource_id: int,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建只读权限"""
        return cls.create_for_user(
            user_id, resource_type, resource_id, cls.LEVEL_READ, cookie, **overrides
        )

    @classmethod
    def create_admin(
        cls, user_id: int, resource_type: str, resource_id: int,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建管理员权限"""
        return cls.create_for_user(
            user_id, resource_type, resource_id, cls.LEVEL_ADMIN, cookie, **overrides
        )
