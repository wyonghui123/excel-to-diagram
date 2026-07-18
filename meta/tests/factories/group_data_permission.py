"""
GroupDataPermissionFactory (Phase 5 新建)
==========================================

用户组数据权限工厂: 用于数据层级权限测试

yaml: meta/schemas/group_data_permission.yaml
required 字段 (排除审计自动生成):
- group_id
- resource_type (enum: domain/sub_domain/service_module/business_object)
- resource_id
- permission_level (enum: read/write/admin)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class GroupDataPermissionFactory(BaseFactory):
    """用户组数据权限工厂"""

    _OBJECT_TYPE = 'group_data_permission'

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
        suffix = unique_str(4)
        return {
            # [FIX 2026-07-17 P1] 覆盖 yaml 必填字段
            # 真实调用必须用 create_for_group() 显式传入
            'group_id': None,  # 需配 UserGroupFactory
            'resource_type': cls.RESOURCE_DOMAIN,
            'resource_id': None,  # 需配实际资源
            'permission_level': cls.LEVEL_READ,
            # 业务字段 (使用 yaml default 值)
            'inherit_to_children': True,
        }

    @classmethod
    def create_for_group(
        cls,
        group_id: int,
        resource_type: str,
        resource_id: int,
        level: str = 'read',
        cookie=None,
        **overrides
    ) -> Dict[str, Any]:
        """为指定用户组创建数据权限"""
        return cls.create(
            cookie=cookie,
            group_id=group_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission_level=level,
            **overrides
        )

    @classmethod
    def create_read_only(
        cls, group_id: int, resource_type: str, resource_id: int,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建只读权限"""
        return cls.create_for_group(
            group_id, resource_type, resource_id, cls.LEVEL_READ, cookie, **overrides
        )

    @classmethod
    def create_admin(
        cls, group_id: int, resource_type: str, resource_id: int,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建管理员权限"""
        return cls.create_for_group(
            group_id, resource_type, resource_id, cls.LEVEL_ADMIN, cookie, **overrides
        )