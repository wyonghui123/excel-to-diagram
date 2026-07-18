"""
PermissionRuleFactory (Phase 6 新建)
=======================================

条件权限规则工厂: 用于基于条件的动态权限规则测试

yaml: meta/schemas/permission_rule.yaml
required 字段:
- role_id (关联角色)
- resource_type (资源类型)
- condition (条件表达式, JSON)
- permission_level (权限级别)
"""
from typing import Dict, Any
from ._base import BaseFactory, unique_str, register_factory


@register_factory
class PermissionRuleFactory(BaseFactory):
    """条件权限规则工厂"""

    _OBJECT_TYPE = 'permission_rule'

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
            # 真实调用必须用 create_for_role() 显式传入
            'role_id': None,  # 需配 RoleFactory
            'resource_type': cls.RESOURCE_DOMAIN,
            'condition': '{}',  # 默认无条件
            'permission_level': cls.LEVEL_READ,
            'is_denied': False,
            'inherit_to_children': True,
            'propagate_to_parents': True,
        }

    @classmethod
    def create_for_role(
        cls, role_id: int, resource_type: str, condition: str,
        level: str = 'read', cookie=None, **overrides
    ) -> Dict[str, Any]:
        """为指定角色创建条件权限规则"""
        return cls.create(
            cookie=cookie,
            role_id=role_id,
            resource_type=resource_type,
            condition=condition,
            permission_level=level,
            **overrides
        )

    @classmethod
    def create_deny_rule(
        cls, role_id: int, resource_type: str, condition: str,
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建拒绝规则 (is_denied=True)"""
        return cls.create(
            cookie=cookie,
            role_id=role_id,
            resource_type=resource_type,
            condition=condition,
            is_denied=True,
            **overrides
        )

    @classmethod
    def create_simple_allow(
        cls, role_id: int, resource_type: str, level: str = 'read',
        cookie=None, **overrides
    ) -> Dict[str, Any]:
        """创建简单允许规则 (无条件)"""
        return cls.create_for_role(
            role_id, resource_type, '{}', level, cookie, **overrides
        )
